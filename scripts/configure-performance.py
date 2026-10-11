#!/usr/bin/env python3
"""Guarded performance settings for the two existing static-site nginx vhosts.

This script never changes Git, website files, certificates, global nginx settings,
redirect domains or Docker. Run from outside the public webroot after deployment.
"""
import argparse
import fcntl
import hashlib
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


ROOT = Path('/opt/legacy-stack/sites/sweb/site.urbaso.ru/public_html')
AVAILABLE = Path('/etc/nginx/sites-available')
ENABLED = Path('/etc/nginx/sites-enabled')
BACKUPS = Path('/root/backups/site.urbaso.ru')
LOCK = Path('/run/lock/site-urbaso-domain-cutover.lock')
HOSTS = ('urbaso.ru', 'site.urbaso.ru')
TLS = '''    ssl_certificate /etc/letsencrypt/live/{host}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{host}/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;'''
GZIP = '''    # Text compression is scoped to this site's TLS server only.
    gzip on;
    gzip_comp_level 5;
    gzip_min_length 512;
    gzip_vary on;
    gzip_types text/plain text/css text/javascript application/javascript
        application/json application/xml text/xml image/svg+xml;
'''
IMMUTABLE = r'''    # Only generated filenames with a 12-character content hash are immutable.
    # Keep this after the hidden-file rule and before the general asset rule.
    location ~ "^/assets/optimized/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+-[a-f0-9]{12}\.(?:webp|avif|woff2|css|js)$" {
        try_files $uri =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
'''


def fail(message):
    raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def tokens(text):
    # Quotes are retained so regex quantifiers and # inside quotes remain intact.
    pattern = r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\#[^\n]*|[^\s{};#]+|[{};]'''
    return [token for token in re.findall(pattern, text) if not token.startswith('#')]


def run(args, *, timeout=40):
    result = subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout)
    return result.stdout


def expected_config(host):
    """Exact post-cutover configuration; only comments/spacing may differ."""
    preview = host == 'site.urbaso.ru'
    names = host if preview else 'urbaso.ru www.urbaso.ru'
    redirect = f'''server {{
    listen 80;
    listen [::]:80;
    server_name {names};
    location / {{ return 301 https://{host}$request_uri; }}
}}
'''
    if not preview:
        redirect += f'''server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name www.urbaso.ru;
{TLS.format(host=host)}
    location / {{ return 301 https://urbaso.ru$request_uri; }}
}}
'''
    locations = r'''    location = / {
        try_files /index.html =404;
        add_header Cache-Control "no-cache" always;
    }
    location = /index.html {
        try_files $uri =404;
        add_header Cache-Control "no-cache" always;
    }
    location = /robots.txt { try_files $uri =404; }
    location = /sitemap.xml { try_files $uri =404; }
    location = /favicon.ico { try_files $uri =404; }
    location ~ /\. { return 404; }
    location ~* ^/assets/.*\.(?:css|js|mjs|json|xml|txt|svg|ico|jpg|jpeg|png|gif|webp|avif|woff|woff2|ttf|otf|eot|vcf)$ {
        try_files $uri =404;
        add_header Cache-Control "no-cache" always;
    }
'''
    if preview:
        locations += '    location = /tools/layout-check.html { try_files $uri =404; }\n'
    locations += '    location / { return 404; }\n'
    return redirect + f'''server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name {host};
    root {ROOT};
    index index.html;
    charset utf-8;
    access_log /var/log/nginx/{host}.access.log;
    error_log /var/log/nginx/{host}.error.log;
{TLS.format(host=host)}
{locations}}}
'''


def optimized_config(host):
    config = expected_config(host)
    config = config.replace(f'    root {ROOT};\n', f'    root {ROOT};\n' + GZIP, 1)
    hidden_rule = r'    location ~ /\. { return 404; }' + '\n'
    config = config.replace(hidden_rule, hidden_rule + IMMUTABLE, 1)
    return '# Managed by scripts/configure-performance.py; originals are in its backup.\n' + config


def config_path(host):
    return AVAILABLE / (host + '.conf')


