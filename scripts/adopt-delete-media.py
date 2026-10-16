#!/usr/bin/env python3
"""Track the six verified uploads, without moving images/videos or changing nginx.

Run outside webroot beside install-performance-release.py from the same commit.
The target commit must already have been fetched; this script has no networking.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import sys
import tempfile

sys.dont_write_bytecode = True
# Read-only Git checks must not refresh the index before its backup is saved.
os.environ['GIT_OPTIONAL_LOCKS'] = '0'
HELPER = Path(__file__).resolve().with_name('install-performance-release.py')
spec = importlib.util.spec_from_file_location('performance_release', HELPER)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
BASELINE = '7a19d1a5f869acf932346adb7e32f6c7b94c05ea'
IMAGES = {
    'delete/astra/1.jpg': '1a4b9163da44c871fb33a2698da2bc59d40f6a51c77ec2324adcbfaa7eb0caa5',
    'delete/astra/2.jpg': 'b7d7be94f0b0adfcfb4d05923f0cd892cb6d9854e4341d9e868f5e6186fca9a6',
    'delete/astra/3.jpg': '5261cbb47279f22baccd59bc6b592c3216ce25d112cf7859938590318befd17d',
    'delete/astra/5.png': 'fddf654adba78188a7fd546a159969eee41058d7997c69231ef7aea1b3699dcb',
    'delete/astra/6.png': '195108713866d0c980ac32caed444be260fe909b4bb8aa92c6e9dd5c1fa5effb',
    'delete/astra/7.jpg': 'a6b38deb64c1f850e5905fb95418174d6e8efcc8df4355e04f25d144e5ac8245',
}
OTHER = {'.gitignore', 'delete/README.md', 'docs/delete-media.md',
         'scripts/configure-delete-media.py', 'scripts/adopt-delete-media.py'}
ALLOWED = set(IMAGES) | OTHER


def git(*args):
    return base.git(base.SITE_ROOT, '-c', 'diff.autoRefreshIndex=false', *args).stdout


def out(*args):
    return git(*args).decode().strip()


def dirty(*args):
    result = base.git(base.SITE_ROOT, '-c', 'diff.autoRefreshIndex=false', 'diff', '--quiet', *args, check=False)
    if result.returncode not in (0, 1):
        base.fail(result.stderr.decode(errors='replace'))
    return result.returncode == 1


def clean():
    if dirty('HEAD', '--') or dirty('--cached'):
        base.fail('Есть изменения отслеживаемых файлов или индекса')


def tree(commit):
    result = {}
    for row in git('ls-tree', '-r', '-z', commit).split(b'\0'):
        if row:
            header, path = row.split(b'\t', 1)
            mode, kind, blob = header.decode().split()
            result[os.fsdecode(path)] = (mode, kind, blob)
    return result


def safe_path(name):
    path = base.SITE_ROOT / name
    for parent in (path, *path.parents):
        if parent == base.SITE_ROOT:
            break
        if parent.is_symlink() or (parent.exists() and parent != path and not parent.is_dir()):
            base.fail('Неожиданный путь или ссылка: ' + str(parent))
    if path.exists() and not path.is_file():
        base.fail('Ожидался обычный файл: ' + str(path))
    return path


def file_state(path):
    info = path.stat()
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid]


def media_state():
    images = {}
    for name, digest in IMAGES.items():
        path = safe_path(name)
        if not path.is_file() or base.sha(path.read_bytes()) != digest:
            base.fail('Исходное изображение отсутствует или изменилось: ' + name)
        images[name] = file_state(path)
    directory = base.SITE_ROOT / 'delete/astra/video'
    if directory.is_symlink() or not directory.is_dir():
        base.fail('Не найден обычный каталог исходных видео')
    videos = {}
    for path in sorted(directory.rglob('*')):
        name = path.relative_to(base.SITE_ROOT).as_posix()
        if path.is_symlink():
            base.fail('Ссылка в каталоге видео: ' + name)
        if not path.is_dir():
            safe_path(name)
            videos[name] = file_state(path)
    if 'delete/astra/video/video3.mp4' not in videos:
        base.fail('Не найден video3.mp4')
    return {'images': images, 'videos': videos}


def unchanged(state):
    if media_state() != state['media']:
        base.fail('Изменилось наличие, содержимое или состояние исходных медиа')
    if base.preserved_index_entry(base.SITE_ROOT, BASELINE, state['target']) != state['preserved']:
        base.fail('Изменились флаг S или сохраняемый файл')


def validate_target(target):
    base.validate_sha(target)
    git('merge-base', '--is-ancestor', BASELINE, target)
    changed = base.names(git('diff', '--name-only', '-z', BASELINE, target))
    if changed != ALLOWED:
        base.fail('Коммит должен менять только согласованные медиа и пять служебных файлов')
    old, new = tree(BASELINE), tree(target)
    for name in ALLOWED:
        if new.get(name, ())[:2] != ('100644', 'blob'):
            base.fail('Неожиданный тип/режим целевого файла: ' + name)
    for name, digest in IMAGES.items():
        if name in old or base.sha(git('cat-file', 'blob', new[name][2])) != digest:
            base.fail('Целевой Git blob не совпадает с оригиналом: ' + name)
    if old['index.html'] != new['index.html']:
        base.fail('Главная страница не должна изменяться')
    return old, new


def rollback(backup):
    raw = (backup / 'adoption.json').read_bytes()
    if base.sha(raw) != (backup / 'adoption.sha256').read_text().strip():
        base.fail('Повреждены сведения резервной копии')
    state = json.loads(raw)
    if state.get('kind') != 'delete-media-adoption-v1' or state.get('baseline') != BASELINE:
        base.fail('Неизвестная резервная копия')
    old, new = validate_target(state['target'])
    current = out('rev-parse', 'HEAD')
    if current not in {BASELINE, state['target']} or base.git(base.SITE_ROOT, 'symbolic-ref', '-q', 'HEAD', check=False).returncode == 0:
        base.fail('HEAD изменился после установки; автоматический откат остановлен')
    unchanged(state)
    index = backup / 'index.before'
    if index.is_symlink() or base.sha(index.read_bytes()) != state['index_sha256']:
        base.fail('Повреждена резервная копия индекса')
    # Accept clean installation or an interrupted install/rollback, but only
    # when every affected index/file entry is an exact known old/new version.
    outside = ['.', *(':(exclude,literal)' + name for name in sorted(ALLOWED))]
    if dirty('--', *outside) or dirty('--cached', BASELINE, '--', *outside):
        base.fail('Есть посторонние изменения; откат остановлен')
    for row in git('ls-files', '--stage', '-z').split(b'\0'):
        if not row:
            continue
        header, path = row.split(b'\t', 1)
        name = os.fsdecode(path)
        if name in ALLOWED:
            mode, blob, stage = header.decode().split()
            if stage != '0' or (mode, 'blob', blob) not in {old.get(name), new.get(name)}:
                base.fail('Неизвестное изменение индекса: ' + name)
    existing = []
    for name in sorted(OTHER):
        path = safe_path(name)
        if path.exists():
            if path.read_bytes() not in [git('cat-file', 'blob', entry[2]) for entry in (old.get(name), new.get(name)) if entry]:
                base.fail('Служебный файл изменён после установки: ' + name)
            existing.append(name)
        elif name in old:
            base.fail('Прежний файл отсутствует: ' + name)
    # Stage only the verified non-media files so restore also handles an
    # interrupted checkout which created a file before committing its index.
    if existing:
        git('add', '--', *existing)
    tracked = base.names(git('ls-files', '-z'))
    restore_paths = sorted(OTHER & (tracked | set(old)))
    if restore_paths:
        git('restore', '--source=' + BASELINE, '--staged', '--worktree', '--', *restore_paths)
    adopted = sorted(set(IMAGES) & tracked)
    if adopted:
        git('rm', '--cached', '--', *adopted)
    if out('write-tree') != out('rev-parse', BASELINE + '^{tree}'):
        base.fail('Индекс не совпал с исходным деревом; HEAD не изменён')
    unchanged(state)
    git('update-ref', '--no-deref', '-m', 'Restore delete media baseline', 'HEAD', BASELINE, current)
    # Restore the original flags/stat cache byte-for-byte under Git's own lock.
    git_dir = Path(out('rev-parse', '--absolute-git-dir'))
    lock = git_dir / 'index.lock'
    stream = lock.open('xb')
    identity = os.fstat(stream.fileno()).st_ino
    try:
        with stream:
            stream.write(index.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(lock, stat.S_IMODE(index.stat().st_mode))
        os.replace(lock, git_dir / 'index')
    except BaseException:
        if lock.exists() and lock.lstat().st_ino == identity:
            lock.unlink()
        raise
    unchanged(state)
    (backup / 'ROLLED_BACK').write_text(BASELINE + '\n')
    print('Восстановлен прежний detached HEAD. Изображения снова вне Git; оригиналы и видео сохранены.')


def install(target):
    old, new = validate_target(target)
    if out('rev-parse', 'HEAD') != BASELINE or base.git(base.SITE_ROOT, 'symbolic-ref', '-q', 'HEAD', check=False).returncode == 0:
        base.fail('Требуется исходный detached HEAD ' + BASELINE)
    clean()
    for name in ALLOWED:
        path = safe_path(name)
        if name not in old and name not in IMAGES and os.path.lexists(path):
            base.fail('Нельзя заменить существующий файл вне Git: ' + name)
    state = {'kind': 'delete-media-adoption-v1', 'baseline': BASELINE, 'target': target,
             'media': media_state(), 'preserved': base.preserved_index_entry(base.SITE_ROOT, BASELINE, target)}
    git_dir = Path(out('rev-parse', '--absolute-git-dir'))
    destination = base.BACKUP_ROOT.resolve()
    base.outside(destination, base.SITE_ROOT.resolve())
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='delete-media-git-', dir=destination))
    for path in (Path(__file__).resolve(), HELPER):
        shutil.copy2(path, backup / path.name)
    shutil.copy2(git_dir / 'index', backup / 'index.before')
    shutil.copy2(git_dir / 'HEAD', backup / 'HEAD.before')
    state['index_sha256'] = base.sha((backup / 'index.before').read_bytes())
    raw = (json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode()
    (backup / 'adoption.json').write_bytes(raw)
    (backup / 'adoption.sha256').write_text(base.sha(raw) + '\n')
    print('Резервная копия:', backup, flush=True)
    print(f'Откат: python3 {backup}/adopt-delete-media.py --rollback {backup}', flush=True)
    try:
        unchanged(state)
        if out('rev-parse', 'HEAD') != BASELINE:
            base.fail('Состояние Git изменилось до установки')
        clean()
        git('add', '--', *sorted(IMAGES))
        for name in IMAGES:
            if git('ls-files', '--stage', '-z', '--', name) != f'100644 {new[name][2]} 0\t{name}\0'.encode():
                base.fail('Добавленный индекс не совпал с Git blob: ' + name)
        unchanged(state)
        git('switch', '--no-overwrite-ignore', '--detach', target)
        if out('rev-parse', 'HEAD') != target:
            base.fail('Не прошла проверка установленного состояния')
        clean()
        unchanged(state)
        (backup / 'COMPLETED').write_text(target + '\n')
        print('Шесть исходных изображений отслеживаются Git. Видео, файлы медиа и nginx не изменялись.')
        print('HEAD:', target)
    except BaseException:
        print('Установка не завершилась; восстанавливаю прежнее состояние Git.', file=sys.stderr, flush=True)
        rollback(backup)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', nargs='?')
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    if bool(args.target) == bool(args.rollback):
        parser.error('укажите целевой SHA либо --rollback КАТАЛОГ')
    if os.geteuid() != 0:
        base.fail('Запускать от root на VPS')
    base.outside(Path(__file__).resolve(), base.SITE_ROOT.resolve())
    with base.check_repo(base.SITE_ROOT):
        if args.rollback:
            backup = args.rollback.resolve(strict=True)
            if backup.parent != base.BACKUP_ROOT.resolve() or not backup.name.startswith('delete-media-git-'):
                base.fail('Неожиданный каталог резервной копии')
            rollback(backup)
        else:
            install(args.target)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(f'ОСТАНОВКА: {error or "операция прервана"}', file=sys.stderr)
        sys.exit(1)
