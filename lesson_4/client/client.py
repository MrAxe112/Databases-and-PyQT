import argparse
import dis
import socket
import sys
import json
import logging
import common.functions as functions
import common.constants as constants
import threading
from common.decorators import log
import time
from client_database import ClientStorage

client_log = logging.getLogger('client')
thread_lock = threading.RLock()
second_thread_lock = threading.RLock()


@log
def arg_pars():
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', default=constants.DEFAULT_ADDRESS, nargs='?')
    parser.add_argument('-p', default=constants.DEFAULT_PORT, type=int, nargs='?')
    parser.add_argument('-n', '--name', default='default_user', nargs='?')
    namespace = parser.parse_args(sys.argv[1:])
    server_address = namespace.a
    server_port = namespace.p
    client_name = namespace.name
    if not 1023 < server_port < 65536:
        client_log.critical(
            f'Попытка запуска клиента с неподходящим номером порта: {server_port}. '
            f'Допустимы адреса с 1024 до 65535. Клиент завершается.')
        sys.exit(1)
    return server_address, server_port, client_name


class ClientVerifier(type):
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
        if 'accept' in methods or "listen" in methods:
            raise TypeError('В классе обнаружено использование запрещённого метода "accept" и "listen"')
        elif 'get_message' in methods or 'send_message' in methods:
            pass
        else:
            raise TypeError('Отсутствуют вызовы функций, работающих с сокетами.')
        super().__init__(class_name, class_parents, class_dict)


class ClientSender(threading.Thread, metaclass=ClientVerifier):
    def __init__(self, socket_name, user_name, database):
        super().__init__()
        self.socket_name = socket_name
        self.user_name = user_name
        self.database = database

    def run(self):
        def print_help():
            print('Поддерживаемые команды:')
            print('message - отправить сообщение. Кому и текст будет запрошены отдельно.')
            print('contacts - получить контакты')
            print('help - вывести подсказки по командам')
            print('exit - выход из программы')

        print_help()

        while True:
            command = input('Введите команду: ')
            if command == 'message':
                self.create_message()
            elif command == 'help':
                print_help()
            elif command == 'exit':
                with threading.RLock():
                    try:
                        functions.send_message(self.socket_name, functions.create_exit_message(self.user_name))
                    except Exception as e:
                        print(e)
                        pass
                    print('Завершение соединения.')
                    client_log.info('Завершение работы по команде пользователя.')
                time.sleep(0.5)
                break

            elif command == 'contacts':
                with thread_lock:
                    contacts_list = self.database.get_contacts()
                for contact in contacts_list:
                    print(contact)
            elif command == 'edit':
                self.edit_contacts()
            elif command == 'history':
                self.print_history()
            else:
                print('Команда не распознана, попробойте снова. '
                      'help - вывести поддерживаемые команды.')

    def create_message(self):
        to = input('Введите получателя сообщения: ')
        message = input('Введите сообщение для отправки: ')
        with threading.RLock():
            if not self.database.check_user(to):
                client_log.error(f'Попытка отправить сообщение '
                                 f'незарегистрированому получателю: {to}')
                return
        print("hello debug!")
        new_message = functions.message_common(self.user_name, message, to)
        client_log.debug(f'Сформирован словарь сообщения: {new_message}')
        print("hello debug 2!")
        with threading.RLock():
            self.database.save_message(self.user_name, to, message)
        print("hello debug!")
        with threading.RLock():
            try:
                functions.send_message(self.socket_name, new_message)
                client_log.debug(f'Отправлено сообщение для пользователя {to}')
            except OSError as err:
                if err.errno:
                    client_log.critical('Потеряно соединение с сервером.')
                    exit(1)
                else:
                    client_log.error('Не удалось передать сообщение. Таймаут соединения')

    def print_history(self):
        ask = input('Показать входящие сообщения - in, исходящие - out, все - просто Enter: ')
        with thread_lock:
            if ask == 'in':
                history_list = self.database.get_history(to_who=self.user_name)
                for message in history_list:
                    print(f'\nСообщение от пользователя: {message[0]} от {message[3]}:\n{message[2]}')
            elif ask == 'out':
                history_list = self.database.get_history(from_who=self.user_name)
                for message in history_list:
                    print(f'\nСообщение пользователю: {message[1]} от {message[3]}:\n{message[2]}')
            else:
                history_list = self.database.get_history()
                for message in history_list:
                    print(
                        f'\nСообщение от пользователя: {message[0]}, пользователю {message[1]} от {message[3]}\n{message[2]}')

    def edit_contacts(self):
        ans = input('Для удаления введите del, для добавления add: ')
        if ans == 'del':
            edit = input('Введите имя удаляемного контакта: ')
            with thread_lock:
                if self.database.check_contact(edit):
                    self.database.del_contact(edit)
                else:
                    client_log.error('Попытка удаления несуществующего контакта.')
        elif ans == 'add':
            edit = input('Введите имя создаваемого контакта: ')
            if self.database.check_user(edit):
                with thread_lock:
                    self.database.add_contact(edit)
                with thread_lock:
                    try:
                        add_contact(self.socket_name, self.user_name, edit)
                    except Exception as err:
                        client_log.error(f'Не удалось отправить информацию на сервер.{err}')