def read_entry(host):
    path, link = config_path(host), ENABLED / (host + '.conf')
    if path.is_symlink() or not path.is_file() or not link.is_symlink() or link.resolve() != path:
        fail(f'Неожиданная схема nginx-файлов: {host}')
    original = path.read_bytes()
    info = path.stat()
    entry = {'name': host, 'path': str(path), 'link_target': os.readlink(link),
             'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid,
             'original_hash': digest(original), 'applied_hash': digest(optimized_config(host).encode())}
    return entry, original


def verify_entry(entry, allowed_hashes):
    current, data = read_entry(entry['name'])
    if current['path'] != entry['path'] or current['link_target'] != entry['link_target']:
        fail(f'Изменилась схема nginx-файлов: {entry["name"]}')
    if digest(data) not in allowed_hashes:
        fail(f'Конфиг изменён вне этой установки: {entry["name"]}; замена отменена')
    return data


def loaded_files():
    dump = run(['nginx', '-T'])
    paths = re.findall(r'(?m)^# configuration file ([^\n]+):$', dump)
    if not paths:
        fail('nginx -T не вернул список активных конфигов')
    result = {str(Path(path).resolve()): digest(Path(path).read_bytes()) for path in paths}
    for host in HOSTS:
        if str(config_path(host)) not in result:
            fail(f'Конфиг не включён в nginx: {host}')
    return result


def check_other_files(metadata):
    current = loaded_files()
    for entry in metadata['entries']:
        current.pop(entry['path'], None)
    if current != metadata['other_files']:
        fail('Изменился состав или содержимое других активных nginx-конфигов')


def atomic_write(path, content, entry):
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, entry['mode'])
        os.chown(temporary, entry['uid'], entry['gid'])
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def request(host, path, directory, *, gzip=False, scheme='https'):
    headers, body = directory / 'headers', directory / 'body'
    args = ['curl', '--disable', '--noproxy', '*', '--silent', '--show-error',
            '--connect-timeout', '4', '--max-time', '12', '--resolve',
            f'{host}:{443 if scheme == "https" else 80}:127.0.0.1',
            '--dump-header', str(headers), '--output', str(body), '--write-out', '%{http_code}']
    if gzip:
        args += ['--compressed', '-H', 'Accept-Encoding: gzip']
    status = run(args + [f'{scheme}://{host}{path}'], timeout=15).strip()
    fields = {}
    for line in headers.read_text().splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            fields.setdefault(key.lower(), []).append(value.strip())
    return status, fields, body.read_bytes()


def optimized_styles():
    # Check the naming contract before granting year-long caching to these files.
    optimized = ROOT / 'assets/optimized'
    for path in optimized.rglob('*'):
        match = re.search(r'-([a-f0-9]{12})\.(?:webp|avif|woff2|css|js)$', path.name)
        if path.is_file() and match and digest(path.read_bytes())[:12] != match.group(1):
            fail(f'Имя оптимизированного файла не соответствует SHA256: {path}')
    styles = sorted((ROOT / 'assets/optimized').glob('site-*.css'))
    styles = [path for path in styles if re.fullmatch(r'site-[a-f0-9]{12}\.css', path.name)]
    if not styles:
        fail('Не найден assets/optimized/site-<12 hex>.css; сначала установить код сайта')
    return styles


