#!/usr/bin/env bash
# Restore the recorded checkout and the originally untracked incoming files.
set -Eeuo pipefail
export GIT_PAGER=cat
stop() { printf 'ОСТАНОВКА: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 1 ] || stop 'Использование: rollback-review.sh КАТАЛОГ_РЕЗЕРВНОЙ_КОПИИ'
backup=$(cd "$1" && pwd -P)
mapfile -t fields < <(python3 - "$backup/deployment.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
for key in ('site_root', 'previous_sha', 'previous_branch', 'target_sha', 'review_branch'):
    print(m[key])
PY
)
[ "${#fields[@]}" -eq 5 ] || stop 'Не удалось прочитать сведения об установке'
site_root=${fields[0]} previous=${fields[1]} previous_branch=${fields[2]} target=${fields[3]} review=${fields[4]}
[[ "$previous" =~ ^[0-9a-f]{40}$ && "$target" =~ ^[0-9a-f]{40}$ ]] || stop 'Некорректный SHA в сведениях об установке'
cd "$site_root"
[ "$(git rev-parse --show-toplevel)" = "$(pwd -P)" ] || stop 'Неожиданный корень репозитория'
exec 9>"$(git rev-parse --git-dir)/site-deploy.lock"
flock -n 9 || stop 'Уже выполняется другая установка или откат'
head=$(git rev-parse HEAD)
[[ "$head" == "$previous" || "$head" == "$target" ]] || stop 'После этой установки уже был другой коммит; автоматический откат остановлен'
git diff --quiet && git diff --cached --quiet || stop 'Есть изменения отслеживаемых файлов; сначала сохранить их'

# Validate the backup and every restoration destination before switching anything.
python3 - "$backup" <<'PY'
import json, pathlib, subprocess, sys
backup = pathlib.Path(sys.argv[1])
m = json.loads((backup / 'deployment.json').read_text())
root = pathlib.Path(m['site_root'])
tracked = set(subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0'))
for entry in m['conflicts']:
    saved = backup / 'untracked' / entry['path']
    live = root / entry['path']
    if not saved.exists():
        # A failed installation may have stopped before moving this file.
        if not live.is_file() or live.is_symlink():
            raise SystemExit(f'ОСТАНОВКА: файл отсутствует и на сайте, и в копии: {entry["path"]}')
        candidate = live
    else:
        candidate = saved
    if candidate.is_symlink():
        raise SystemExit(f'ОСТАНОВКА: вместо файла найдена ссылка: {candidate}')
    sha = subprocess.check_output(['git', 'hash-object', '--no-filters', '--', str(candidate)]).decode().strip()
    if sha != entry['blob']:
        raise SystemExit(f'ОСТАНОВКА: резервная копия изменилась: {candidate}')
    if entry['path'] not in tracked and (live.exists() or live.is_symlink()):
        if live.is_symlink() or not live.is_file():
            raise SystemExit(f'ОСТАНОВКА: конфликт восстановления: {live}')
        actual = subprocess.check_output(['git', 'hash-object', '--no-filters', '--', str(live)]).decode().strip()
        if actual != entry['blob']:
            raise SystemExit(f'ОСТАНОВКА: новый файл отличается, его нельзя заменить: {live}')
PY

if [ "$head" != "$previous" ]; then
  # Do not move main or erase the newer review branch. A later review can start here.
  if git show-ref --verify --quiet "refs/heads/$previous_branch" && \
     [ "$(git rev-parse "$previous_branch")" = "$previous" ]; then
    git switch --no-overwrite-ignore "$previous_branch"
  else
    git switch --no-overwrite-ignore -c "rollback/$(date +%Y%m%d-%H%M%S)-${previous:0:7}" "$previous"
  fi
fi
python3 - "$backup" <<'PY'
import json, pathlib, shutil, subprocess, sys
backup = pathlib.Path(sys.argv[1])
m = json.loads((backup / 'deployment.json').read_text())
for entry in m['conflicts']:
    destination = pathlib.Path(m['site_root']) / entry['path']
    source = backup / 'untracked' / entry['path']
    root = pathlib.Path(m['site_root'])
    for parent in destination.parents:
        if parent == root:
            break
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise SystemExit(f'ОСТАНОВКА: конфликт пути восстановления: {parent}')
    if destination.is_symlink():
        raise SystemExit(f'ОСТАНОВКА: вместо файла найдена ссылка: {destination}')
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    actual = subprocess.check_output(['git', 'hash-object', '--no-filters', '--', str(destination)]).decode().strip()
    if actual != entry['blob']:
        raise SystemExit(f'ОСТАНОВКА: восстановленный файл отличается: {destination}')
PY
[ "$(git rev-parse HEAD)" = "$previous" ] || stop 'Неожиданный HEAD после отката'
git diff --quiet && git diff --cached --quiet || stop 'Есть изменения после отката'
printf 'Восстановлен коммит: %s\nРезервная копия сохранена: %s\n' "$previous" "$backup"
git branch --show-current
git status --short
