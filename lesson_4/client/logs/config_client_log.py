import sys
import os
import logging

sys.path.append('../')
from common.constants import LOGGING_LEVEL_CLIENT, STREAM_LEVEL

client_formatter = logging.Formatter('%(asctime)s %(levelname)s %(filename)s %(message)s')
PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'client.log')

stream_handler = logging.StreamHandler(sys.stderr)
stream_handler.setFormatter(client_formatter)
stream_handler.setLevel(STREAM_LEVEL)
log_file = logging.FileHandler(PATH, encoding='utf8')
log_file.setFormatter(client_formatter)

logger = logging.getLogger('client')
logger.addHandler(stream_handler)
logger.addHandler(log_file)
logger.setLevel(LOGGING_LEVEL_CLIENT)

if __name__ == '__main__':
    logger.critical('Критическая ошибка')
    logger.error('Ошибка')
    logger.info('Информационное сообщение')
    logger.debug('Отладочная информация')