def smoke(directory):
    style = optimized_styles()[-1]
    style_url = '/' + str(style.relative_to(ROOT))
    for host in HOSTS:
        for path, expected in (('/', ROOT / 'index.html'), (style_url, style)):
            status, headers, body = request(host, path, directory, gzip=True)
            if status != '200' or body != expected.read_bytes():
                fail(f'Неверное содержимое {host}{path}: HTTP {status}')
            cache = ', '.join(headers.get('cache-control', []))
            wanted = 'no-cache' if path == '/' else 'public, max-age=31536000, immutable'
            if cache != wanted:
                fail(f'Неверный Cache-Control {host}{path}: {cache}')
            if headers.get('content-encoding') != ['gzip']:
                fail(f'Не включилось gzip-сжатие {host}{path}')
        status, headers, _ = request(host, '/assets/css/style.css', directory)
        if status != '200' or headers.get('cache-control') != ['no-cache']:
            fail(f'Изменилось кеширование исходного CSS: {host}')
        for path in ('/.git/config', '/AGENTS.md', '/docs/performance-server.md',
                     '/scripts/configure-performance.py', '/assets/.hidden.css',
                     '/assets/optimized/missing-123456789abc.css', '/not-a-real-page'):
            status, headers, _ = request(host, path, directory)
            if status != '404' or 'immutable' in ', '.join(headers.get('cache-control', [])):
                fail(f'Неверная защита служебного/отсутствующего пути: {host}{path}')
        status, headers, _ = request(host, '/?performance-check=1', directory, scheme='http')
        if status != '301' or headers.get('location') != [f'https://{host}/?performance-check=1']:
            fail(f'Изменилось HTTP-перенаправление: {host}')
        status, _, _ = request(host, '/tools/layout-check.html', directory)
        if status != ('200' if host == 'site.urbaso.ru' else '404'):
            fail(f'Изменился доступ к инструменту проверки: {host}')
    status, headers, _ = request('www.urbaso.ru', '/?performance-check=1', directory)
    if status != '301' or headers.get('location') != ['https://urbaso.ru/?performance-check=1']:
        fail('Изменилось HTTPS-перенаправление www.urbaso.ru')


def wait_smoke(backup):
    directory = backup / 'http-check'
    directory.mkdir(mode=0o700)
    deadline = time.monotonic() + 35
    while True:
        try:
            smoke(directory)
            return
        except (RuntimeError, subprocess.SubprocessError) as error:
            (directory / 'failure.txt').write_text(str(error) + '\n')
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)


def restore(backup):
    metadata = json.loads((backup / 'performance.json').read_text())
    entries = metadata.get('entries', [])
    if metadata.get('version') != 1 or len(entries) != 2 or {e['name'] for e in entries} != set(HOSTS):
        fail('Неизвестный формат резервной копии')
    previous = {}
    for entry in entries:
        if entry['path'] != str(config_path(entry['name'])):
            fail('Неожиданный путь в резервной копии')
        source = backup / (entry['name'] + '.conf')
        if source.is_symlink() or digest(source.read_bytes()) != entry['original_hash']:
            fail('Повреждён исходный конфиг в резервной копии')
        previous[entry['name']] = verify_entry(entry, {entry['original_hash'], entry['applied_hash']})
    try:
        for entry in entries:
            atomic_write(Path(entry['path']), (backup / (entry['name'] + '.conf')).read_bytes(), entry)
        run(['nginx', '-t'])
        run(['systemctl', 'reload', 'nginx'])
    except BaseException:
        for entry in entries:
            atomic_write(Path(entry['path']), previous[entry['name']], entry)
        # A reload can fail after sending its signal. Restore the known on-disk
        # configuration, then try to synchronize workers without masking the error.
        try:
            run(['nginx', '-t'])
            run(['systemctl', 'reload', 'nginx'])
        except Exception as error:
            print(f'Не удалось повторно загрузить сохранённую конфигурацию: {error}', file=sys.stderr)
        raise
    (backup / 'ROLLED_BACK').write_text('nginx performance configuration restored\n')
    print('Исходные настройки nginx восстановлены. Версия кода сайта не изменялась.')


