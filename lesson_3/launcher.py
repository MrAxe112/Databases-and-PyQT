import subprocess

PROCESS = []

while True:
    ACTION = input('Выберите действие: q - выход, s - запустить сервер и клиенты, x - закрыть все окна: ')

    if ACTION == 'q':
        while PROCESS:
            VICTIM = PROCESS.pop()
            VICTIM.kill()
        break
    elif ACTION == 's':
        # PROCESS.append(subprocess.Popen('python server.py',
        #                                 creationflags=subprocess.CREATE_NEW_CONSOLE))
        for i in range(5):
            PROCESS.append(subprocess.Popen(f'python client.py -n guest{i+1}',
                                            creationflags=subprocess.CREATE_NEW_CONSOLE))
    elif ACTION == 'x':
        while PROCESS:
            VICTIM = PROCESS.pop()
            VICTIM.kill()

# если запускать сервер по этом скрипту все клиенты и сервер сразу умирают, пока сервер необходимо запускать отдельно
