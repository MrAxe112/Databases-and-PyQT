import argparse
import socket
import sys
import json
import logging
import time
import threading
from PyQt5.QtWidgets import QApplication
import client.common.functions as functions
import client.common.constants as constants
from client.common.alerts import ServerError
from client.common.decorators import log
from client.client_database import ClientStorage
from client.start_dialog import UserNameDialog
from client.main_window import ClientMainWindow
from client.client_socket import ClientTransport

client_log = logging.getLogger('client')
thread_lock = threading.RLock()
second_thread_lock = threading.RLock()


@log
def arg_pars():
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', default=constants.DEFAULT_ADDRESS, nargs='?')
    parser.add_argument('-p', default=constants.DEFAULT_PORT, type=int, nargs='?')
    parser.add_argument('-n', '--name', nargs='?')
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


def main():
    server_address, server_port, client_name = arg_pars()
    client_app = QApplication(sys.argv)

    if not client_name:
        start_dialog = UserNameDialog()
        client_app.exec_()
        if start_dialog.ok_pressed:
            client_name = start_dialog.client_name.text()
            del start_dialog
        else:
            exit(0)

    client_log.info(
        f'Запущен клиент с парамертами: адрес сервера: {server_address} , '
        f'порт: {server_port}, имя пользователя: {client_name}')

    database = ClientStorage(client_name)

    try:
        client = ClientTransport(server_port, server_address, database, client_name)
    except ServerError as error:
        print(error.text)
        exit(1)

    client.daemon = True
    client.start()

    main_window = ClientMainWindow(database, client)
    main_window.make_connection(client)
    main_window.setWindowTitle(f'Программа по обмену сообшениями ver. {constants.VERSION} - {client_name}')
    client_app.exec_()

    client.transport_shutdown()
    client.join()


if __name__ == '__main__':
    main()
