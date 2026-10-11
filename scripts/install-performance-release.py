#!/usr/bin/env python3
"""Install a reviewed local Git bundle without moving any branch or contacting GitHub.

Run this file from outside the public webroot. Rollback restores the old checkout
and, if present, the byte-for-byte known pre-release Metrika edit to index.html.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.request

SITE_ROOT = Path('/opt/legacy-stack/sites/sweb/site.urbaso.ru/public_html')
BACKUP_ROOT = Path('/root/backups/site.urbaso.ru')
ORIGINS = {
    'git@github.com:urbatron/site-urbaso.git',
    'https://github.com/urbatron/site-urbaso.git',
    'https://github.com/urbatron/site-urbaso',
}


def fail(message):
    raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args, check=True):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=False)
    if check and result.returncode:
        fail(result.stderr.decode(errors='replace').strip() or 'Ошибка Git: ' + ' '.join(args))
    return result


def out(root, *args):
    return git(root, *args).stdout.decode().strip()


def names(raw):
    return {os.fsdecode(value) for value in raw.split(b'\0') if value}


def validate_sha(value):
    if not re.fullmatch(r'[0-9a-f]{40}', value):
        fail('Нужен полный SHA из 40 строчных шестнадцатеричных символов')
    return value


def outside(path, root):
    if path == root or root in path.parents:
        fail(f'Этот путь должен находиться вне webroot: {path}')


def check_repo(root):
    if out(root, 'rev-parse', '--show-toplevel') != str(root):
        fail('Каталог сайта не совпадает с корнем Git-репозитория')
    if out(root, 'config', '--get', 'remote.origin.url') not in ORIGINS:
        fail('Неожиданный remote.origin.url, нужен urbatron/site-urbaso')
    for row in git(root, 'ls-files', '-v', '-z').stdout.split(b'\0'):
        if row and row[:1] != b'H':
            fail('В индексе есть специальные флаги или конфликт; требуется ручная проверка')
    git_dir = Path(out(root, 'rev-parse', '--absolute-git-dir'))
    for name in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply', 'index.lock'):
        if (git_dir / name).exists():
            fail('В Git уже выполняется другая операция: ' + name)
    lock = (git_dir / 'site-deploy.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fail('Уже выполняется другая установка или откат')
    return lock


def clean_index(root):
    if git(root, 'diff', '--cached', '--quiet', check=False).returncode:
        fail('Есть staged-изменения; сначала требуется их отдельный разбор')


def changed(root):
    return names(git(root, 'diff', '--name-only', '-z', 'HEAD', '--').stdout)


def check_collisions(root, target):
    tracked = names(git(root, 'ls-files', '-z').stdout)
    incoming = names(git(root, 'ls-tree', '-r', '--name-only', '-z', target).stdout)
    for name in sorted(incoming - tracked):
        destination = root / name
        if os.path.lexists(destination):
            fail('Нельзя заменить существующий файл или каталог вне Git: ' + name)
        for parent in destination.parents:
            if parent == root:
                break
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                fail('Неизвестный файл или ссылка перекрывает путь: ' + str(parent))


def copy_atomic(source, destination):
    handle, temporary = tempfile.mkstemp(prefix='.performance-restore-', dir=destination.parent)
    os.close(handle)
    temporary = Path(temporary)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def rollback_command(backup):
    return 'python3 ' + shlex.quote(str(backup / 'install-performance-release.py')) + ' rollback ' + shlex.quote(str(backup))


def load_state(backup):
    raw = (backup / 'deployment.json').read_bytes()
    if sha(raw) != (backup / 'deployment.sha256').read_text().strip():
        fail('Контрольная сумма deployment.json не совпадает')
    state = json.loads(raw)
    for key in ('previous_sha', 'baseline_sha', 'target_sha'):
        validate_sha(state[key])
    for name, expected in state['backup_files'].items():
        if name not in ('index.before.html', 'install-performance-release.py'):
            fail('Неизвестный файл в метаданных резервной копии')
        path = backup / name
        if path.is_symlink() or not path.is_file() or sha(path.read_bytes()) != expected:
            fail('Повреждена резервная копия: ' + name)
    return state


def restore(root, backup, state):
    clean_index(root)
    current = out(root, 'rev-parse', 'HEAD')
    if current not in (state['previous_sha'], state['target_sha']):
        fail('После установки появился другой коммит; автоматический откат остановлен')
    dirty = changed(root)
    saved = backup / 'index.before.html'
    # Repeated rollback is safe, including the original known Metrika edit.
    restored_index = (not (root / 'index.html').is_symlink()
                      and (root / 'index.html').is_file()
                      and sha((root / 'index.html').read_bytes()) == state['backup_files']['index.before.html'])
    if dirty and not (current == state['previous_sha'] and dirty == {'index.html'} and restored_index):
        fail('Файлы изменились после установки; сначала сохраните и разберите изменения')
    check_collisions(root, state['previous_sha'])
    if current != state['previous_sha']:
        branch = state['previous_branch']
        ref = 'refs/heads/' + branch if branch else ''
        exists = git(root, 'show-ref', '--verify', '--quiet', ref, check=False).returncode == 0 if ref else False
        if exists and out(root, 'rev-parse', ref) == state['previous_sha']:
            git(root, 'switch', '--no-overwrite-ignore', branch)
        else:
            git(root, 'switch', '--no-overwrite-ignore', '--detach', state['previous_sha'])
    if not restored_index or current != state['previous_sha']:
        copy_atomic(saved, root / 'index.html')
    if out(root, 'rev-parse', 'HEAD') != state['previous_sha']:
        fail('После отката получен неожиданный HEAD')
    expected_changes = {'index.html'} if state['known_metrika_edit'] else set()
    if changed(root) != expected_changes or sha((root / 'index.html').read_bytes()) != state['backup_files']['index.before.html']:
        fail('Проверка восстановленного состояния не пройдена')
    print('Восстановлен исходный код, включая Метрику. HEAD:', state['previous_sha'])


def install(args, root):
    bundle = args.bundle.resolve(strict=True)
    outside(bundle, root)
    backup_root = args.backup_root.resolve()
    outside(backup_root, root)
    baseline, target = validate_sha(args.baseline), validate_sha(args.target)
    clean_index(root)
    # This only imports objects. No local branch, remote branch or origin is updated.
    git(root, 'bundle', 'verify', str(bundle))
    git(root, 'bundle', 'unbundle', str(bundle))
    for commit in (baseline, target):
        if out(root, 'rev-parse', commit + '^{commit}') != commit:
            fail('SHA не является коммитом: ' + commit)
    git(root, 'merge-base', '--is-ancestor', baseline, target)
    previous = out(root, 'rev-parse', 'HEAD')
    parents = out(root, 'rev-list', '--parents', '-n', '1', baseline).split()
    if len(parents) != 2:
        fail('Baseline должен иметь ровно один исходный родительский коммит')
    parent = parents[1]
    if previous not in (baseline, parent) or target == previous:
        fail('Текущий HEAD не совпадает с ожидаемым состоянием до установки')
    if names(git(root, 'diff', '--name-only', '-z', parent, baseline).stdout) != {'index.html'}:
        fail('Baseline должен сохранять только прежнее изменение index.html с Метрикой')
    if git(root, '-c', 'core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol', 'diff', '--check', previous, target, check=False).returncode:
        fail('Целевой Git diff не прошёл проверку пробельных ошибок')
    index = root / 'index.html'
    if index.is_symlink() or not index.is_file():
        fail('index.html не является обычным файлом')
    original = index.read_bytes()
    dirty = changed(root)
    known_edit = dirty == {'index.html'} and previous == parent and original == git(root, 'show', baseline + ':index.html').stdout
    if dirty and not known_edit:
        fail('Есть неизвестные изменения отслеживаемых файлов; ничего не установлено')
    # A clean old HEAD would remove an expected production counter on rollback.
    if previous == parent and not known_edit:
        fail('В исходном index.html нет ожидаемой сохранённой установки Метрики')
    check_collisions(root, target)
    branch = out(root, 'branch', '--show-current')
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='performance-code-', dir=backup_root))
    os.chmod(backup, 0o700)
    shutil.copy2(index, backup / 'index.before.html')
    shutil.copy2(Path(__file__).resolve(), backup / 'install-performance-release.py')
    state = dict(site_root=str(root), previous_sha=previous, previous_branch=branch,
                 baseline_sha=baseline, target_sha=target, known_metrika_edit=known_edit,
                 bundle_sha256=sha(bundle.read_bytes()),
                 backup_files={name: sha((backup / name).read_bytes()) for name in ('index.before.html', 'install-performance-release.py')})
    raw = (json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode()
    (backup / 'deployment.json').write_bytes(raw)
    (backup / 'deployment.sha256').write_text(sha(raw) + '\n')
    refs = 'refs/backups/' + backup.name
    git(root, 'update-ref', refs + '/before', previous)
    git(root, 'update-ref', refs + '/baseline', baseline)
    git(root, 'update-ref', refs + '/release', target)
    print('Резервная копия:', backup, flush=True)
    print('Откат:', rollback_command(backup), flush=True)
    # Re-check immediately before the first write to the live checkout.
    clean_index(root)
    if out(root, 'rev-parse', 'HEAD') != previous or changed(root) != dirty or index.read_bytes() != original:
        fail('Состояние изменилось во время подготовки. Код не установлен')
    check_collisions(root, target)
    try:
        if known_edit:
            git(root, 'restore', '--source=HEAD', '--worktree', '--', 'index.html')
        git(root, 'switch', '--no-overwrite-ignore', '--detach', target)
        clean_index(root)
        if out(root, 'rev-parse', 'HEAD') != target or changed(root):
            fail('После установки состояние Git не совпадает с целевым')
        url = args.site_url.rstrip('/') + '/?performance=' + target
        request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache', 'Accept-Encoding': 'identity'})
        with urllib.request.urlopen(request, timeout=30) as response:
            published = response.read()
        if published != index.read_bytes():
            fail('Публичный index.html не совпадает с установленным')
        print('Установлен и проверен код:', target)
        print('Указатели веток не изменены; текущий checkout находится в detached HEAD.')
    except BaseException:
        print('Ошибка установки. Выполняется возврат прежнего кода.', file=sys.stderr, flush=True)
        try:
            restore(root, backup, state)
        except Exception as error:
            print('Автоматический возврат остановлен: ' + str(error), file=sys.stderr)
            print('Команда повторного отката: ' + rollback_command(backup), file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    deploy = commands.add_parser('install')
    deploy.add_argument('bundle', type=Path)
    deploy.add_argument('target')
    deploy.add_argument('baseline')
    deploy.add_argument('--site-root', type=Path, default=SITE_ROOT)
    deploy.add_argument('--backup-root', type=Path, default=BACKUP_ROOT)
    deploy.add_argument('--site-url', default='https://urbaso.ru')
    rollback = commands.add_parser('rollback')
    rollback.add_argument('backup', type=Path)
    args = parser.parse_args()
    state = None
    if args.command == 'rollback':
        backup = args.backup.resolve(strict=True)
        state = load_state(backup)
        root = Path(state['site_root']).resolve(strict=True)
        outside(backup, root)
    else:
        root = args.site_root.resolve(strict=True)
    outside(Path(__file__).resolve(), root)
    lock = check_repo(root)
    try:
        if state:
            restore(root, backup, state)
        else:
            install(args, root)
    finally:
        lock.close()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        main()
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError, KeyboardInterrupt) as error:
        print('ОСТАНОВКА: ' + str(error), file=sys.stderr)
        sys.exit(1)
