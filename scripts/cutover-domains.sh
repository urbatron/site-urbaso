#!/usr/bin/env bash
# One-time, guarded nginx cutover. Does not copy website files or change Docker/Git.
set -Eeuo pipefail
exec python3 - "$@" <<'PY'
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile

ROOT = Path('/opt/legacy-stack/sites/sweb/site.urbaso.ru/public_html')
AVAILABLE = Path('/etc/nginx/sites-available')
ENABLED = Path('/etc/nginx/sites-enabled')
BACKUPS = Path('/root/backups/site.urbaso.ru')
LOCK = Path('/run/lock/site-urbaso-domain-cutover.lock')
MAIN = 'urbaso.ru'
ALIASES = ('sitetops.ru', 'disiner.ru', 'prodvizheniyesaytov.ru')
CERT_NAMES = (MAIN, 'www.' + MAIN, ALIASES[2], 'www.' + ALIASES[2])
HOSTS = (MAIN, 'www.' + MAIN, *(h for d in ALIASES for h in (d, 'www.' + d)))
NEW_NAME = ALIASES[2]
TLS = '''    ssl_certificate /etc/letsencrypt/live/{cert}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{cert}/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;'''

# The complete configurations supplied by the owner on 2026-10-04.
# Token comparison ignores comments/formatting, but accepts no added directive.
EXPECTED = {
'urbaso.ru': '''server {
listen 80; server_name urbaso.ru; return 301 https://$host$request_uri;
}
server {
listen 443 ssl; server_name urbaso.ru; client_max_body_size 64M;
ssl_certificate /etc/letsencrypt/live/urbaso.ru/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/urbaso.ru/privkey.pem;
include /etc/letsencrypt/options-ssl-nginx.conf;
ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
location / {
proxy_pass http://127.0.0.1:8084; proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header HTTPS on;
proxy_set_header X-Forwarded-SSL on;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Port $server_port;
} }''',
'sitetops.ru': '''server {
listen 80; server_name sitetops.ru www.sitetops.ru; return 301 https://$host$request_uri;
}
server {
listen 443 ssl; server_name sitetops.ru www.sitetops.ru;
access_log /var/log/nginx/sitetops.ru.access.log;
error_log /var/log/nginx/sitetops.ru.error.log;
ssl_certificate /etc/letsencrypt/live/sitetops.ru/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/sitetops.ru/privkey.pem;
include /etc/letsencrypt/options-ssl-nginx.conf;
ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
location / {
proxy_pass http://127.0.0.1:8083; proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Port $server_port;
} }''',
'disiner.ru': r'''server {
listen 80; listen [::]:80; server_name disiner.ru www.disiner.ru;
return 301 https://disiner.ru$request_uri;
}
server {
listen 443 ssl http2; listen [::]:443 ssl http2; server_name www.disiner.ru;
ssl_certificate /etc/letsencrypt/live/disiner.ru/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/disiner.ru/privkey.pem;
include /etc/letsencrypt/options-ssl-nginx.conf;
ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
return 301 https://disiner.ru$request_uri;
}
server {
listen 443 ssl http2; listen [::]:443 ssl http2; server_name disiner.ru;
root /opt/legacy-stack/sites/sweb/disiner.ru/public_html;
index index.html;
access_log /var/log/nginx/disiner.ru.access.log;
error_log /var/log/nginx/disiner.ru.error.log;
ssl_certificate /etc/letsencrypt/live/disiner.ru/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/disiner.ru/privkey.pem;
include /etc/letsencrypt/options-ssl-nginx.conf;
ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
sendfile on; tcp_nopush on; tcp_nodelay on; keepalive_timeout 65;
gzip on; gzip_comp_level 6; gzip_min_length 1024; gzip_vary on;
gzip_proxied any; gzip_static on;
gzip_types text/plain text/css text/xml text/javascript application/javascript
application/x-javascript application/json application/xml application/xml+rss
image/svg+xml font/ttf font/otf font/woff font/woff2;
charset utf-8;
location = / {
try_files /index.html =404;
add_header Cache-Control "public, max-age=300, stale-while-revalidate=86400" always;
}
location = /index.html {
add_header Cache-Control "public, max-age=300, stale-while-revalidate=86400" always;
}
location ~* \.(?:css|js|mjs|json|xml|txt|svg|ico|jpg|jpeg|png|gif|webp|avif|woff|woff2|ttf|otf|eot)$ {
try_files $uri =404; access_log off; expires 365d;
add_header Cache-Control "public, max-age=31536000, immutable" always;
}
location / {
try_files $uri $uri/ /index.html;
add_header Cache-Control "public, max-age=300, stale-while-revalidate=86400" always;
}
location ~ /\.(?!well-known) { deny all; }
}''',
'site.urbaso.ru': '''server {
server_name site.urbaso.ru;
root /opt/legacy-stack/sites/sweb/site.urbaso.ru/public_html;
index index.html index.htm;
access_log /var/log/nginx/site.urbaso.ru.access.log;
error_log /var/log/nginx/site.urbaso.ru.error.log;
location / { try_files $uri $uri/ =404; }
listen [::]:443 ssl; listen 443 ssl;
ssl_certificate /etc/letsencrypt/live/site.urbaso.ru/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/site.urbaso.ru/privkey.pem;
include /etc/letsencrypt/options-ssl-nginx.conf;
ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}
server {
if ($host = site.urbaso.ru) { return 301 https://$host$request_uri; }
listen 80; listen [::]:80; server_name site.urbaso.ru; return 404;
}''',
}


