#!/usr/bin/env python3
"""Expose only image/video files below /delete without changing the site checkout.

Download configure-performance.py from the same reviewed commit beside this file.
Both files must be outside the public webroot. Backups include both for rollback.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
HELPER = Path(__file__).resolve().with_name('configure-performance.py')
spec = importlib.util.spec_from_file_location('performance_config', HELPER)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
VIDEO = 'delete/astra/video/video3.mp4'
MEDIA = r'''    # Public media only; keep after the hidden-file rule.
    location ~* ^/delete/.*\.(?:jpg|jpeg|png|gif|webp|avif|mp4|webm)$ {
        try_files $uri =404;
        autoindex off;
        disable_symlinks on from=$document_root;
        types {
            image/jpeg jpg jpeg;
            image/png png;
            image/gif gif;
            image/webp webp;
            image/avif avif;
            video/mp4 mp4;
            video/webm webm;
        }
        default_type application/octet-stream;
        add_header Cache-Control "no-cache" always;
        add_header X-Content-Type-Options "nosniff" always;
    }
'''
HIDDEN = re.compile(r'(?m)^[ \t]*location\s+~\s+/\\\.\s*\{\s*return\s+404\s*;\s*\}')


def patched(text):
    matches = list(HIDDEN.finditer(text))
    if len(matches) != 1:
        base.fail('Не найдена единственная ожидаемая защита скрытых файлов')
    end = matches[0].end()
    return text[:end] + '\n' + MEDIA.rstrip('\n') + text[end:]


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def error_details(error):
    if isinstance(error, subprocess.CalledProcessError) and error.stderr:
        detail = error.stderr.decode(errors='replace') if isinstance(error.stderr, bytes) else error.stderr
        print(detail.strip(), file=sys.stderr)


def git(*args):
    return subprocess.check_output(['git', '--no-optional-locks', '-C', str(base.ROOT), *args])


def git_state():
    return {'head': git('rev-parse', 'HEAD').decode().strip(),
            'status': git('status', '--porcelain=v1', '--untracked-files=all').decode(),
            'flags_sha256': base.digest(git('ls-files', '-v', '-z')),
            'index_sha256': file_hash(Path(git('rev-parse', '--absolute-git-dir').decode().strip()) / 'index')}


def regular(path):
    for item in (path, *path.parents):
        if item == base.ROOT:
            break
        if item.is_symlink():
            base.fail('Ссылка в пути медиа: ' + str(item))
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        base.fail('Нет обычного файла: ' + str(path))


def inventory():
    directory = base.ROOT / 'delete'
    if directory.is_symlink() or not directory.is_dir():
        base.fail('delete должен быть обычным каталогом в webroot')
    rows = []
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            base.fail('Ссылка внутри delete: ' + str(path))
        if path.is_dir():
            continue
        regular(path)
        size = path.stat().st_size
        # Large originals remain on the server; do not read entire videos.
        small_image = path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif'} and size <= 10 * 1024 * 1024
        rows.append({'path': path.relative_to(base.ROOT).as_posix(),
                     'bytes': size, 'sha256': file_hash(path) if small_image else None})
    print('Файлы delete (оригинальные байты):', flush=True)
    print(json.dumps(rows, ensure_ascii=False, indent=2), flush=True)
    video = base.ROOT / VIDEO
    regular(video)
    size = video.stat().st_size
    if not size:
        base.fail('Видео пустое')
    with video.open('rb') as stream:
        prefix = stream.read(1024)
    return rows, size, prefix


def range_request(host, directory, size, prefix):
    headers, body = directory / 'range.headers', directory / 'range.body'
    status = base.run(['curl', '--disable', '--noproxy', '*', '--silent', '--show-error',
                       '--connect-timeout', '4', '--max-time', '12', '--max-filesize', '1024',
                       '--resolve', f'{host}:443:127.0.0.1', '--range', '0-1023',
                       '--dump-header', str(headers), '--output', str(body),
                       '--write-out', '%{http_code}', f'https://{host}/{VIDEO}'], timeout=15).strip()
    fields = {}
    for line in headers.read_text().splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            fields.setdefault(key.lower(), []).append(value.strip())
    if (status != '206' or fields.get('content-type') != ['video/mp4']
            or fields.get('content-range') != [f'bytes 0-{len(prefix) - 1}/{size}']
            or body.read_bytes() != prefix):
        base.fail(f'Не прошла проверка Range/MIME/байтов: {host}/{VIDEO}, HTTP {status}')


def smoke(directory, originals, size, prefix):
    for host in base.HOSTS:
        status, _, body = base.request(host, '/', directory)
        if status != '200' or body != originals[host]:
            base.fail('Изменилось содержимое главной страницы: ' + host)
        range_request(host, directory, size, prefix)
        image = base.ROOT / 'delete/astra/1.jpg'
        if image.is_file():
            status, headers, body = base.request(host, '/delete/astra/1.jpg', directory)
            if status != '200' or headers.get('content-type') != ['image/jpeg'] or body != image.read_bytes():
                base.fail('Не прошла проверка исходного изображения: ' + host)
        for path in ('/.git/config', '/scripts/configure-delete-media.py',
                     '/delete/.hidden.jpg', '/delete/astra/.hidden/test.mp4',
                     '/delete/astra/test.php', '/delete/astra/test.html',
                     '/delete/astra/video/', '/delete/astra/video/not-a-real-video.mp4'):
            status, _, _ = base.request(host, path, directory)
            if status != '404':
                base.fail(f'Изменился доступ к закрытому пути: {host}{path}, HTTP {status}')


def restore(backup):
    raw = (backup / 'delete-media.json').read_bytes()
    if base.digest(raw) != (backup / 'delete-media.sha256').read_text().strip():
        base.fail('Повреждены сведения резервной копии')
    metadata = json.loads(raw)
    entries = metadata.get('entries', [])
    if (metadata.get('kind') != 'delete-media-v1' or len(entries) != 2
            or {entry['name'] for entry in entries} != set(base.HOSTS)):
        base.fail('Неизвестный формат резервной копии')
    before = {}
    for entry in entries:
        if entry['path'] != str(base.config_path(entry['name'])):
            base.fail('Неожиданный путь конфигурации в резервной копии')
        source = backup / (entry['name'] + '.conf')
        if source.is_symlink() or file_hash(source) != entry['original_hash']:
            base.fail('Повреждён сохранённый nginx-конфиг')
        before[entry['name']] = base.verify_entry(entry, {entry['original_hash'], entry['applied_hash']})
    # nginx -T cannot parse an invalid just-written config. Check the saved
    # unrelated files directly until our known originals are back on disk.
    for name, expected in metadata['other_files'].items():
        path = Path(name)
        if path.is_symlink() or not path.is_file() or file_hash(path) != expected:
            base.fail('Откат остановлен: изменён другой nginx-файл: ' + name)
    try:
        for entry in entries:
            base.verify_entry(entry, {base.digest(before[entry['name']])})
            base.atomic_write(Path(entry['path']), (backup / (entry['name'] + '.conf')).read_bytes(), entry)
        base.run(['nginx', '-t'])
        base.check_other_files(metadata)
        base.run(['systemctl', 'reload', 'nginx'])
    except BaseException as error:
        error_details(error)
        # Never put a potentially invalid applied config back over originals.
        print('Откат не завершён. Сохранённые оригиналы не удалены; '\
              'необходимо проверить nginx перед дальнейшей перезагрузкой.', file=sys.stderr)
        raise
    (backup / 'ROLLED_BACK').write_text('delete media nginx configuration restored\n')
    print('Исходные nginx-конфиги восстановлены; файлы сайта и Git не менялись.')


def install():
    state = git_state()
    print('Текущий Git:', json.dumps(state, ensure_ascii=False), flush=True)
    rows, size, prefix = inventory()
    base.run(['nginx', '-t'])
    base.run(['systemctl', 'is-active', '--quiet', 'nginx'])
    initial = base.loaded_files()
    entries, original, updated, modes = [], {}, {}, []
    for host in base.HOSTS:
        entry, data = base.read_entry(host)
        text = data.decode()
        current = base.tokens(text)
        if current == base.tokens(base.optimized_config(host)):
            modes.append('old')
            replacement = patched(text).encode()
        elif current == base.tokens(patched(base.optimized_config(host))):
            modes.append('media')
            replacement = data
        else:
            base.fail('Неизвестная nginx-конфигурация, замена отменена: ' + host)
        if initial.get(entry['path']) != base.digest(data):
            base.fail('Конфиг изменился во время проверки: ' + host)
        entry['applied_hash'] = base.digest(replacement)
        entries.append(entry)
        original[host], updated[host] = data, replacement
    if len(set(modes)) != 1:
        base.fail('Два домена имеют разные состояния media-конфигурации; требуется сверка')
    with tempfile.TemporaryDirectory(prefix='delete-media-check-') as temporary:
        checks = Path(temporary)
        pages = {}
        for host in base.HOSTS:
            status, _, body = base.request(host, '/', checks)
            if status != '200' or body != (base.ROOT / 'index.html').read_bytes():
                base.fail('До изменения сервер отдаёт неожиданную главную страницу: ' + host)
            pages[host] = body
        if modes[0] == 'media':
            smoke(checks, pages, size, prefix)
            if git_state() != state:
                base.fail('Состояние Git изменилось во время проверки')
            print('Доступ к медиа уже настроен и проверен; повторная запись не нужна.')
            return
        base.BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
        if base.BACKUPS.resolve().is_relative_to(base.ROOT.resolve()):
            base.fail('Резервная копия должна находиться вне webroot')
        backup = Path(tempfile.mkdtemp(prefix='delete-media-', dir=base.BACKUPS))
        os.chmod(backup, 0o700)
        metadata = {'kind': 'delete-media-v1', 'git': state, 'inventory': rows, 'entries': entries,
                    'other_files': {p: h for p, h in initial.items()
                                    if p not in {entry['path'] for entry in entries}}}
        for entry in entries:
            (backup / (entry['name'] + '.conf')).write_bytes(original[entry['name']])
        for path in (Path(__file__).resolve(), HELPER):
            shutil.copy2(path, backup / path.name)
        raw = (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode()
        (backup / 'delete-media.json').write_bytes(raw)
        (backup / 'delete-media.sha256').write_text(base.digest(raw) + '\n')
        print('Резервная копия:', backup, flush=True)
        print(f'Откат: python3 {backup}/configure-delete-media.py --rollback {backup}', flush=True)
        mutated = False
        try:
            base.check_other_files(metadata)
            if git_state() != state:
                base.fail('Состояние Git изменилось до записи')
            for entry in entries:
                base.verify_entry(entry, {entry['original_hash']})
            for entry in entries:
                base.verify_entry(entry, {entry['original_hash']})
                mutated = True
                base.atomic_write(Path(entry['path']), updated[entry['name']], entry)
            base.run(['nginx', '-t'])
            base.check_other_files(metadata)
            base.run(['systemctl', 'reload', 'nginx'])
            deadline = time.monotonic() + 15
            while True:
                try:
                    smoke(checks, pages, size, prefix)
                    break
                except (RuntimeError, subprocess.SubprocessError):
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.5)
            base.check_other_files(metadata)
            for entry in entries:
                base.verify_entry(entry, {entry['applied_hash']})
            if git_state() != state:
                base.fail('Состояние Git изменилось во время установки')
            (backup / 'COMPLETED').write_text(state['head'] + '\n')
            print('Медиа открыты. Range 206, video/mp4, исходные байты и закрытые пути проверены.')
        except BaseException as error:
            error_details(error)
            if mutated:
                print('Проверка не прошла; восстанавливаю nginx-конфиги.', file=sys.stderr, flush=True)
                try:
                    restore(backup)
                except BaseException as rollback_error:
                    error_details(rollback_error)
                    base.fail(f'Автоматический откат не завершён: {rollback_error}. Резервная копия: {backup}')
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0 or base.run(['hostname']).strip() != 'urbaserge3-vps-1':
        base.fail('Скрипт предназначен для root на urbaserge3-vps-1')
    if Path(__file__).resolve().is_relative_to(base.ROOT.resolve()):
        base.fail('Запустите скачанные скрипты из каталога вне webroot')
    if git('rev-parse', '--show-toplevel').decode().strip() != str(base.ROOT):
        base.fail('Неожиданный корень Git')
    git_dir = Path(git('rev-parse', '--absolute-git-dir').decode().strip())
    with base.LOCK.open('a') as lock, (git_dir / 'site-deploy.lock').open('a') as git_lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(git_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.rollback:
            backup = args.rollback.resolve(strict=True)
            if backup.parent != base.BACKUPS.resolve() or not backup.name.startswith('delete-media-'):
                base.fail('Неожиданный каталог резервной копии')
            restore(backup)
        else:
            install()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        error_details(error)
        print(f'ОСТАНОВКА: {error or "операция прервана"}', file=sys.stderr)
        sys.exit(1)
