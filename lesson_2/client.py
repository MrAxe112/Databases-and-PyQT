import argparse
import dis
import socket
import sys
import json
import logging
import lesson_2.classes.common.functions as functions
import lesson_2.classes.common.constants as constants
import threading
from lesson_2.classes.common.decorators import log
import time

client_log = logging.getLogger('client')


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
        if 'accept' in methods or "listen" in methods :
            raise TypeError('В классе обнаружено использование запрещённого метода "accept" и "listen"')
        elif 'get_message' in methods or 'send_message' in methods:
            pass
        else:
            raise TypeError('Отсутствуют вызовы функций, работающих с сокетами.')
        super().__init__(class_name, class_parents, class_dict)


class ClientSender(threading.Thread):
    def __init__(self, socket_name, user_name):
        super().__init__()
        self.socket_name = socket_name
        self.user_name = user_name
        self.daemon = True

    @log
    def run(self):
        def print_help():
            """Функция выводящяя справку по использованию"""
            print('Поддерживаемые команды:')
            print('message - отправить сообщение. Кому и текст будет запрошены отдельно.')
            print('help - вывести подсказки по командам')
            print('exit - выход из программы')

        print_help()

        while True:
            command = input('Введите команду: ')
            if command == 'message':
                self.create_message(self.socket_name, self.user_name)
            elif command == 'help':
                print_help()
            elif command == 'exit':
                functions.send_message(self.socket_name, functions.create_exit_message(self.user_name))
                print('Завершение соединения.')
                client_log.info('Завершение работы по команде пользователя.')
                time.sleep(0.5)
                break
            else:
                print('Команда не распознана, попробойте снова. help - вывести поддерживаемые команды.')

    def create_message(self, socket_name, user_name):
        to_user = input('Введите получателя сообщения: ')
        user_message = input('Введите сообщение для отправки: ')
        message = functions.message_common(user_name, user_message, to_user)
        client_log.debug(f'Сформирован словарь сообщения: {message}')
        try:
            functions.send_message(socket_name, message)
            client_log.debug(f'Отправлено сообщение для пользователя {to_user}, {message}')
        except Exception:
            client_log.critical('Потеряно соединение с сервером.')
            sys.exit(1)


class ClientReceiver(threading.Thread):
    def __init__(self, socket_name, user_name):
        super().__init__()
        self.socket_name = socket_name
        self.user_name = user_name
        self.daemon = True

    @log
    def run(self):
        while True:
            try:
                message = functions.get_message(self.socket_name)
                if "action" in message \
                        and message["action"] == "msg" \
                        and "time" in message \
                        and "to" in message \
                        and "from" in message \
                        and message["to"] == self.user_name \
                        or message["to"] == "all" \
                        and "message" in message:
                    print(f'\nПолучено сообщение от пользователя {message["from"]}:'
                          f'\n{message["message"]}')
                    client_log.debug(f'Получено сообщение от пользователя {message["from"]}:'
                                     f'\n{message["message"]}')
                else:
                    client_log.debug(f'Получено некорректное сообщение с сервера: {message}')
            except (OSError, ConnectionError, ConnectionAbortedError,
                    ConnectionResetError, json.JSONDecodeError):
                client_log.critical(f'Потеряно соединение с сервером.')
                break


class Client(metaclass=ClientVerifier):
    def __init__(self, server_address, server_port, account_name):
        self.server_address = server_address
        self.server_port = server_port
        self.account_name = account_name

    def loop(self):
        client_log.info(f'Запущен клиент пользователя {self.account_name} с парамертами: '
                        f'адрес сервера: {self.server_address}, порт: {self.server_port}')
        print(f'Запущен клиент пользователя {self.account_name}')
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect((self.server_address, self.server_port))
            message = functions.message_presence(self.account_name)
            client_log.debug(f'Сообщение на присутствие {message}')
            functions.send_message(client, message)
            client_log.debug(f'Ответ от сервера на сообщение на присутствие '
                             f'{functions.presence_server(functions.get_message(client))}')
        except json.JSONDecodeError:
            client_log.error('Не удалось декодировать полученную Json строку.')
            sys.exit(1)
        except Exception as err:
            client_log.error(f'При работе возникла ошибка: {err}.')
            print(err)
            sys.exit(1)
        else:
            receive = ClientReceiver(client, self.account_name)
            receive.start()
            send = ClientSender(client, self.account_name)
            send.start()
            client_log.debug("Процессы запущены")

            while True:
                time.sleep(1)
                if receive.is_alive() and send.is_alive():
                    continue
                break


def main():
    server_address, server_port, account_name = arg_pars()
    client = Client(server_address, server_port, account_name)
    client.loop()


if __name__ == '__main__':
    main()
