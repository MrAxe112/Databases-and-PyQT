if __name__ == '__main__':
    import subprocess
    import time

    PROCESS = []

    while True:
        ACTION = input('Выберите действие: q - выход, s - запустить клиенты, x - закрыть все окна: ')

        if ACTION == 'q':
            while PROCESS:
                VICTIM = PROCESS.pop()
                VICTIM.kill()
            break
        elif ACTION == 's':
            for i in range(5):
                PROCESS.append(subprocess.Popen(f'python client_run.py -n guest{i + 1} -p 123456',
                                                creationflags=subprocess.CREATE_NEW_CONSOLE))
                time.sleep(5)
        elif ACTION == 'x':
            while PROCESS:
                VICTIM = PROCESS.pop()
                VICTIM.kill()
