import argparse
import binascii
import dis
import hmac
import os
import socket
import threading
from json import JSONDecodeError

import select
import sys
import logging
import server.logs.config_server_log

import server.common.functions as functions
import server.common.constants as constants
import server.common.alerts
import server.common.sevrer_db
import configparser
from PyQt5.QtWidgets import QMessageBox

from server.common.decorators import login_required
from server.common.main_window import MainWindow
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

server_log = logging.getLogger('server')
thread_lock = threading.RLock()


class NonNegativePort:
    """Класс дескримптор проверки правильного введения параметра порта в объекте классе сервера Server()"""
    def __set__(self, instance, value):
        if not 0 < value < 65536:
            raise ValueError("Значение порта должно быть целым неотрицательным числом")
        instance.__dict__[self.port_number] = value

    def __set_name__(self, owner, port_number):
        self.port_number = port_number


class ServerVerifier(type):
    """Метакласс, проверяющий что в результирующем классе
    нет клиентских вызовов "connect".
    """
    def __init__(cls, class_name, class_parents, class_dict):
        methods = []
        for func in class_dict:
            try:
                ret = dis.get_instructions(class_dict[func])
            except TypeError:
                pass
            else:
                for i in ret:
                    if i.opname == 'LOAD_METHOD':
                        if i.argval not in methods:
                            methods.append(i.argval)
                for i in ret:
                    if i.opname == 'LOAD_GLOBAL':
                        if i.argval not in methods:
                            methods.append(i.argval)
        if 'connect' in methods:
            raise TypeError('В классе обнаружено использование запрещённого метода "accept" и "listen"')
        elif 'get_message' in methods or 'send_message' in methods:
            pass
        else:
            raise TypeError('Отсутствуют вызовы функций, работающих с сокетами.')
        super().__init__(class_name, class_parents, class_dict)


