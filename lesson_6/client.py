import argparse
import os
import socket
import sys
import json
import logging
import time
import threading
from PyQt5.QtWidgets import QApplication, QMessageBox
import client.common.functions as functions
import client.common.constants as constants
from client.common.alerts import ServerError
from client.common.decorators import log
from client.client_database import ClientStorage
from client.start_dialog import UserNameDialog
from client.main_window import ClientMainWindow
from client.client_socket import ClientTransport
from Cryptodome.PublicKey import RSA

client_log = logging.getLogger('client')
thread_lock = threading.RLock()
second_thread_lock = threading.RLock()


@log
def arg_pars():
    parser = argparse.ArgumentParser()
    parser.add_argument('-add', default=constants.DEFAULT_ADDRESS, nargs='?')
    parser.add_argument('-port', default=constants.DEFAULT_PORT, type=int, nargs='?')
    parser.add_argument('-n', '--name', default=None, nargs='?')
    parser.add_argument('-p', '--password', default='', nargs='?')
    namespace = parser.parse_args(sys.argv[1:])
    pars_server_address = namespace.add
    pars_server_port = namespace.port
    pars_client_name = namespace.name
    pars_client_passwd = namespace.password

    if not 1023 < pars_server_port < 65536:
        client_log.critical(
            f'Попытка запуска клиента с неподходящим номером порта: {pars_server_port}. '
            f'Допустимы адреса с 1024 до 65535. Клиент завершается.')
        sys.exit(1)
    return pars_server_address, pars_server_port, pars_client_name, pars_client_passwd


def main():
    server_address, server_port, client_name, client_password = arg_pars()

    client_app = QApplication(sys.argv)
    start_dialog = UserNameDialog()

    if not client_name or not client_password:
        client_app.exec_()
        if start_dialog.ok_pressed:
            client_name = start_dialog.client_name.text()
            client_password = start_dialog.client_passwd.text()
        else:
            exit(0)

    client_log.info(
        f'Запущен клиент с парамертами: адрес сервера: {server_address} , '
        f'порт: {server_port}, имя пользователя: {client_name}')
    
    dir_path = os.path.dirname(os.path.realpath(__file__))
    key_file = os.path.join(dir_path, f'{client_name}.key')
    if not os.path.exists(key_file):
        keys = RSA.generate(2048, os.urandom)
        with open(key_file, 'wb') as key:
            key.write(keys.export_key())
    else:
        with open(key_file, 'rb') as key:
            keys = RSA.import_key(key.read())

    database = ClientStorage(client_name)

    try:
        client = ClientTransport(server_port, server_address, database, client_name, client_password, keys)
    except ServerError as error:
        message = QMessageBox()
        message.critical(start_dialog, 'Ошибка сервера', error.text)
        exit(1)

    client.daemon = True
    client.start()

    del start_dialog

    main_window = ClientMainWindow(database, client)
    main_window.make_connection(client)
    main_window.setWindowTitle(f'Программа по обмену сообшениями ver. {constants.VERSION} - {client_name}')
    client_app.exec_()

    client.transport_shutdown()
    client.join()


if __name__ == '__main__':
    main()
