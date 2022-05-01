import dis
import socket
import select
import sys
import logging
import logs.config_server_log
import argparse
import common.functions as functions
import common.constants as constants

server_log = logging.getLogger('server')


class NonNegativePort:
    def __set__(self, instance, value):
        if not 0 < value < 65536:
            raise ValueError("Значение порта должно быть целым неотрицательным числом")
        instance.__dict__[self.port_number] = value

    def __set_name__(self, owner, port_number):
        self.port_number = port_number


class ServerVerifier(type):
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
        if 'connect' in methods:
            raise TypeError('В классе обнаружено использование запрещённого метода "accept" и "listen"')
        elif 'get_message' in methods or 'send_message' in methods:
            pass
        else:
            raise TypeError('Отсутствуют вызовы функций, работающих с сокетами.')
        super().__init__(class_name, class_parents, class_dict)


class Server(metaclass=ServerVerifier):
    listen_port = NonNegativePort()

    def __init__(self, listen_address, listen_port):
        self.listen_address = listen_address
        self.listen_port = listen_port
        self.messages = []
        self.clients = []
        self.clients_names = dict()

    def message_type_separation(self, client, message_obj, messages_list):
        if "action" in message_obj \
                and message_obj["action"] == "presence":
            presence = functions.presence_message_validation(message_obj)
            functions.send_message(client, presence)
            return

        elif "action" in message_obj \
                and message_obj["action"] == "msg" \
                and "time" in message_obj \
                and "message" in message_obj:
            messages_list.append((message_obj["from"], message_obj["message"], message_obj["to"]))
            return
        elif "action" in message_obj \
                and message_obj["action"] == "exit" \
                and "from" in message_obj:
            self.clients.remove(self.clients_names["from"])
            self.clients_names["from"].close()
            del self.clients_names["from"]
            return

        else:
            functions.send_message(client, {
                "response": 400,
                "error": 'Bad Request'
            })
            return

    def init(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((self.listen_address, self.listen_port))
        server.settimeout(1)

        self.socket = server
        print("Запушен сервер!")
        server_log.info(f'Запушен сервер. Адрес: {self.listen_address}. Порт: {self.listen_port}')
        self.socket.listen(constants.MAX_CLIENTS)

    def loop(self):

        self.init()

        while True:
            try:
                client, address = self.socket.accept()
            except OSError:
                pass
            else:

                server_log.info(f'Установлено соедение с ПК {address}')
                self.clients.append(client)
            recv_data_list = []
            send_data_list = []
            try:
                if self.clients:
                    recv_data_list, send_data_list, _ = select.select(self.clients, self.clients, [], 0)
            except OSError:
                pass
            if recv_data_list:
                for client_with_message in recv_data_list:
                    try:
                        a = functions.get_message(client_with_message)
                        self.message_type_separation(client_with_message, a, self.messages)
                    except Exception as err:
                        server_log.info(f'Клиент {client_with_message.getpeername()} отключился от сервера. '
                                        f'Ошибка: {err}.')
                        self.clients.remove(client_with_message)

            if self.messages and send_data_list:
                print(self.messages)
                message = functions.message_common(self.messages[0][0], self.messages[0][1], self.messages[0][2])
                del self.messages[0]
                for waiting_client in send_data_list:
                    try:
                        functions.send_message(waiting_client, message)
                    except Exception as err:
                        server_log.info(f'Клиент {waiting_client.getpeername()} отключился от сервера.{err}')
                        waiting_client.close()
                        self.clients.remove(waiting_client)


def arg_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', default=constants.DEFAULT_PORT, type=int, nargs='?')
    parser.add_argument('-a', default='', nargs='?')
    namespace = parser.parse_args(sys.argv[1:])
    listen_addr = namespace.a
    listen_port = namespace.p
    return listen_addr, listen_port


def main():
    listen_addr, listen_port = arg_parser()
    server_run = Server(listen_addr, listen_port)
    server_run.loop()


if __name__ == '__main__':
    main()
