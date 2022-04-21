import dis
import os
import socket
import threading
import select
import sys
import logging
import logs.config_server_log
import argparse
import common.functions as functions
import common.constants as constants
import common.alerts
import sevrer_db
import configparser
from PyQt5.QtWidgets import QApplication, QMessageBox
import common.server_gui as gui
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QStandardItemModel, QStandardItem

server_log = logging.getLogger('server')
new_connection_flag = False
thread_lock = threading.Lock()


class NonNegativePort:
    def __set__(self, instance, value):
        if not 0 < value < 65536:
            raise ValueError("Значение порта должно быть целым неотрицательным числом")
        instance.__dict__[self.port_number] = value

    def __set_name__(self, owner, port_number):
        self.port_number = port_number


class ServerVerifier(type):
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
        super().__init__()

    def presence_message_validation(self, client, message):
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
                return common.alerts.alert_409
            with thread_lock:
                new_connection_flag = True
            return common.alerts.alert_200
        else:
            return common.alerts.alert_400

    def message_type_separation(self, client, message_obj, messages_list):
        global new_connection_flag
        if "action" in message_obj \
                and message_obj["action"] == "presence":
            presence = self.presence_message_validation(client, message_obj)
            if presence["response"] != 400:
                functions.send_message(client, presence)
            return

        elif "action" in message_obj \
                and message_obj["action"] == "msg" \
                and "time" in message_obj \
                and "message" in message_obj:
            messages_list.append(message_obj)
            self.db.process_message(message_obj['from'], message_obj['to'])
            return

        elif "action" in message_obj \
                and message_obj["action"] == "exit" \
                and "from" in message_obj:
            self.db.user_logout(message_obj["from"])
            self.clients.remove(self.clients_names[message_obj["from"]])
            self.clients_names[message_obj["from"]].close()
            del self.clients_names[message_obj["from"]]
            with thread_lock:
                new_connection_flag = True
            return

        elif "action" in message_obj \
                and message_obj["action"] == 'get_contacts' \
                and 'user' in message_obj \
                and self.clients_names[message_obj['user']] == client:
            response = common.alerts.response_202
            response["alert"] = self.db.get_contacts(message_obj['user'])
            functions.send_message(client, response)

        elif "action" in message_obj \
                and message_obj["action"] == 'add_contacts' \
                and 'user' in message_obj \
                and 'account_name' in message_obj  \
                and self.clients_names[message_obj['user']] == client:
            self.db.add_contact(message_obj['user'], message_obj['account_name'])
            functions.send_message(client, common.alerts.alert_200)

        elif "action" in message_obj \
                and message_obj["action"] == 'del_contacts' \
                and 'user' in message_obj \
                and 'account_name' in message_obj \
                and self.clients_names[message_obj['user']] == client:
            self.db.remove_contact(message_obj['user'], message_obj['account_name'])
            functions.send_message(client, common.alerts.alert_200)

        elif "action" in message_obj \
                and message_obj["action"] == "users_request" \
                and 'account_name' in message_obj \
                and self.clients_names[message_obj['account_name']] == client:
            response = common.alerts.response_202
            response['alert'] = [user[0] for user in self.db.users_list()]
            functions.send_message(client, response)

        else:
            functions.send_message(client, {
                "response": 400,
                "error": 'Bad Request'
            })
            return

    def init(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((self.listen_address, self.listen_port))
        server.settimeout(1)

        self.socket = server
        server_log.info(f'Запушен сервер. Адрес: {self.listen_address}. Порт: {self.listen_port}')
        self.socket.listen(constants.MAX_CLIENTS)

    def run(self):
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
                        self.message_type_separation(client_with_message, a, self.messages)
                    except OSError:
                        server_log.info(f'Клиент {client_with_message.getpeername()} отключился от сервера.')
                        for name in self.clients_names:
                            if self.clients_names[name] == client_with_message:
                                self.db.user_logout(name)
                                del self.clients_names[name]
                                break
                        self.clients.remove(client_with_message)

            for message in self.messages:
                try:
                    self.process_message(message, send_data_list)
                except (ConnectionAbortedError, ConnectionError, ConnectionResetError, ConnectionRefusedError):
                    server_log.info(
                        f'Связь с клиентом с именем {message["to"]} была потеряна')
                    self.clients.remove(self.clients_names[message["to"]])
                    self.db.user_logout(message["to"])
                    del self.clients_names[message["to"]]
            self.messages.clear()

    def process_message(self, message, listen_socks):
        print(message)
        print(type(message))
        print(type(listen_socks))
        if message["to"] in self.clients_names and self.clients_names[message["to"]] in listen_socks:
            functions.send_message(self.clients_names[message["to"]], message)
            server_log.info(f'Отправлено сообщение пользователю {message["to"]} от пользователя {message["from"]}.')
        elif message["to"] in self.clients_names and self.clients_names[message["to"]] not in listen_socks:
            raise ConnectionError
        else:
            server_log.error(f'Пользователь {message["to"]} не зарегистрирован на сервере,'
                             f' отправка сообщения невозможна.')

    def console_interface(self):
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
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', default=port, type=int, nargs='?')
    parser.add_argument('-a', default=address, nargs='?')
    namespace = parser.parse_args(sys.argv[1:])
    listen_addr = namespace.a
    listen_port = namespace.p
    return listen_addr, listen_port


def print_help():
    print('Поддерживаемые комманды:')
    print('users - список известных пользователей')
    print('connected - список подключённых пользователей')
    print('loghist - история входов пользователя')
    print('exit - завершение работы сервера.')
    print('help - вывод справки по поддерживаемым командам')


def main():
    config = configparser.ConfigParser()
    dir_path = os.path.dirname(os.path.realpath(__file__))
    config.read(f"{dir_path}/{'server.ini'}")
    listen_addr, listen_port = arg_parser(config['SETTINGS']['Default_port'], config['SETTINGS']['Listen_Address'])
    database = sevrer_db.ServerStorage(os.path.join(config['SETTINGS']['Database_path'],
                                                    config['SETTINGS']['Database_file']))

    server_run = Server(listen_addr, listen_port, database)
    server_run.daemon = True
    server_run.start()
    # server_run.console_interface()

    server_app = QApplication(sys.argv)
    main_window = gui.MainWindow()

    main_window.statusBar().showMessage('Server Working')
    main_window.active_clients_table.setModel(gui.gui_create_model(database))
    main_window.active_clients_table.resizeColumnsToContents()
    main_window.active_clients_table.resizeRowsToContents()

    def list_update():
        global new_connection_flag
        if new_connection_flag:
            main_window.active_clients_table.setModel(
                gui.gui_create_model(database))
            main_window.active_clients_table.resizeColumnsToContents()
            main_window.active_clients_table.resizeRowsToContents()
            with thread_lock:
                new_connection_flag = False

    def show_statistics():
        global stat_window
        stat_window = gui.HistoryWindow()
        stat_window.history_table.setModel(gui.create_stat_model(database))
        stat_window.history_table.resizeColumnsToContents()
        stat_window.history_table.resizeRowsToContents()
        stat_window.show()

    def server_config():
        global config_window
        config_window = gui.ConfigWindow()
        config_window.db_path.insert(config['SETTINGS']['Database_path'])
        config_window.db_file.insert(config['SETTINGS']['Database_file'])
        config_window.port.insert(config['SETTINGS']['Default_port'])
        config_window.ip.insert(config['SETTINGS']['Listen_Address'])
        config_window.save_btn.clicked.connect(save_server_config)

    def save_server_config():
        global config_window
        message = QMessageBox()
        config['SETTINGS']['Database_path'] = config_window.db_path.text()
        config['SETTINGS']['Database_file'] = config_window.db_file.text()
        try:
            port = int(config_window.port.text())
        except ValueError:
            message.warning(config_window, 'Ошибка', 'Порт должен быть числом')
        else:
            config['SETTINGS']['Listen_Address'] = config_window.ip.text()
            if 1023 < port < 65536:
                config['SETTINGS']['Default_port'] = str(port)
                print(port)
                with open('server.ini', 'w') as conf:
                    config.write(conf)
                    message.information(
                        config_window, 'OK', 'Настройки успешно сохранены!')
            else:
                message.warning(
                    config_window,
                    'Ошибка',
                    'Порт должен быть от 1024 до 65536')

    timer = QTimer()
    timer.timeout.connect(list_update)
    timer.start(1000)

    main_window.refresh_button.triggered.connect(list_update)
    main_window.show_history_button.triggered.connect(show_statistics)
    main_window.config_btn.triggered.connect(server_config)

    server_app.exec_()


if __name__ == '__main__':
    main()
