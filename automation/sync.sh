#!/bin/bash
# Зафиксировать изменения папки проекта и отправить на GitHub.
# Вручную:   ~/Developer/AI-STUDIO/sync.sh  ["текст коммита"]
# Автоматом: раз в 5 минут через launchd (com.aistudio.autosync)
cd "$(dirname "$0")/project" || exit 1

STAMP=$(date '+%d.%m %H:%M')

# Забытый замок от прерванной операции. Живой git-процесс держит его секунды,
# так что всё старше пяти минут — мусор, и его надо убрать, иначе коммит не пройдёт.
for L in .git/index.lock .git/config.lock; do
  if [ -e "$L" ] && [ -z "$(find "$L" -mmin -5 2>/dev/null)" ]; then
    rm -f "$L" && echo "[$STAMP] снят забытый замок $L"
  fi
done

if [ -z "$(git status --porcelain)" ]; then
  echo "[$STAMP] изменений нет"
else
  N=$(git status --porcelain | wc -l | tr -d ' ')
  git add -A
  if git commit -q -m "${1:-Обновление комплекта $STAMP — файлов: $N}"; then
    echo "[$STAMP] коммит: $N файлов"
  else
    echo "[$STAMP] ОШИБКА: коммит не прошёл, изменения остались нефиксированными"
    exit 1
  fi
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "[$STAMP] GitHub не настроен — копия только локальная"
  exit 0
fi

if [ -n "$(git log origin/main..HEAD --oneline 2>/dev/null)" ]; then
  if git push -q origin HEAD; then
    echo "[$STAMP] отправлено на GitHub"
  else
    echo "[$STAMP] ОШИБКА push — проверьте авторизацию: cd ~/Developer/AI-STUDIO/project && git push"
    exit 1
  fi
fi