def install(expected_sha, check_only):
    if not re.fullmatch(r'[a-f0-9]{40}', expected_sha):
        fail('Укажите полный SHA установленного коммита')
    if run(['git', '-C', str(ROOT), 'rev-parse', '--show-toplevel']).strip() != str(ROOT):
        fail('Неожиданный корень Git')
    if run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).strip() != expected_sha:
        fail('На сервере другой Git SHA')
    if run(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no']):
        fail('Есть изменения отслеживаемых файлов; сначала сохранить и разобрать их')
    if Path(__file__).resolve().is_relative_to(ROOT):
        fail('Запустите копию скрипта из временного каталога вне webroot')
    run(['nginx', '-t'])
    run(['systemctl', 'is-active', '--quiet', 'nginx'])
    optimized_styles()
    tls_include = Path('/etc/letsencrypt/options-ssl-nginx.conf')
    if any(token.startswith('gzip') for token in tokens(tls_include.read_text())):
        fail('TLS include уже содержит gzip-директивы; требуется отдельная сверка')
    entries, originals, states = [], {}, []
    initial_files = loaded_files()
    for host in HOSTS:
        entry, original = read_entry(host)
        content_tokens = tokens(original.decode())
        if content_tokens == tokens(expected_config(host)):
            states.append('original')
        elif content_tokens == tokens(optimized_config(host)):
            states.append('optimized')
        else:
            fail(f'Конфиг {host} отличается от согласованного cutover; ничего не записано')
        if initial_files.get(entry['path']) != digest(original):
            fail(f'Конфиг изменился во время проверки: {host}')
        entries.append(entry)
        originals[host] = original
    if len(set(states)) != 1:
        fail('Один vhost уже оптимизирован, другой нет; требуется сверка')
    if states[0] == 'optimized':
        print('Оба vhost уже имеют эти настройки; повторная запись не нужна.')
        return
    # The webroot cannot be used for backups, even if a parent directory is linked.
    if BACKUPS.resolve().is_relative_to(ROOT.resolve()):
        fail('Резервная копия должна находиться вне webroot')
    metadata = {'version': 1, 'site_sha': expected_sha, 'entries': entries,
                'other_files': {p: h for p, h in initial_files.items() if p not in {e['path'] for e in entries}}}
    check_other_files(metadata)
    if check_only:
        print(f'Проверка пройдена. SHA: {expected_sha}. Можно включить gzip и кеширование версий.')
        return
    BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='performance-', dir=BACKUPS))
    os.chmod(backup, 0o700)
    for entry in entries:
        (backup / (entry['name'] + '.conf')).write_bytes(originals[entry['name']])
    shutil.copy2(Path(__file__).resolve(), backup / 'configure-performance.py')
    (backup / 'performance.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    print(f'Резервная копия: {backup}', flush=True)
    print(f'Откат nginx: python3 {backup}/configure-performance.py --rollback {backup}', flush=True)
    mutated = False
    try:
        check_other_files(metadata)
        for entry in entries:
            verify_entry(entry, {entry['original_hash']})
        for entry in entries:
            # Recheck immediately before each write; do not replace concurrent edits.
            verify_entry(entry, {entry['original_hash']})
            mutated = True
            atomic_write(Path(entry['path']), optimized_config(entry['name']).encode(), entry)
        run(['nginx', '-t'])
        check_other_files(metadata)
        run(['systemctl', 'reload', 'nginx'])
        wait_smoke(backup)
        check_other_files(metadata)
        for entry in entries:
            verify_entry(entry, {entry['applied_hash']})
        (backup / 'COMPLETED').write_text(expected_sha + '\n')
        print('gzip, кеширование, содержимое страниц и защита служебных путей проверены.')
    except BaseException:
        if mutated:
            print('Проверка не прошла; возвращаю прежние nginx-конфиги.', file=sys.stderr, flush=True)
            restore(backup)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('expected_sha', nargs='?')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    if args.rollback and (args.expected_sha or args.check_only):
        parser.error('--rollback используется отдельно')
    if not args.rollback and not args.expected_sha:
        parser.error('нужен полный SHA установленного коммита')
    if os.geteuid() != 0 or run(['hostname']).strip() != 'urbaserge3-vps-1':
        fail('Скрипт предназначен для запуска root на urbaserge3-vps-1')
    with LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.rollback:
            backup = args.rollback.resolve(strict=True)
            if backup.parent != BACKUPS.resolve() or not backup.name.startswith('performance-'):
                fail('Неожиданный каталог резервной копии')
            restore(backup)
        else:
            git_dir = Path(run(['git', '-C', str(ROOT), 'rev-parse', '--absolute-git-dir']).strip())
            with (git_dir / 'site-deploy.lock').open('a') as git_lock:
                fcntl.flock(git_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                install(args.expected_sha, args.check_only)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(f'ОСТАНОВКА: {error or "операция прервана"}', file=sys.stderr)
        sys.exit(1)
