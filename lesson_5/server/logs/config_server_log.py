import sys
import os
import logging
import logging.handlers
sys.path.append('../')
from server.common.constants import LOGGING_LEVEL_SERVER, STREAM_LEVEL


server_formatter = logging.Formatter('%(asctime)s %(levelname)s %(filename)s %(message)s')
PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.log')

stream_handler = logging.StreamHandler(sys.stderr)
stream_handler.setFormatter(server_formatter)
stream_handler.setLevel(STREAM_LEVEL)
log_file = logging.handlers.TimedRotatingFileHandler(PATH, encoding='utf8', interval=1, when='D')
log_file.setFormatter(server_formatter)

logger = logging.getLogger('server')
logger.addHandler(stream_handler)
logger.addHandler(log_file)
logger.setLevel(LOGGING_LEVEL_SERVER)

if __name__ == '__main__':
    logger.critical('Критическая ошибка')
    logger.error('Ошибка')
    logger.info('Информационное сообщение')
    logger.debug('Отладочная информация')