#!/usr/bin/env bash
# Restore only nginx files recorded by cutover-domains.sh. Keep all site data and certificates.
set -Eeuo pipefail
exec python3 - "$@" <<'PY'
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

NAMES = {'urbaso.ru', 'site.urbaso.ru', 'sitetops.ru', 'disiner.ru', 'prodvizheniyesaytov.ru'}
AVAILABLE = Path('/etc/nginx/sites-available')
ENABLED = Path('/etc/nginx/sites-enabled')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fail(message):
    raise RuntimeError(message)


def atomic_write(path, data, entry):
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, entry['mode'])
        os.chown(temporary, entry['uid'], entry['gid'])
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    if os.geteuid() != 0 or len(sys.argv) != 2:
        fail('Запуск от root: rollback-domains.sh КАТАЛОГ_РЕЗЕРВНОЙ_КОПИИ')
    backup = Path(sys.argv[1]).resolve(strict=True)
    if backup.parent != Path('/root/backups/site.urbaso.ru'):
        fail('Неожиданный каталог резервной копии')
    lock = open('/run/lock/site-urbaso-domain-cutover.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    metadata = json.loads((backup / 'cutover.json').read_text())
    entries = metadata['entries']
    if metadata.get('version') != 1 or {e['name'] for e in entries} != NAMES or len(entries) != len(NAMES):
        fail('Неизвестный формат резервной копии')
    # Validate every destination and source before restoring the first file.
    for entry in entries:
        name = entry['name']
        path, link = AVAILABLE / (name + '.conf'), ENABLED / (name + '.conf')
        if entry['path'] != str(path) or entry['link'] != str(link):
            fail('В копии указаны неожиданные пути')
        if path.is_symlink() or (path.exists() and not path.is_file()):
            fail(f'Изменился тип nginx-файла: {path}')
        current = digest(path.read_bytes()) if path.exists() else None
        if current not in entry['allowed_hashes']:
            fail(f'После переключения изменён конфиг; автоматическая замена запрещена: {path}')
        if link.is_symlink():
            if os.readlink(link) != entry['link_target'] or link.resolve() != path:
                fail(f'Изменилась nginx-ссылка: {link}')
        elif link.exists() or entry['existed']:
            fail(f'Изменился nginx-путь: {link}')
        if entry['existed']:
            source = backup / (name + '.conf')
            if source.is_symlink() or not source.is_file() or digest(source.read_bytes()) != entry['original_hash']:
                fail(f'Повреждён исходный конфиг: {source}')
    # Keep a recovery copy of current known files if nginx validation/reload fails.
    current = {e['name']: Path(e['path']).read_bytes() if Path(e['path']).exists() else None for e in entries}
    current_links = {e['name']: Path(e['link']).is_symlink() for e in entries}
    try:
        for entry in entries:
            path, link = Path(entry['path']), Path(entry['link'])
            if entry['existed']:
                atomic_write(path, (backup / (entry['name'] + '.conf')).read_bytes(), entry)
            else:
                if link.is_symlink():
                    link.unlink()
                if path.exists():
                    path.unlink()
        subprocess.run(['nginx', '-t'], check=True, timeout=30)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=True, timeout=30)
    except BaseException:
        # Failed validation leaves the running workers untouched; restore the known on-disk state.
        for entry in entries:
            path, link = Path(entry['path']), Path(entry['link'])
            data = current[entry['name']]
            if data is None:
                if link.is_symlink():
                    link.unlink()
                if path.exists():
                    path.unlink()
            else:
                atomic_write(path, data, entry)
                if current_links[entry['name']] and not link.is_symlink():
                    os.symlink(entry['link_target'], link)
        raise
    (backup / 'ROLLED_BACK').write_text('nginx configurations restored\n')
    print('Восстановлена прежняя маршрутизация nginx. Файлы сайтов, Docker, БД и сертификаты сохранены.')
    print(f'Резервная копия: {backup}')


try:
    main()
except (Exception, KeyboardInterrupt) as error:
    print(f'ОСТАНОВКА ОТКАТА: {error or "операция прервана"}', file=sys.stderr)
    sys.exit(1)
PY
