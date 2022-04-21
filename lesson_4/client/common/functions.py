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
    presence_msg = {
        "action": "presence",
        "time": time.time(),
        "type": "status",
        "user": {
            "account_name": user_name,
            "status": "Status report"
        }
    }
    return presence_msg


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
    exit_msg = {
        "action": "exit",
        "time": time.time(),
        "user": account_name
    }
    return exit_msg


@log
def get_contacts_message(account_name):
    get_contacts_msg = {
        "action": "get_contacts",
        "time": time.time(),
        "user": account_name
    }
    return get_contacts_msg


@log
def add_contact_message(account_name, added_contact):
    add_contact_msg = {
        "action": "add_contact",
        "time": time.time(),
        'user': account_name,
        'account_name': added_contact
    }
    return add_contact_msg


@log
def del_contact_message(username,contact):
    del_contact_msg = {
        "action": "del_contacts",
        "time": time.time(),
        'user': username,
        'account_name': contact
    }
    return del_contact_msg

@log
def get_contacts_list_message(username):
    get_contacts_list_msg = {
        "action": "users_request",
        "time": time.time(),
        'account_name': username
    }
    return get_contacts_list_msg


@log
def presence_server(message):
    if "response" in message:
        if message["response"] == 200:
            return '200 : OK'
    else:
        return f'400 : {message["error"]}'
    raise ValueError
