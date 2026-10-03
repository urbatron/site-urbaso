#!/usr/bin/env bash
# Install an exact, reviewed commit on the existing VPS. Never push or merge main.
set -Eeuo pipefail
export GIT_PAGER=cat

SITE_ROOT=${SITE_ROOT:-/opt/legacy-stack/sites/sweb/site.urbaso.ru/public_html}
BACKUP_ROOT=${BACKUP_ROOT:-/root/backups/site.urbaso.ru}
SITE_URL=${SITE_URL:-https://site.urbaso.ru}
DEPLOY_KEY=${DEPLOY_KEY:-/root/.ssh/id_ed25519_site_urbaso_repo}

stop() { printf 'ОСТАНОВКА: %s\n' "$*" >&2; exit 1; }
on_exit() {
  status=$?
  if [ "$status" -ne 0 ] && [ -n "${backup:-}" ] && [ -f "$backup/deployment.json" ]; then
    printf '\nУстановка не завершена. Сведения для восстановления: %s\n' "$backup" >&2
    printf 'Для отката: bash %q %q\n' "$backup/rollback-review.sh" "$backup" >&2
  fi
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
[ "$#" -eq 3 ] || stop 'Использование: deploy-review.sh ВЕТКА ЦЕЛЕВОЙ_SHA ТЕКУЩИЙ_SHA'
review=$1 target=$2 previous=$3
[[ "$target" =~ ^[0-9a-f]{40}$ && "$previous" =~ ^[0-9a-f]{40}$ ]] || stop 'Нужны полные SHA коммитов'
git check-ref-format --branch "$review" >/dev/null
[[ "$review" == codex/* ]] || stop 'Рабочая ветка должна начинаться с codex/'
cd "$SITE_ROOT"
[ "$(git rev-parse --show-toplevel)" = "$(pwd -P)" ] || stop 'Каталог не совпадает с корнем репозитория'
python3 - "$BACKUP_ROOT" <<'PY'
import pathlib, sys
site = pathlib.Path.cwd().resolve()
backup = pathlib.Path(sys.argv[1]).resolve()
if backup == site or site in backup.parents:
    raise SystemExit('ОСТАНОВКА: резервная копия должна находиться вне каталога сайта')
PY
case "$(git config --get remote.origin.url)" in
  git@github.com:urbatron/site-urbaso.git|https://github.com/urbatron/site-urbaso.git|https://github.com/urbatron/site-urbaso) ;;
  *) stop 'Неожиданный origin' ;;
esac
exec 9>"$(git rev-parse --git-dir)/site-deploy.lock"
flock -n 9 || stop 'Уже выполняется другая установка или откат'
current_branch=$(git branch --show-current)
[[ "$current_branch" == main || "$current_branch" == "$review" || "$current_branch" == rollback/* ]] || stop 'Неожиданная текущая ветка'
[ "$(git rev-parse HEAD)" = "$previous" ] || stop 'На сервере другой текущий коммит'
git diff --quiet && git diff --cached --quiet || stop 'Есть изменения отслеживаемых файлов; сначала сохранить и разобрать их'

git_remote() {
  GIT_SSH_COMMAND="ssh -o IdentitiesOnly=yes -i $DEPLOY_KEY -o StrictHostKeyChecking=yes" git "$@"
}
git_remote fetch --no-tags origin "refs/heads/$review:refs/remotes/origin/$review"
[ "$(git rev-parse "refs/remotes/origin/$review")" = "$target" ] || stop 'В удалённой рабочей ветке другой коммит'
git merge-base --is-ancestor "$previous" "$target" || stop 'Обновление не является fast-forward'
# The previous checkout may not yet have .gitattributes for the CRLF vCard.
git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol diff --check "$previous" "$target"
if git show-ref --verify --quiet "refs/heads/$review"; then
  git merge-base --is-ancestor "$review" "$target" || stop 'Локальная рабочая ветка разошлась с целевой'
fi
[ "$(git rev-parse HEAD)" = "$previous" ] || stop 'HEAD изменился во время проверки'
git diff --quiet && git diff --cached --quiet || stop 'Файлы изменились во время проверки'

mkdir -p "$BACKUP_ROOT"
backup=$(mktemp -d "$BACKUP_ROOT/review-$(date +%Y%m%d-%H%M%S)-XXXXXX")
# Keep the rollback executable outside the checkout so switching commits cannot remove it.
git show "$target:scripts/rollback-review.sh" > "$backup/rollback-review.sh"
python3 - "$target" "$previous" "$current_branch" "$review" "$backup" <<'PY'
import json, os, pathlib, stat, subprocess, sys
target, previous, previous_branch, review, destination = sys.argv[1:]
root = pathlib.Path.cwd()
backup = pathlib.Path(destination)
def git(*args):
    return subprocess.check_output(['git', *args])
tracked = set(git('ls-files', '-z').split(b'\0'))
conflicts = []
for row in git('ls-tree', '-rz', target).split(b'\0'):
    if not row:
        continue
    header, raw_path = row.split(b'\t', 1)
    mode, kind, blob = header.split()
    if raw_path in tracked:
        continue
    path = root / os.fsdecode(raw_path)
    # Never traverse a server symlink or replace an existing directory with a file.
    for parent in path.parents:
        if parent == root:
            break
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise SystemExit(f'ОСТАНОВКА: конфликт пути: {parent}')
    if not path.exists() and not path.is_symlink():
        continue
    if kind != b'blob' or mode not in (b'100644', b'100755') or not stat.S_ISREG(path.lstat().st_mode):
        raise SystemExit(f'ОСТАНОВКА: требуется ручной разбор: {path}')
    actual = git('hash-object', '--no-filters', '--', str(path)).strip()
    if actual != blob:
        raise SystemExit(f'ОСТАНОВКА: файл вне Git отличается от целевого: {path}')
    conflicts.append({'path': os.fsdecode(raw_path), 'blob': blob.decode()})
metadata = dict(site_root=str(root), previous_sha=previous, previous_branch=previous_branch,
                target_sha=target, review_branch=review, conflicts=conflicts)
(backup / 'deployment.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
print(f'Проверено совпадающих файлов вне Git: {len(conflicts)}')
PY

# All collisions were checked before moving the first file. Unrelated files stay in place.
python3 - "$backup" <<'PY'
import json, pathlib, shutil, subprocess, sys
backup = pathlib.Path(sys.argv[1])
metadata = json.loads((backup / 'deployment.json').read_text())
for entry in metadata['conflicts']:
    source = pathlib.Path(metadata['site_root']) / entry['path']
    actual = subprocess.check_output(['git', 'hash-object', '--no-filters', '--', str(source)]).decode().strip()
    if source.is_symlink() or actual != entry['blob']:
        raise SystemExit(f'ОСТАНОВКА: файл изменился после проверки: {source}')
    destination = backup / 'untracked' / entry['path']
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
PY

# The ancestor check above makes this a fast-forward of the local review branch.
# One switch avoids publishing an older intermediate branch head. -C moves only
# this checked review reference; it does not discard working files or force-push.
git switch --no-overwrite-ignore -C "$review" "$target"
git branch --set-upstream-to="origin/$review" "$review" >/dev/null
[ "$(git rev-parse HEAD)" = "$target" ] || stop 'После установки получен другой HEAD'
[ "$(git branch --show-current)" = "$review" ] || stop 'После установки получена другая ветка'
git diff --quiet && git diff --cached --quiet || stop 'После установки появились изменения отслеживаемых файлов'
python3 - "$backup" <<'PY'
import json, pathlib, subprocess, sys
metadata = json.loads((pathlib.Path(sys.argv[1]) / 'deployment.json').read_text())
for entry in metadata['conflicts']:
    actual = subprocess.check_output(['git', 'hash-object', '--no-filters', '--', entry['path']]).decode().strip()
    if actual != entry['blob']:
        raise SystemExit(f"ОСТАНОВКА: изменились байты изображения: {entry['path']}")
PY
curl --fail --silent --show-error --connect-timeout 10 --max-time 30 \
  "$SITE_URL/?review=$target" -o "$backup/published-index.html"
cmp -s index.html "$backup/published-index.html" || stop 'Сайт отдаёт другую версию index.html; проверь кэш или откати установку'
printf '\nУстановлено: %s\nВетка: %s\nПроверка: %s/\nОткат: bash %q %q\n' \
  "$target" "$review" "$SITE_URL" "$backup/rollback-review.sh" "$backup"
git status --short
