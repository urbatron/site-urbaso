#!/usr/bin/env python3
"""Download a pinned performance release from GitHub and run its guarded installer.

Run this copy outside the public webroot. The download is kept in /root; the
existing site is changed only by install-performance-release.py after its checks.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile

BRANCH = 'codex/performance-pagespeed-20261011'
SOURCE = 'git@github.com:urbatron/site-urbaso.git'
ORIGINAL = '22fc0324edce4f4fec3ecf7bc65ff75a8e823cb9'
PUBLISHED_CODE = '790642c73c8dec2d5fd7e72944ef97ea15dceab0'
PUBLISHED_INSTALLER = 'db29fe35b793d415e5dd77e04774ab5394086c74'
BASELINE_INDEX_SHA256 = 'b7d49ffe13355047a76f2e6fe040b44f2b81b22cf0b3b8a3e80126fdeddd2e81'
KEY = Path('/root/.ssh/id_ed25519_site_urbaso_repo')
DOWNLOAD_ROOT = Path('/root')
SITE_ROOT = Path('/opt/legacy-stack/sites/sweb/site.urbaso.ru/public_html')


def commit_sha(value):
    if not re.fullmatch(r'[0-9a-f]{40}', value):
        raise argparse.ArgumentTypeError('Нужен полный SHA из 40 строчных шестнадцатеричных символов.')
    return value


def prepare(directory, source, branch, target, baseline, environment):
    subprocess.run(['git', 'check-ref-format', 'refs/heads/' + branch], check=True)
    repo = directory / 'repository.git'
    subprocess.run(['git', 'clone', '--bare', '--single-branch', '--branch', branch,
                    source, str(repo)], env=environment, check=True)

    def git(*arguments):
        return subprocess.check_output(['git', '-C', str(repo), *arguments])

    if git('rev-parse', 'HEAD').decode().strip() != target:
        raise RuntimeError('Ветка изменилась: установка остановлена до изменения сайта.')
    for child, parent in ((target, PUBLISHED_INSTALLER), (PUBLISHED_INSTALLER, PUBLISHED_CODE),
                          (PUBLISHED_CODE, baseline), (baseline, ORIGINAL)):
        if git('rev-list', '--parents', '-n', '1', child).decode().split() != [child, parent]:
            raise RuntimeError('Не совпадает линейная цепочка коммитов релиза: ' + child)
    if git('diff', '--name-only', '-z', ORIGINAL, baseline) != b'index.html\0':
        raise RuntimeError('Исходный коммит должен сохранять только прежнее изменение index.html.')
    if hashlib.sha256(git('show', baseline + ':index.html')).hexdigest() != BASELINE_INDEX_SHA256:
        raise RuntimeError('Исходный index.html не совпадает с сохранённой установкой Метрики.')
    git('bundle', 'create', str(directory / 'release.bundle'), 'HEAD')
    for filename, source_name in [('install-performance-release.py', 'install-performance-release.py'),
                                  ('configure-performance.py', 'configure-performance.py'),
                                  ('install.py', 'install-performance.py')]:
        (directory / filename).write_bytes(git('show', target + ':scripts/' + source_name))
    files = ['release.bundle', 'install-performance-release.py', 'configure-performance.py', 'install.py']
    manifest = dict(project='urbatron/site-urbaso', originalCommit=ORIGINAL,
                    baselineCommit=baseline, targetCommit=target,
                    filesSha256={name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in files})
    (directory / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=commit_sha, required=True, help='Проверенный SHA релиза в GitHub')
    parser.add_argument('--baseline', type=commit_sha, required=True, help='SHA исходного состояния с Метрикой')
    parser.add_argument('--branch', default=BRANCH, help='Ветка с проверенным релизом')
    args = parser.parse_args(argv)
    if os.geteuid() != 0 or socket.gethostname() != 'urbaserge3-vps-1':
        raise RuntimeError('Запустите от root на сервере urbaserge3-vps-1.')
    location = Path(__file__).resolve()
    if SITE_ROOT.resolve() in location.parents:
        raise RuntimeError('Запустите скачанную копию вне публичного каталога сайта, например в /root.')
    if not KEY.is_file():
        raise RuntimeError('Не найден SSH-ключ репозитория: ' + str(KEY))
    environment = dict(os.environ, GIT_TERMINAL_PROMPT='0',
                       GIT_SSH_COMMAND='ssh -i ' + str(KEY) + ' -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes')
    directory = Path(tempfile.mkdtemp(prefix='urbaso-performance-', dir=DOWNLOAD_ROOT))
    print('Папка установки:', directory, flush=True)
    prepare(directory, SOURCE, args.branch, args.target, args.baseline, environment)
    subprocess.run([sys.executable, str(directory / 'install.py')], check=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Exception, KeyboardInterrupt) as error:
        print('ОСТАНОВКА: ' + str(error or 'операция прервана'), file=sys.stderr)
        sys.exit(1)
