import binascii
import dis
import hmac
import os
import socket
import threading
import server.common.server_class as sc
from json import JSONDecodeError

import select
import sys
import logging
import server.logs.config_server_log
import argparse
import server.common.functions as functions
import server.common.constants as constants
import server.common.alerts
import server.common.sevrer_db
import configparser
from PyQt5.QtWidgets import QMessageBox
import server.common.server_gui as gui
from server.common.decorators import login_required
# from server.common.core import MessageProcessor
# from server.database import ServerStorage
from server.common.main_window import MainWindow
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt


server_log = logging.getLogger('server')
new_connection_flag = False


def main():
    config = configparser.ConfigParser()
    dir_path = os.path.dirname(os.path.realpath(__file__))
    config.read(f"{dir_path}/server/{'server.ini'}")
    listen_addr, listen_port = sc.arg_parser(config['SETTINGS']['Default_port'], config['SETTINGS']['Listen_Address'])
    database = server.common.sevrer_db.ServerStorage(os.path.join(config['SETTINGS']['Database_path'],
                                                                  config['SETTINGS']['Database_file']))
    server_run = sc.Server(listen_addr, listen_port, database)
    server_run.daemon = True
    server_run.start()

    server_app = QApplication(sys.argv)
    server_app.setAttribute(Qt.AA_DisableWindowContextHelpButton)
    main_window = MainWindow(database, server_run, config)

    server_app.exec_()


if __name__ == '__main__':
    main()
