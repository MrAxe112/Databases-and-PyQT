import socket
import sys
import time
import logging
import json
import threading
from PyQt5.QtCore import pyqtSignal, QObject
sys.path.append('../')
from client.common.constants import *
from client.common.functions import *
from client.common.alerts import ServerError

client_log = logging.getLogger('client_socket')
socket_lock = threading.RLock()


class ClientTransport(threading.Thread, QObject):
    new_message = pyqtSignal(str)
    connection_lost = pyqtSignal()

    def __init__(self, port, ip_address, database, username):
        threading.Thread.__init__(self)
        QObject.__init__(self)
        self.database = database
        self.username = username
        self.client_socket = None
        self.connection_init(port, ip_address)
        try:
            self.user_list_update()
            self.contacts_list_update()
        except OSError as err:
            if err.errno:
                client_log.critical(f'Потеряно соединение с сервером.')
                raise ServerError('Потеряно соединение с сервером!')
            client_log.error('Timeout соединения при обновлении списков пользователей.')
        except json.JSONDecodeError:
            client_log.critical(f'Потеряно соединение с сервером.')
            raise ServerError('Потеряно соединение с сервером!')
        self.running = True

    def connection_init(self, port, ip):
        self.transport = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.transport.settimeout(5)

        connected = False
        for i in range(5):
            client_log.info(f'Попытка подключения №{i + 1}')
            try:
                self.transport.connect((ip, port))
            except (OSError, ConnectionRefusedError):
                pass
            else:
                connected = True
                break
            time.sleep(1)

        if not connected:
            client_log.critical('Не удалось установить соединение с сервером')
            raise ServerError('Не удалось установить соединение с сервером')

        client_log.debug('Установлено соединение с сервером')

        try:
            with socket_lock:
                send_message(self.transport, message_presence(self.username))
                self.process_server_ans(get_message(self.transport))
        except (OSError, json.JSONDecodeError):
            client_log.critical('Потеряно соединение с сервером!')
            raise ServerError('Потеряно соединение с сервером!')

        client_log.info('Соединение с сервером успешно установлено.')

    def process_server_ans(self, message):
        client_log.debug(f'Разбор сообщения от сервера: {message}')

        if 'response' in message:
            if message['response'] == "200":
                return
            elif message['response'] == "400":
                raise ServerError(f'{message["error"]}')
            else:
                client_log.debug(f'Принят неизвестный код подтверждения {message["response"]}')

        elif "action" in message \
                and message["action"] == "msg" \
                and "time" in message \
                and "to" in message \
                and "from" in message \
                and message["to"] == self.username \
                and "message" in message:
            client_log.debug(f'Получено сообщение от пользователя {message["from"]}:'
                         f'{message["message"]}')
            self.database.save_message(message["from"], 'in', message["message"])
            self.new_message.emit(message["from"])

    def contacts_list_update(self):
        client_log.debug(f'Запрос контакт листа для пользователя {self.name}')
        req = get_contacts_message(self.username)
        client_log.debug(f'Сформирован запрос {get_contacts_message(self.username)}')
        with socket_lock:
            send_message(self.transport, req)
            ans = get_message(self.transport)
        client_log.debug(f'Получен ответ {ans}')
        if 'response' in ans and ans['response'] == "202":
            for contact in ans['alert']:
                self.database.add_contact(contact)
        else:
            client_log.error('Не удалось обновить список контактов.')

    def user_list_update(self):
        client_log.debug(f'Запрос списка известных пользователей {self.username}')
        with socket_lock:
            send_message(self.transport, get_contacts_list_message(self.username))
            ans = get_message(self.transport)
        if 'response' in ans and ans['response'] == "202":
            self.database.add_users(ans['alert'])
        else:
            client_log.error('Не удалось обновить список известных пользователей.')

    def add_contact(self, contact):
        client_log.debug(f'Создание контакта {contact}')
        req = add_contact_message(self.username, contact)
        with socket_lock:
            send_message(self.transport, req)
            self.process_server_ans(get_message(self.transport))

    def remove_contact(self, contact):
        client_log.debug(f'Удаление контакта {contact}')
        req = del_contact_message(self.username, contact)
        with socket_lock:
            send_message(self.transport, req)
            self.process_server_ans(get_message(self.transport))

    def transport_shutdown(self):
        self.running = False
        with socket_lock:
            try:
                send_message(self.transport, create_exit_message(self.username))
            except OSError:
                pass
        client_log.debug('Транспорт завершает работу.')
        time.sleep(0.5)

    def client_send_message(self, to, message):
        msg = message_common(self.username, message, to)
        client_log.debug(f'Сформирован словарь сообщения: {msg}')

        with socket_lock:
            send_message(self.transport, msg)
            self.process_server_ans(get_message(self.transport))
            client_log.info(f'Отправлено сообщение для пользователя {to}')

    def run(self):
        client_log.debug('Запущен процесс - приёмник сообщений с сервера.')
        while self.running:
            time.sleep(1)
            with socket_lock:
                try:
                    self.transport.settimeout(0.5)
                    message = get_message(self.transport)
                except OSError as err:
                    if err.errno:
                        client_log.critical(f'Потеряно соединение с сервером.')
                        self.running = False
                        self.connection_lost.emit()
                except (ConnectionError, ConnectionAbortedError,
                        ConnectionResetError, json.JSONDecodeError, TypeError):
                    client_log.debug(f'Потеряно соединение с сервером.')
                    self.running = False
                    self.connection_lost.emit()
                else:
                    client_log.debug(f'Принято сообщение с сервера: {message}')
                    self.process_server_ans(message)
                finally:
                    self.transport.settimeout(5)
