import platform
import subprocess
import threading
from ipaddress import ip_address

result = {'Reachable': "", "Unreachable": ""}


def is_ip(value):
    try:
        ip = ip_address(value)
    except ValueError:
        raise Exception('Некорректный ip адрес')
    return ip


def host_ping(hosts_list, get_list=False):
    def ping(ip_add, result, get_list):
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        response = subprocess.Popen(["ping", param, '1', '-w', '1', str(ip_add)], stdout=subprocess.PIPE)
        if response.wait() == 0:
            result["Reachable"] += f"{ip}\n"
            res = f"{ip_add} - Узел доступен"
            if not get_list:
                print(res)
            return res
        else:
            result["Unreachable"] += f"{ip}\n"
            res = f"{str(ip_add)} - Узел недоступен"
            if not get_list:
                print(res)
            return res
    threads = []
    for host in hosts_list:
        try:
            ip = is_ip(host)
        except Exception:
            ip = host

        thread = threading.Thread(target=ping, args=(ip, result, get_list), daemon=True)
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    if get_list:
        return result


if __name__ == '__main__':
    hosts_list = ['192.168.8.1', '8.8.8.8', 'yandex.ru', 'google.com',
                  '0.0.0.1', '0.0.0.2', '0.0.0.3', '0.0.0.4', '0.0.0.5',
                  '0.0.0.6', '0.0.0.7', '0.0.0.8', '0.0.0.9', '0.0.1.0']
    host_ping(hosts_list)


