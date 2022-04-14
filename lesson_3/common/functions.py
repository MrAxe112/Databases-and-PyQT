import time
import json
import common.constants as constants
import common.alerts
from common.decorators import log


@log
def send_message(sock, message):
    if not isinstance(message, dict):
        raise TypeError
    json_message = json.dumps(message)
    encoded_message = json_message.encode(constants.DECODING_FORMAT)
    sock.send(encoded_message)


@log
def get_message(client):
    encoded_response = client.recv(constants.MAX_LENGTH_BYTES)
    if isinstance(encoded_response, bytes):
        json_response = encoded_response.decode(constants.DECODING_FORMAT)
        response = json.loads(json_response)
        if isinstance(response, dict):
            return response
        raise ValueError
    raise ValueError


@log
def message_presence(user_name):
    client_presence = {
        "action": "presence",
        "time": time.time(),
        "type": "status",
        "user": {
            "account_name": user_name,
            "status": "Status report"
        }
    }
    return client_presence


@log
def message_common(user_name, text, send_to):
    chat_msg = {
        "action": "msg",
        "time": time.time(),
        "to": send_to,
        "from": user_name,
        "message": str(text),
    }
    return chat_msg


@log
def create_exit_message(account_name):
    return {
        "action": "exit",
        "time": time.time(),
        "from": account_name
    }


@log
def presence_server(message):
    if "response" in message:
        if message["response"] == 200:
            return '200 : OK'
        return f'400 : {message["error"]}'
    raise ValueError
