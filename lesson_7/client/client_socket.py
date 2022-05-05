import binascii
import hashlib
import hmac
import socket
import sys
import time
import logging
import json
import threading
from PyQt5.QtCore import pyqtSignal, QObject
import client.common.alerts as alerts

sys.path.append('../')
from client.common.constants import *
from client.common.functions import *
from client.common.alerts import ServerError

client_log = logging.getLogger('client_socket')
socket_lock = threading.RLock()


class ClientTransport(threading.Thread, QObject):
    """Класс реализующий подсистему клиентского модуля для связи с сервером."""
    new_message = pyqtSignal(str)
    connection_lost = pyqtSignal()
    message_205 = pyqtSignal()

    def __init__(self, port, ip_address, database, username, password, keys):
        threading.Thread.__init__(self)
        QObject.__init__(self)
        self.database = database
        self.username = username
        self.password = password
        self.keys = keys
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
        """Метод отвечающий за устанновку связи с сервером."""
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

        _passwd_bytes = self.password.encode('utf-8')
        _salt = self.username.lower().encode('utf-8')
        _passwd_hash = hashlib.pbkdf2_hmac('sha512', _passwd_bytes, _salt, 10000)
        _passwd_hash_string = binascii.hexlify(_passwd_hash)
        _pubkey = self.keys.publickey().export_key().decode('utf-8')
        with socket_lock:
            _presence = message_presence(self.username, _pubkey)
            try:
                send_message(self.transport, _presence)
                answer = get_message(self.transport)
                if 'response' in answer:
                    if answer['response'] == "400":
                        raise ServerError(answer["error"])
                    elif answer['response'] == "511":
                        ans_data = answer['bin']
                        hash = hmac.new(_passwd_hash_string, ans_data.encode('utf-8'), 'MD5')
                        digest = hash.digest()
                        my_ans = alerts.alert_511
                        my_ans['bin'] = binascii.b2a_base64(digest).decode('utf-8')
                        send_message(self.transport, my_ans)
                        self.process_server_ans(get_message(self.transport))
            except (OSError, json.JSONDecodeError):
                client_log.critical('Потеряно соединение с сервером!')
                raise ServerError('Потеряно соединение с сервером!')

            client_log.info('Соединение с сервером успешно установлено.')

    def process_server_ans(self, message):
        """
        Метод для обработки полученых сообщений от сервера.
        """
        client_log.debug(f'Разбор сообщения от сервера: {message}')
        if 'response' in message:
            if message['response'] == "400":
                raise ServerError(f'{message["error"]}')
            elif message['response'] == "200":
                return
            elif message['response'] == "205":
                self.user_list_update()
                self.contacts_list_update()
                self.message_205.emit()
            else:
                client_log.debug(f'Принят неизвестный код подтверждения {message["response"]}')

        elif "action" in message \
                and message["action"] == "msg" \
                and "time" in message \
                and "to" in message \
                and "from" in message \
                and message["to"] == self.username \
                and "message" in message:
            client_log.debug(f'Получено сообщение от пользователя {message["from"]}: {message["message"]}')
            self.database.save_message(message["from"], 'in', message["message"])
            self.new_message.emit(message["from"])

    def contacts_list_update(self):
        """Метод для обновления списка контактов в базе данных."""
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
        """Метод обновляющий с сервера список пользователей."""
        client_log.debug(f'Запрос списка известных пользователей {self.username}')
        with socket_lock:
            send_message(self.transport, get_contacts_list_message(self.username))
            ans = get_message(self.transport)
        if 'response' in ans and ans['response'] == "202":
            self.database.add_users(ans['alert'])
        else:
            client_log.error('Не удалось обновить список известных пользователей.')

    def key_request(self, user):
        """Метод для запроса публичный ключа пользователя с сервера."""
        client_log.debug(f'Запрос публичного ключа для {user}')
        req = {
            "action": "public_key_request",
            "time": time.time(),
            "account_name": user
        }
        with socket_lock:
            send_message(self.transport, req)
            ans = get_message(self.transport)
        if 'response' in ans and ans['response'] == 511:
            return ans["bin"]
        else:
            client_log.error(f'Не удалось получить ключ собеседника {user}.')

    def add_contact(self, contact):
        """Метод сохранения контакта пользователя на сервере."""
        client_log.debug(f'Создание контакта {contact}')
        req = add_contact_message(self.username, contact)
        with socket_lock:
            send_message(self.transport, req)
            self.process_server_ans(get_message(self.transport))

    def remove_contact(self, contact):
        """Метод удаления контакта пользователя на сервере."""
        client_log.debug(f'Удаление контакта {contact}')
        req = del_contact_message(self.username, contact)
        with socket_lock:
            send_message(self.transport, req)
            self.process_server_ans(get_message(self.transport))

    def transport_shutdown(self):
        """Метод завершения работы. Отправляет завершающее сообщение на сервер"""
        self.running = False
        with socket_lock:
            try:
                send_message(self.transport, create_exit_message(self.username))
            except OSError:
                pass
        client_log.debug('Транспорт завершает работу.')
        time.sleep(0.5)

    def client_send_message(self, to, message):
        """Метод отправки сообщения внешнему пользователю через сервер."""
        msg = message_common(self.username, message, to)
        client_log.debug(f'Сформирован словарь сообщения: {msg}.')

        with socket_lock:
            send_message(self.transport, msg)
            self.process_server_ans(get_message(self.transport))
            client_log.info(f'Отправлено сообщение для пользователя {to}.')

    def run(self):
        """
        Метод цикл обработки созданых и отправленых сообщений.
        """
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
                    client_log.debug(f'Принято сообщение с сервера: {message}.')
                    self.process_server_ans(message)
                finally:
                    self.transport.settimeout(5)
