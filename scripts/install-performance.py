#!/usr/bin/env python3
"""Verify an offline release, install its code, then configure the existing vhosts."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import socket
import subprocess
import sys

ROOT = Path('/opt/legacy-stack/sites/sweb/site.urbaso.ru/public_html')
REQUIRED_FILES = ('release.bundle', 'install-performance-release.py', 'configure-performance.py')


def validate_environment(directory):
    if os.geteuid() != 0 or socket.gethostname() != 'urbaserge3-vps-1':
        raise RuntimeError('Запустите установку от root на сервере urbaserge3-vps-1.')
    if directory == ROOT.resolve() or ROOT.resolve() in directory.parents:
        raise RuntimeError('Распакуйте релиз вне публичного каталога сайта, например в /root.')


def read_release(directory):
    manifest = directory / 'release.json'
    if manifest.is_symlink() or not manifest.is_file():
        raise RuntimeError('Отсутствует обычный файл release.json.')
    release = json.loads(manifest.read_text())
    for key in ('targetCommit', 'baselineCommit'):
        if not isinstance(release.get(key), str) or not re.fullmatch(r'[0-9a-f]{40}', release[key]):
            raise RuntimeError('Некорректный полный SHA: ' + key)
    hashes = release.get('filesSha256')
    if not isinstance(hashes, dict) or not all(name in hashes for name in REQUIRED_FILES):
        raise RuntimeError('В release.json не хватает контрольных сумм файлов релиза.')
    for name, expected in hashes.items():
        if not isinstance(name, str) or Path(name).name != name or name in ('.', '..'):
            raise RuntimeError('Недопустимый путь в filesSha256.')
        if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
            raise RuntimeError('Некорректная SHA256: ' + name)
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('Файл отсутствует или является ссылкой: ' + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Контрольная сумма не совпадает: ' + name + '. Ничего не установлено.')
    return release


def run_step(command, log, result, prefix):
    command = [str(value) for value in command]
    print('\nЗапуск:', shlex.join(command), flush=True)
    log.write('\n$ ' + shlex.join(command) + '\n')
    log.flush()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, bufsize=1, start_new_session=True)

    def relay():
        for line in process.stdout:
            print(line, end='', flush=True)
            log.write(line)
            log.flush()
            if line.startswith('Резервная копия: '):
                result[prefix + 'Backup'] = line.partition(': ')[2].strip()
            elif line.startswith('Откат nginx: '):
                result['nginxRollback'] = line.partition(': ')[2].strip()
            elif line.startswith('Откат: '):
                result['codeRollback'] = line.partition(': ')[2].strip()

    try:
        relay()
        return process.wait()
    except KeyboardInterrupt:
        print('\nОстановка: ожидаю завершения защитного отката текущего шага.', flush=True)
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
        relay()
        process.wait()
        raise
    finally:
        process.stdout.close()


def print_recovery(result, directory, target):
    if result.get('nginxRollback') or result.get('codeRollback'):
        print('\nКоманды полного отката, в указанном порядке:')
        if result.get('nginxRollback'):
            print(result['nginxRollback'])
        if result.get('codeRollback'):
            print(result['codeRollback'])
    if result['status'] == 'code_installed_nginx_failed':
        print('\nПосле устранения причины повторить только настройку Nginx:')
        print(shlex.join([sys.executable, str(directory / 'configure-performance.py'), target]))


def main():
    if len(sys.argv) != 1:
        raise RuntimeError('Запуск без аргументов: python3 /root/папка-релиза/install.py')
    directory = Path(__file__).resolve().parent
    validate_environment(directory)
    release = read_release(directory)
    target, baseline = release['targetCommit'], release['baselineCommit']
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    log_path = directory / ('installation-' + stamp + '.log')
    result_path = directory / ('installation-' + stamp + '.json')
    result = dict(targetCommit=target, baselineCommit=baseline, status='starting', log=str(log_path))
    exit_code = 1
    print('Контрольные суммы проверены. Релиз:', target, flush=True)
    print('Лог установки:', log_path, flush=True)
    try:
        with log_path.open('x') as log:
            os.chmod(log_path, 0o600)
            result['status'] = 'code_failed'
            code_status = run_step([sys.executable, directory / 'install-performance-release.py', 'install',
                                   directory / 'release.bundle', target, baseline], log, result, 'code')
            if code_status:
                print('\nУстановка кода не завершена. Nginx не изменялся. Проверьте вывод выше.')
            else:
                result['status'] = 'code_installed_nginx_failed'
                nginx_status = run_step([sys.executable, directory / 'configure-performance.py', target],
                                        log, result, 'nginx')
                if nginx_status:
                    print('\nКод установлен. Настройка Nginx не завершена; состояние и попытка восстановления указаны выше.')
                    print('Код автоматически не откатывался. Сохранены отдельные команды восстановления.')
                else:
                    result['status'] = 'completed'
                    exit_code = 0
                    print('\nКод, сжатие и кеширование установлены; серверные проверки пройдены.')
                    print('Указатели веток Git сохранены, текущий checkout находится в detached HEAD.')
    except KeyboardInterrupt:
        print('\nУстановка прервана. Проверьте результат защитного отката выше.')
    finally:
        raw = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        descriptor = os.open(result_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as saved:
            saved.write(raw)
        print_recovery(result, directory, target)
        print('\nСведения об установке:', result_path)
    return exit_code


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        sys.exit(main())
    except (Exception, KeyboardInterrupt) as error:
        print('ОСТАНОВКА: ' + str(error or 'операция прервана'), file=sys.stderr)
        sys.exit(1)
