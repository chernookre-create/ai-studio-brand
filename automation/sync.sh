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

# Раньше здесь стояло `git log origin/main..HEAD 2>/dev/null`: на ветке не main или при
# отсутствующей ссылке git падал, вывод глушился, условие выходило ложным — и скрипт молча
# не пушил, не написав в лог ни строки. Молчание выглядело как «всё отправлено» (Ф135).
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if ! git rev-parse --verify -q "origin/$BRANCH" >/dev/null; then
  echo "[$STAMP] ветка $BRANCH ещё не на GitHub — отправляю впервые"
  AHEAD=1
else
  AHEAD=$(git rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null || echo 0)
fi

if [ "$AHEAD" = "0" ]; then
  echo "[$STAMP] на GitHub уже всё"
  exit 0
fi

if git push -q origin "$BRANCH"; then
  echo "[$STAMP] отправлено на GitHub: коммитов $AHEAD"
  exit 0
fi

# Push отклонён. Самая частая причина — на GitHub есть коммит, которого нет тут.
echo "[$STAMP] push отклонён, пробую подтянуть чужие коммиты"
if git pull --rebase -q origin "$BRANCH" && git push -q origin "$BRANCH"; then
  echo "[$STAMP] отправлено после rebase: коммитов $AHEAD"
  exit 0
fi
echo "[$STAMP] ОШИБКА push. Руками: cd ~/Developer/AI-STUDIO/project && git pull --rebase && git push"
exit 1
