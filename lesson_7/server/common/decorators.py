import socket
import sys
import logging
import traceback


def log(func):
    """Декоратор для логирования работы функЦий."""
    def decorations(*args, **kwargs):
        logger_name = 'server' if 'server.py' in sys.argv[0] else 'client'
        logger = logging.getLogger(logger_name)

        f = func(*args, **kwargs)
        module_name = sys._getframe().f_back.f_code.co_filename.split('\\')[-1]
        func_name = traceback.format_stack()[0].strip().split()[-1]

        logger.debug(
            f'Функция "{func.__name__}" вызвана из функции "{func_name}".модуля "{module_name}";\n'
            f'c параметрами {args}, {kwargs}\n')
        return f
    return decorations


def login_required(func):
    """Декоратор позволяющий проверить, авторизован ли клиент на сервере."""

    def checker(*args, **kwargs):
        from server.common.server_class import Server
        if isinstance(args[1], Server):

            found = False
            for arg in args:
                if isinstance(arg, socket.socket):
                    for client in args[1].name:
                        if args[1].name[client] == arg:
                            found = True

            for arg in args:
                if isinstance(arg, dict):
                    if 'action' in arg and arg['action'] == 'presence':
                        found = True
            if not found:
                raise TypeError
        return func(*args, **kwargs)
    return checker
