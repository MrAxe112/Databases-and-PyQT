import sys
import logging
import traceback


def log(func):
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

