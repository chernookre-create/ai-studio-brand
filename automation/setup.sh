#!/bin/bash
# Установка окружения замеров. Одна команда на чистой машине:
#
#     bash automation/setup.sh
#
# Создаёт .venv внутри комплекта и ставит туда библиотеки из requirements.txt.
# .venv в .gitignore — на GitHub не уезжает, у каждого свой.
#
#     bash automation/setup.sh --версии    что реально встало
#     bash automation/setup.sh --проверка  прогнать selftest в этом окружении
set -u
cd "$(dirname "$0")/.." || exit 1
VENV=".venv"
PY="$VENV/bin/python"

if [ "${1:-}" = "--версии" ]; then
  [ -x "$PY" ] || { echo "окружения нет — сначала bash automation/setup.sh"; exit 1; }
  "$PY" -m pip freeze
  exit 0
fi

if [ "${1:-}" = "--проверка" ]; then
  [ -x "$PY" ] || { echo "окружения нет — сначала bash automation/setup.sh"; exit 1; }
  exec "$PY" tools/selftest.py
fi

echo "python сборки: $(python3 -V 2>&1)"

if [ ! -x "$PY" ]; then
  echo "создаю $VENV"
  python3 -m venv "$VENV" || { echo "ОШИБКА: не создался venv"; exit 1; }
fi

"$PY" -m pip install -q --upgrade pip setuptools wheel || { echo "ОШИБКА: pip не обновился"; exit 1; }

# numpy и Cython ставятся первыми: insightface собирается из исходников и без них
# падает на этапе сборки, а не установки — сообщение при этом невнятное.
"$PY" -m pip install -q numpy Cython || { echo "ОШИБКА: не встали numpy/Cython"; exit 1; }

if ! "$PY" -m pip install -r requirements.txt; then
  echo
  echo "ОШИБКА: не все библиотеки встали. Что именно — видно выше."
  echo "Комплект без них работает частично: структурные проверки идут, замеры нет."
  exit 1
fi

echo
echo "готово. Проверка:  bash automation/setup.sh --проверка"