class ClientReceiver(threading.Thread, metaclass=ClientVerifier):
    def __init__(self, socket_name, user_name, database):
        super().__init__()
        self.socket_name = socket_name
        self.user_name = user_name
        self.database = database

    def run(self):
        while True:
            time.sleep(1)
            with thread_lock:
                try:
                    message = functions.get_message(self.socket_name)
                except ValueError:
                    client_log.error(f'Не удалось декодировать полученное сообщение.')
                except OSError as err:
                    if err.errno:
                        client_log.critical(f'Потеряно соединение с сервером.')
                        break
                except (OSError, ConnectionError, ConnectionAbortedError, ConnectionResetError, json.JSONDecodeError):
                    client_log.critical(f'Потеряно соединение с сервером.')
                    break

                else:
                    if "action" in message \
                            and message["action"] == "msg" \
                            and "time" in message \
                            and "to" in message \
                            and "from" in message \
                            and message["to"] == self.user_name \
                            and "message" in message:
                        print(f'\nПолучено сообщение от пользователя {message["from"]}:'
                              f'\n{message["message"]}')
                        with second_thread_lock:
                            try:
                                self.database.save_message(message["from"], self.user_name, message["message"])
                            except Exception as e:
                                print(e)
                                client_log.error('Ошибка взаимодействия с базой данных')
                        client_log.debug(f'Получено сообщение от пользователя {message["from"]}:'
                                         f'\n{message["message"]}')
                    else:
                        client_log.debug(f'Получено некорректное сообщение с сервера: {message}')


@log
def contacts_list_request(sock, name):
    client_log.debug(f'Запрос контакт листа для пользователя {name}')
    message = functions.get_contacts_message(name)
    client_log.debug(f'Сформирован запрос {message}')
    functions.send_message(sock, message)
    ans = functions.get_message(sock)
    client_log.debug(f'Получен ответ {ans}')
    if 'response' in ans and ans['response'] == '202':
        return ans['alert']
    else:
        print(ans['alert'])
        raise ValueError


@log
def add_contact(sock, username, contact):
    client_log.debug(f'Создание контакта {contact}')
    new_message = functions.add_contact_message(username, contact)
    functions.send_message(sock, new_message)
    ans = functions.get_message(sock)
    if 'response' in ans and ans['response'] == 200:
        pass
    else:
        raise Exception('Ошибка создания контакта')
    print('Удачное создание контакта.')


@log
def user_list_request(sock, username):
    client_log.debug(f'Запрос списка известных пользователей {username}')
    new_message = functions.get_contacts_list_message(username)
    functions.send_message(sock, new_message)
    ans = functions.get_message(sock)
    if 'response' in ans and ans['response'] == "202":
        return ans['alert']
    else:
        raise Exception('Ошибка получения контакта')


@log
def remove_contact(sock, username, contact):
    client_log.debug(f'Создание контакта {contact}')
    new_message = functions.del_contact_message(username, contact)
    functions.send_message(sock, new_message)
    ans = functions.get_message(sock)
    if 'response' in ans and ans['response'] == 200:
        pass
    else:
        raise Exception('Ошибка удаления клиента')
    print('Удачное удаление')


@log
def database_load(sock, database, username):
    try:
        users_list = user_list_request(sock, username)
    except Exception:
        client_log.error('Ошибка запроса списка известных пользователей.')
    else:
        database.add_users(users_list)

    try:
        contacts_list = contacts_list_request(sock, username)

    except Exception:
        client_log.error('Ошибка запроса списка контактов.')
    else:
        for contact in contacts_list:
            database.add_contact(contact)


def main():
    server_address, server_port, account_name = arg_pars()

    if not account_name:
        account_name = input('Введите имя пользователя: ')
    else:
        print(f'Клиентский модуль запущен с именем: {account_name}')
        client_log.info(f'Запущен клиент с параметрами: адрес сервера: {server_address} , порт: {server_port}, '
                        f'имя пользователя: {account_name}')

    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(1)
        client.connect((server_address, server_port))
        client.settimeout(None)
        message = functions.message_presence(account_name)
        client_log.debug(f'Сообщение на присутствие {message}')
        functions.send_message(client, message)
        presence_status = functions.presence_server(functions.get_message(client))
        client_log.debug(f'Ответ от сервера на сообщение на присутствие {presence_status}')
    except json.JSONDecodeError:
        client_log.error('Не удалось декодировать полученную Json строку.')
        sys.exit(1)
    except (ConnectionRefusedError, ConnectionError):
        client_log.error(f'Не удалось подключиться к серверу '
                         f'{server_address}:{server_port}, конечный компьютер отверг запрос на подключение.')
        exit(1)
    else:
        database = ClientStorage(account_name)
        database_load(client, database, account_name)
        receiver = ClientReceiver(client, account_name, database)
        receiver.daemon = True
        receiver.start()

        sender = ClientSender(client, account_name, database)
        sender.daemon = True
        sender.start()

        client_log.debug("Процессы запущены")

        while True:
            time.sleep(1)
            if receiver.is_alive() and sender.is_alive():
                continue
            break


if __name__ == '__main__':
    main()