def tokens(text):
    # Preserve quoted values and nginx regex arguments; split only grammar separators.
    return re.findall(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[^\s{};#]+|[{};]',
                      re.sub(r'(?m)#[^\n]*$', '', text))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(args, *, capture=False, timeout=60):
    result = subprocess.run(args, check=True, text=True, capture_output=capture, timeout=timeout)
    return result.stdout if capture else ''


def fail(message):
    raise RuntimeError(message)


def redirect_config(names, cert, destination):
    hostnames = ' '.join(names)
    # A location-level redirect lets the nginx ACME plugin add an exact challenge location.
    return f'''# Managed by scripts/cutover-domains.sh. Original file is in the rollback backup.
server {{
    listen 80;
    listen [::]:80;
    server_name {hostnames};
    location / {{ return 301 {destination}; }}
}}
server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name {hostnames};
{TLS.format(cert=cert)}
    location / {{ return 301 {destination}; }}
}}
'''


def public_locations(preview=False):
    qa = "    location = /tools/layout-check.html { try_files $uri =404; }\n" if preview else ''
    return r'''    location = / {
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
    # First regex wins: hidden files cannot pass through the asset rule below.
    location ~ /\. { return 404; }
    location ~* ^/assets/.*\.(?:css|js|mjs|json|xml|txt|svg|ico|jpg|jpeg|png|gif|webp|avif|woff|woff2|ttf|otf|eot|vcf)$ {
        try_files $uri =404;
        add_header Cache-Control "no-cache" always;
    }
''' + qa + '    location / { return 404; }\n'


def final_configs():
    main = f'''# Managed by scripts/cutover-domains.sh. Legacy Docker/files are preserved.
server {{
    listen 80;
    listen [::]:80;
    server_name urbaso.ru www.urbaso.ru;
    location / {{ return 301 https://urbaso.ru$request_uri; }}
}}
server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name www.urbaso.ru;
{TLS.format(cert=MAIN)}
    location / {{ return 301 https://urbaso.ru$request_uri; }}
}}
server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name urbaso.ru;
    root {ROOT};
    index index.html;
    charset utf-8;
    access_log /var/log/nginx/urbaso.ru.access.log;
    error_log /var/log/nginx/urbaso.ru.error.log;
{TLS.format(cert=MAIN)}
{public_locations()}}}
'''
    preview = f'''# Same static site and QA helper; repository and deployment files are not public.
server {{
    listen 80;
    listen [::]:80;
    server_name site.urbaso.ru;
    location / {{ return 301 https://site.urbaso.ru$request_uri; }}
}}
server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name site.urbaso.ru;
    root {ROOT};
    index index.html;
    charset utf-8;
    access_log /var/log/nginx/site.urbaso.ru.access.log;
    error_log /var/log/nginx/site.urbaso.ru.error.log;
{TLS.format(cert='site.urbaso.ru')}
{public_locations(preview=True)}}}
'''
    return {MAIN: main, 'site.urbaso.ru': preview,
            **{domain: redirect_config((domain, 'www.' + domain),
               MAIN if domain == NEW_NAME else domain, 'https://urbaso.ru/$is_args$args')
               for domain in ALIASES}}


STAGE = '''# Temporary HTTP hosts for nginx ACME authentication; replaced after issuance.
server {
    listen 80;
    listen [::]:80;
    server_name www.urbaso.ru prodvizheniyesaytov.ru www.prodvizheniyesaytov.ru;
    location / { return 404; }
}
'''


def certificate_names(name):
    path = f'/etc/letsencrypt/live/{name}/fullchain.pem'
    run(['openssl', 'x509', '-in', path, '-noout', '-checkend', '604800'], capture=True)
    output = run(['openssl', 'x509', '-in', path, '-noout', '-ext', 'subjectAltName'], capture=True)
    return set(re.findall(r'DNS:([^,\s]+)', output))


def check_renewal(name):
    text = Path(f'/etc/letsencrypt/renewal/{name}.conf').read_text()
    for key in ('authenticator', 'installer'):
        if not re.search(rf'(?m)^\s*{key}\s*=\s*nginx\s*$', text):
            fail(f'Неожиданный {key} продления: {name}')
    if not re.search(r'(?m)^\s*server\s*=\s*https://acme-v02.api.letsencrypt.org/directory\s*$', text):
        fail(f'Неожиданный ACME server: {name}')


def loaded_files(check_host_scope=False):
    dump = run(['nginx', '-T'], capture=True)
    if check_host_scope:
        blocks = re.split(r'(?m)^# configuration file ', dump)[1:]
        expected_hosts = set(HOSTS) | {'site.urbaso.ru'}
        for block in blocks:
            first, _, content = block.partition('\n')
            path = Path(first.rstrip(':')).resolve()
            for names in re.findall(r'\bserver_name\s+([^;]+);', re.sub(r'(?m)#[^\n]*$', '', content)):
                for name in set(names.split()) & expected_hosts:
                    owner = name[4:] if name.startswith('www.') else name
                    # www.urbaso/prodvizheniyesaytov are intentionally absent before this cutover.
                    if name == 'www.urbaso.ru' or owner == NEW_NAME or path != AVAILABLE / (owner + '.conf'):
                        fail(f'Неожиданное объявление server_name {name}: {path}')
    paths = re.findall(r'(?m)^# configuration file ([^\n]+):$', dump)
    if not paths:
        fail('Не удалось получить полный список активных nginx-конфигов')
    return {str(Path(p).resolve()): digest(Path(p).read_bytes()) for p in paths}


def unchanged_other_files(metadata):
    current = loaded_files()
    for entry in metadata['entries']:
        current.pop(entry['path'], None)
    if current != metadata['other_files']:
        changed = sorted(set(current) ^ set(metadata['other_files']) |
                         {p for p in current.keys() & metadata['other_files'].keys()
                          if current[p] != metadata['other_files'][p]})
        fail(f'Изменились посторонние nginx-конфиги: {changed}')


def check_live_entry(entry):
    path, link = Path(entry['path']), Path(entry['link'])
    if path.is_symlink() or (path.exists() and not path.is_file()):
        fail(f'Неожиданный тип файла: {path}')
    current = digest(path.read_bytes()) if path.exists() else None
    if current not in entry['allowed_hashes']:
        fail(f'Конфиг изменён вне этой установки: {path}')
    if link.is_symlink():
        if os.readlink(link) != entry['link_target']:
            fail(f'Изменилась nginx-ссылка: {link}')
    elif link.exists() or entry['existed']:
        fail(f'Неожиданный nginx-путь: {link}')


def atomic_write(path, data, mode=0o644, uid=0, gid=0):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.chown(name, uid, gid)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_config(entry, content):
    check_live_entry(entry)
    path, link = Path(entry['path']), Path(entry['link'])
    atomic_write(path, content.encode(), entry['mode'], entry['uid'], entry['gid'])
    if not link.is_symlink():
        os.symlink(entry['link_target'], link)


def request(host, scheme, path, directory):
    headers, body = directory / 'headers', directory / 'body'
    status = run(['curl', '--noproxy', '*', '--silent', '--show-error',
        '--connect-timeout', '5', '--max-time', '20', '--resolve',
        f'{host}:{443 if scheme == "https" else 80}:127.0.0.1',
        '--dump-header', str(headers), '--output', str(body), '--write-out', '%{http_code}',
        f'{scheme}://{host}{path}'], capture=True, timeout=25).strip()
    header_text = headers.read_text()
    location = re.findall(r'(?im)^location:\s*(.*?)\r?$', header_text)
    return status, location[-1] if location else None, body.read_bytes()


def smoke(directory):
    for path in ('/', '/assets/css/harmony.css', '/assets/contacts/sergey-urba.vcf'):
        status, _, body = request(MAIN, 'https', path, directory)
        expected = ROOT / ('index.html' if path == '/' else path.lstrip('/'))
        if status != '200' or body != expected.read_bytes():
            fail(f'Основной сайт отдаёт неверный файл: {path}, HTTP {status}')
    probe = '/domain-cutover-check?utm_source=domain-cutover&check=1'
    for host in HOSTS:
        for scheme in ('http', 'https'):
            if host == MAIN and scheme == 'https':
                continue
            status, location, _ = request(host, scheme, probe, directory)
            wanted = ('https://urbaso.ru' + probe if host in (MAIN, 'www.' + MAIN)
                      else 'https://urbaso.ru/?utm_source=domain-cutover&check=1')
            if status != '301' or location != wanted:
                fail(f'Неожиданный редирект {scheme}://{host}: HTTP {status}, {location}')
    for host in (MAIN, 'site.urbaso.ru'):
        for path in ('/.git/config', '/AGENTS.md', '/README.md', '/docs/deployment.md',
                     '/scripts/deploy-review.sh', '/assets/.hidden.css'):
            if request(host, 'https', path, directory)[0] != '404':
                fail(f'На {host} доступен служебный путь: {path}')
    if request(MAIN, 'https', '/tools/layout-check.html', directory)[0] != '404':
        fail('Инструмент проверки доступен на основном домене')
    if request('site.urbaso.ru', 'https', '/tools/layout-check.html', directory)[0] != '200':
        fail('Недоступен прежний инструмент проверки site.urbaso.ru')


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == '--render':
        destination = Path(args[1])
        destination.mkdir(mode=0o700, parents=False, exist_ok=False)
        for name, content in final_configs().items():
            (destination / (name + '.conf')).write_text(content)
        (destination / 'acme-stage.conf').write_text(STAGE)
        print(f'Шаблоны записаны: {destination}')
        return
    if not (len(args) in (1, 2) and re.fullmatch(r'[0-9a-f]{40}', args[0])
            and (len(args) == 1 or args[1] == '--check-only')):
        fail('Использование: cutover-domains.sh ПОЛНЫЙ_ТЕКУЩИЙ_SHA [--check-only]')
    expected_sha, check_only = args[0], len(args) == 2
    if os.geteuid() != 0:
        fail('Скрипт запускается от root на согласованном VPS')
    for command in ('nginx', 'systemctl', 'certbot', 'curl', 'openssl', 'git'):
        if not shutil.which(command):
            fail(f'Не найдена команда: {command}')
    if run(['hostname'], capture=True).strip() != 'urbaserge3-vps-1':
        fail('Неожиданный сервер')
    os.chdir(ROOT)
    if run(['git', 'rev-parse', '--show-toplevel'], capture=True).strip() != str(ROOT):
        fail('Неожиданный корень Git')
    if run(['git', 'rev-parse', 'HEAD'], capture=True).strip() != expected_sha:
        fail('На сервере другой SHA')
    if run(['git', 'status', '--porcelain=v1', '--untracked-files=all'], capture=True):
        fail('Есть изменения или неотслеживаемые файлы; сначала разобрать их')
    for path in ('scripts/cutover-domains.sh', 'scripts/rollback-domains.sh'):
        run(['git', 'ls-files', '--error-unmatch', path], capture=True)
    for path in (ROOT / 'index.html', ROOT / 'assets/css/harmony.css',
                 ROOT / 'assets/contacts/sergey-urba.vcf'):
        if not path.is_file() or path.is_symlink():
            fail(f'Нет ожидаемого файла: {path}')
    run(['nginx', '-t'])
    run(['systemctl', 'is-active', '--quiet', 'nginx'])
    for host in (*HOSTS, 'site.urbaso.ru'):
        addresses = {x[4][0] for x in socket.getaddrinfo(host, 80, socket.AF_INET)}
        if addresses != {'80.93.52.205'}:
            fail(f'Изменился DNS A для {host}: {sorted(addresses)}')
        try:
            ipv6 = {x[4][0] for x in socket.getaddrinfo(host, 80, socket.AF_INET6)}
        except socket.gaierror as error:
            no_address = {getattr(socket, name, None) for name in
                          ('EAI_NONAME', 'EAI_NODATA', 'EAI_ADDRFAMILY')}
            if error.errno not in no_address:
                raise
            ipv6 = set()
        if ipv6:
            fail(f'Обнаружена непроверенная AAAA-запись: {host}')
    existing_cert = certificate_names(MAIN)
    old_names = set(CERT_NAMES) - {'www.' + MAIN}
    if existing_cert not in (old_names, set(CERT_NAMES)):
        fail('Состав urbaso-сертификата отличается; нельзя заменить неизвестные SAN')
    for name in (MAIN, 'sitetops.ru', 'disiner.ru'):
        check_renewal(name)
        if name != MAIN and certificate_names(name) != {name, 'www.' + name}:
            fail(f'Неожиданный состав сертификата: {name}')
    checked_configs = {}
    for name, expected in EXPECTED.items():
        link, path = ENABLED / (name + '.conf'), AVAILABLE / (name + '.conf')
        if not link.is_symlink() or link.resolve() != path or path.is_symlink() or not path.is_file():
            fail(f'Изменилась схема nginx-файлов: {name}')
        checked_bytes = path.read_bytes()
        if tokens(checked_bytes.decode()) != tokens(expected):
            fail(f'Конфиг {name} отличается от присланного; требуется повторная сверка')
        checked_configs[name] = (checked_bytes, path.stat(), os.readlink(link))
    for path in (AVAILABLE / (NEW_NAME + '.conf'), ENABLED / (NEW_NAME + '.conf')):
        if path.exists() or path.is_symlink():
            fail(f'Новый nginx-путь уже занят: {path}')
    initial_files = loaded_files(check_host_scope=True)
    for name, (content, _, _) in checked_configs.items():
        if initial_files.get(str(AVAILABLE / (name + '.conf'))) != digest(content):
            fail(f'Конфиг изменился во время проверки: {name}')
    if check_only:
        print(f'Проверка завершена. SHA: {expected_sha}. Конфигурация допускает переключение.')
        return

    domain_lock = open(LOCK, 'a')
    fcntl.flock(domain_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    git_lock = open(ROOT / '.git/site-deploy.lock', 'a')
    fcntl.flock(git_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if run(['git', 'rev-parse', 'HEAD'], capture=True).strip() != expected_sha:
        fail('SHA изменился во время проверки')
    if run(['git', 'status', '--porcelain=v1', '--untracked-files=all'], capture=True):
        fail('Файлы сайта изменились во время проверки')
    for name, (content, _, link_target) in checked_configs.items():
        path, link = AVAILABLE / (name + '.conf'), ENABLED / (name + '.conf')
        if path.is_symlink() or path.read_bytes() != content or not link.is_symlink() or os.readlink(link) != link_target:
            fail(f'Конфиг изменился перед резервной копией: {name}')
    BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='domains-', dir=BACKUPS))
    os.chmod(backup, 0o700)
    shutil.copy2(ROOT / 'scripts/rollback-domains.sh', backup / 'rollback-domains.sh')
    final = final_configs()
    metadata = {'version': 1, 'site_root': str(ROOT), 'site_sha': expected_sha,
                'entries': [], 'other_files': dict(initial_files)}
    for name, content in final.items():
        path, link = AVAILABLE / (name + '.conf'), ENABLED / (name + '.conf')
        original, info, original_link = checked_configs.get(name, (None, None, None))
        entry = {'name': name, 'path': str(path), 'link': str(link),
                 'link_target': original_link if original is not None else str(path),
                 'existed': original is not None, 'mode': stat.S_IMODE(info.st_mode) if info else 0o644,
                 'uid': info.st_uid if info else 0, 'gid': info.st_gid if info else 0,
                 'original_hash': digest(original) if original is not None else None,
                 'allowed_hashes': [digest(original) if original is not None else None, digest(content.encode())]}
        if name == NEW_NAME:
            entry['allowed_hashes'].append(digest(STAGE.encode()))
        if original is not None:
            (backup / (name + '.conf')).write_bytes(original)
        metadata['entries'].append(entry)
        metadata['other_files'].pop(str(path), None)
    (backup / 'cutover.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    print(f'Резервная копия конфигов: {backup}', flush=True)
    print(f'Откат: bash {backup}/rollback-domains.sh {backup}', flush=True)
    mutated = False
    try:
        unchanged_other_files(metadata)
        for entry in metadata['entries']:
            check_live_entry(entry)
        new_entry = next(e for e in metadata['entries'] if e['name'] == NEW_NAME)
        mutated = True
        write_config(new_entry, STAGE)
        run(['nginx', '-t'])
        run(['systemctl', 'reload', 'nginx'])
        if 'www.' + MAIN not in existing_cert:
            print('Добавление www.urbaso.ru в существующий сертификат...', flush=True)
            run(['certbot', 'certonly', '--nginx', '--non-interactive', '--cert-name', MAIN,
                 '--expand', '--preferred-challenges', 'http-01',
                 *(arg for name in CERT_NAMES for arg in ('-d', name))], timeout=600)
        if certificate_names(MAIN) != set(CERT_NAMES):
            fail('Не получен сертификат для всех четырёх имён')
        check_renewal(MAIN)
        unchanged_other_files(metadata)
        for entry in metadata['entries']:
            check_live_entry(entry)
        for entry in metadata['entries']:
            write_config(entry, final[entry['name']])
        run(['nginx', '-t'])
        run(['systemctl', 'reload', 'nginx'])
        with tempfile.TemporaryDirectory(prefix='domain-smoke-') as temporary:
            smoke(Path(temporary))
        for name in (MAIN, 'sitetops.ru', 'disiner.ru'):
            print(f'Проверка автоматического продления: {name}', flush=True)
            run(['certbot', 'renew', '--dry-run', '--cert-name', name, '--non-interactive',
                 '--no-random-sleep-on-renew'], timeout=600)
        unchanged_other_files(metadata)
        for entry in metadata['entries']:
            if digest(Path(entry['path']).read_bytes()) != digest(final[entry['name']].encode()):
                fail(f'Конфиг изменился во время проверки: {entry["name"]}')
        run(['nginx', '-t'])
        with tempfile.TemporaryDirectory(prefix='domain-smoke-') as temporary:
            smoke(Path(temporary))
        (backup / 'COMPLETED').write_text(expected_sha + '\n')
        print(f'Готово: https://urbaso.ru/\nSHA сайта: {expected_sha}\n'
              f'Откат: bash {backup}/rollback-domains.sh {backup}', flush=True)
    except BaseException:
        if mutated:
            print('Переключение не завершено; восстанавливаю nginx-конфиги.', file=sys.stderr, flush=True)
            fcntl.flock(domain_lock, fcntl.LOCK_UN)
            result = subprocess.run(['bash', str(backup / 'rollback-domains.sh'), str(backup)])
            if result.returncode:
                print(f'Автоматический откат остановлен. Сохранённая копия: {backup}', file=sys.stderr)
        raise


signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
try:
    main()
except (Exception, KeyboardInterrupt) as error:
    print(f'ОСТАНОВКА: {error or "операция прервана"}', file=sys.stderr)
    sys.exit(1)
PY