class Server(threading.Thread, metaclass=ServerVerifier):


    listen_port = NonNegativePort()

    def __init__(self, listen_address, listen_port, db):
        self.listen_address = listen_address
        self.listen_port = listen_port
        self.messages = []
        self.clients = []
        self.clients_names = dict()
        self.db = db
        self.socket = None
        super().__init__()

    def init(self):
        """Метод создания сокета"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((self.listen_address, self.listen_port))
        server.settimeout(1)

        self.socket = server
        server_log.info(f'Запушен сервер. Адрес: {self.listen_address}. Порт: {self.listen_port}')
        self.socket.listen(constants.MAX_CLIENTS)

    def run(self):
        """
        Основной цикл работы сервера
        """
        global new_connection_flag
        self.init()

        while True:
            try:
                client, address = self.socket.accept()
            except OSError:
                pass
            else:
                server_log.info(f'Установлено соедение с ПК {address}')
                self.clients.append(client)

            recv_data_list = []
            send_data_list = []
            err_list = []

            try:
                if self.clients:
                    recv_data_list, send_data_list, err_list = select.select(self.clients, self.clients, [], 0)
            except OSError:
                pass

            if recv_data_list:
                for client_with_message in recv_data_list:
                    try:
                        a = functions.get_message(client_with_message)
                        self.message_type_separation(client_with_message, a)
                    except OSError:
                        server_log.info(f'Клиент {client_with_message.getpeername()} отключился от сервера.')
                        for name in self.clients_names:
                            if self.clients_names[name] == client_with_message:
                                self.db.user_logout(name)
                                del self.clients_names[name]
                                break
                        self.clients.remove(client_with_message)
                    except JSONDecodeError as err:
                        server_log.error(f'Ошибка при декодировании файла. Ошибка {err}')
                        pass
                    with thread_lock:
                        new_connection_flag = True

            for message in self.messages:
                try:
                    self.process_message(message, send_data_list)
                except (ConnectionAbortedError, ConnectionError, ConnectionResetError, ConnectionRefusedError):
                    server_log.info(
                        f'Связь с клиентом с именем {message["to"]} была потеряна')
                    self.clients.remove(self.clients_names[message["to"]])
                    self.db.user_logout(message["to"])
                    del self.clients_names[message["to"]]
                    with thread_lock:
                        new_connection_flag = True
            self.messages.clear()

    @login_required
    def message_type_separation(self, client, message_obj):
        print(message_obj)
        """
        Метод обработки сообщений полученных от клиента
        """
        global new_connection_flag
        if "action" in message_obj \
                and message_obj["action"] == "presence":
            self.autorize_user(message_obj, client)

        elif "action" in message_obj \
                and message_obj["action"] == "msg" \
                and "time" in message_obj \
                and "message" in message_obj:
            self.messages.append(message_obj)
            self.db.process_message(message_obj['from'], message_obj['to'])

        elif "action" in message_obj \
                and message_obj["action"] == "exit" \
                and "from" in message_obj:
            self.remove_client(client)

        elif "action" in message_obj \
                and message_obj["action"] == 'get_contacts' \
                and 'user' in message_obj \
                and self.clients_names[message_obj['user']] == client:
            response = server.common.alerts.response_202
            response["alert"] = self.db.get_contacts(message_obj['user'])
            functions.send_message(client, response)

        elif "action" in message_obj \
                and message_obj["action"] == 'add_contact' \
                and 'user' in message_obj \
                and 'account_name' in message_obj \
                and self.clients_names[message_obj['user']] == client:
            self.db.add_contact(message_obj['user'], message_obj['account_name'])
            functions.send_message(client, server.common.alerts.alert_200)

        elif "action" in message_obj \
                and message_obj["action"] == 'del_contacts' \
                and 'user' in message_obj \
                and 'account_name' in message_obj \
                and self.clients_names[message_obj['user']] == client:
            self.db.remove_contact(message_obj['user'], message_obj['account_name'])
            functions.send_message(client, server.common.alerts.alert_200)

        elif "action" in message_obj \
                and message_obj["action"] == "users_request" \
                and 'account_name' in message_obj \
                and self.clients_names[message_obj['account_name']] == client:
            response = server.common.alerts.response_202
            response['alert'] = [user[0] for user in self.db.users_list()]
            functions.send_message(client, response)

        elif "action" in message_obj and message_obj["action"] == "public_key_request" \
                and "account_name" in message_obj:
            response = server.common.alerts.alert_511
            response['bin'] = self.db.get_pubkey(message_obj["account_name"])

            if response['bin']:
                try:
                    functions.send_message(client, response)
                except OSError:
                    self.remove_client(client)
            else:
                response = server.common.alerts.alert_400
                response["error"] = 'Нет публичного ключа для данного пользователя'
                try:
                    functions.send_message(client, response)
                except OSError:
                    self.remove_client(client)

        else:
            functions.send_message(client, {
                "response": "400",
                "error": 'Bad Request'
            })
            return

    def presence_message_validation(self, client, message):
        """Метод обработки сообщений клиента в формате 'presence' """
        global new_connection_flag
        if "action" in message and message["action"] == 'presence' and "time" in message and "type" in message \
                and message["type"] == "status" and "account_name" in message["user"] and "status" in message["user"]:
            if message["user"]["account_name"] not in self.clients_names.keys():
                self.clients_names[message['user']['account_name']] = client
                name = message["user"]["account_name"]
                client_ip_addr = client.getpeername()[0]
                client_port = int(client.getpeername()[1])
                self.db.user_login(name, client_ip_addr, client_port)
            else:
                return server.common.alerts.alert_409
            with thread_lock:
                new_connection_flag = True
            return server.common.alerts.alert_200
        else:
            return server.common.alerts.alert_400

    def process_message(self, message, listen_socks):
        """Метод отправки сообщеий клиентам подключенным к серверу."""
        if message["to"] in self.clients_names and self.clients_names[message["to"]] in listen_socks:
            functions.send_message(self.clients_names[message["to"]], message)
            server_log.info(f'Отправлено сообщение пользователю {message["to"]} от пользователя {message["from"]}.')

        elif message["to"] in self.clients_names and self.clients_names[message["to"]] not in listen_socks:
            raise ConnectionError

        else:
            server_log.error(f'Пользователь {message["to"]} не зарегистрирован на сервере,'
                             f' отправка сообщения невозможна.')

    def autorize_user(self, message, sock):
        server_log.debug(f'Start auth process for {message["user"]}')
        if message["user"]["account_name"] in self.clients_names.keys():
            response = server.common.alerts.alert_400
            response["error"] = 'Имя пользователя уже занято.'
            try:
                server_log.debug(f'Username busy, sending {response}')
                functions.send_message(sock, response)
            except OSError:
                server_log.debug('OS Error')
                pass
            self.clients.remove(sock)
            sock.close()
        elif not self.db.check_user(message["user"]["account_name"]):
            response = server.common.alerts.alert_400
            response["error"] = 'Пользователь не зарегистрирован.'
            try:
                server_log.debug(f'Unknown username, sending {response}')
                functions.send_message(sock, response)
            except OSError:
                pass
            self.clients.remove(sock)
            sock.close()
        else:
            server_log.debug('Correct username, starting passwd check.')
            message_auth = server.common.alerts.alert_511
            random_str = binascii.hexlify(os.urandom(64))
            message_auth["bin"] = random_str.decode('utf-8')

            hash_var = hmac.new(self.db.get_hash(message["user"]["account_name"]), random_str, 'MD5')

            digest = hash_var.digest()
            server_log.debug(f'Auth message = {message_auth}')
            try:
                functions.send_message(sock, message_auth)
                ans = functions.get_message(sock)
            except OSError as err:
                server_log.debug('Error in auth, data:', exc_info=err)
                sock.close()
                return
            client_digest = binascii.a2b_base64(ans["bin"])
            if 'response' in ans and ans["response"] == "511" and hmac.compare_digest(digest, client_digest):
                self.clients_names[message["user"]["account_name"]] = sock
                client_ip, client_port = sock.getpeername()
                try:
                    functions.send_message(sock, server.common.alerts.alert_200)
                except OSError:
                    self.remove_client(message["user"]["account_name"])
                self.db.user_login(message["user"]["account_name"],
                                   client_ip,
                                   client_port,
                                   message["user"]["public_key"])
            else:
                response = server.common.alerts.alert_400
                response["error"] = 'Неверный пароль.'
                try:
                    functions.send_message(sock, response)
                except OSError:
                    pass
                self.clients.remove(sock)
                sock.close()

    def service_update_lists(self):
        """
        Метод реализующий отправки сервисного сообщения 205 клиентам.
        """
        for client in self.clients_names:
            try:
                functions.send_message(self.clients_names[client], server.common.alerts.response_205)
            except OSError:
                self.remove_client(self.clients_names[client])

    def service_update_lists_(self):
        for client in self.clients_names:
            try:
                functions.send_message(self.clients_names[client], server.common.alerts.response_205)
            except OSError:
                self.remove_client(self.clients_names[client])

    def remove_client(self, client):
        """
        Метод удаления клиента из списка активных в случаи завершения работы или ошибки на стороне клиента
        """
        server_log.info(f'Клиент {client.getpeername()} отключился от сервера.')
        for name in self.clients_names:
            if self.clients_names[name] == client:
                self.db.user_logout(name)
                del self.clients_names[name]
                break
        self.clients.remove(client)
        client.close()

    def console_interface(self):
        """
        Метод доступа к функциям сервера без графического интерфейса.
        """
        def print_help():
            """
            Мето справка работы с сервером в режиме командной строки
            """
            print('Поддерживаемые комманды:')
            print('users - список известных пользователей')
            print('connected - список подключённых пользователей')
            print('loghist - история входов пользователя')
            print('exit - завершение работы сервера.')
            print('help - вывод справки по поддерживаемым командам')

        print_help()
        while True:
            command = input('Введите команду: ')
            if command == 'help':
                print_help()
            elif command == 'exit':
                break
            elif command == 'users':
                for user in sorted(self.db.users_list()):
                    print(f'Пользователь {user[0]}, последний вход: {user[1]}')
            elif command == 'connected':
                for user in sorted(self.db.active_users_list()):
                    print(
                        f'Пользователь {user[0]}, подключен: {user[1]}:{user[2]}, '
                        f'время установки соединения: {user[3]}')
            elif command == 'loghist':
                name = input('Введите имя пользователя для просмотра истории. '
                             'Для вывода всей истории, просто нажмите Enter: ')
                for user in sorted(self.db.login_history(name)):
                    print(f'Пользователь: {user[0]} время входа: {user[1]}. Вход с: {user[2]}:{user[3]}')
            else:
                print('Команда не распознана.')


def arg_parser(port, address):
    """
    Метод обработки параметров командной строки
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', default=port, type=int, nargs='?')
    parser.add_argument('-a', default=address, nargs='?')
    namespace = parser.parse_args(sys.argv[1:])
    listen_addr = namespace.a
    listen_port = namespace.p
    return listen_addr, listen_port

