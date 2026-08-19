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

# Ставим по одной, а не списком. Разом pip уходит в перебор версий и молчит
# минутами, а потом печатает стену текста, из которой не видно, что именно не встало.
# По одной — сразу ясно имя и причина (19.08: списком висело 12 минут без результата).
НЕ_ВСТАЛИ=""
while read -r ПАКЕТ; do
  case "$ПАКЕТ" in ''|\#*) continue;; esac
  printf '  %-26s' "$ПАКЕТ"
  if "$PY" -m pip install -q "$ПАКЕТ" 2>/tmp/aistudio-setup-err.log; then
    echo "ок"
  else
    echo "НЕ ВСТАЛ"
    sed -n '1,3p' /tmp/aistudio-setup-err.log | sed 's/^/      /'
    НЕ_ВСТАЛИ="$НЕ_ВСТАЛИ $ПАКЕТ"
  fi
done < requirements.txt

if [ -n "$НЕ_ВСТАЛИ" ]; then
  echo
  echo "ОШИБКА: не встали —$НЕ_ВСТАЛИ"
  echo "Комплект работает частично: структурные проверки идут, замеры нет."
  echo "Частая причина — старый python. Нужен 3.10 и новее; здесь $(python3 -V 2>&1)."
  exit 1
fi

echo
echo "готово. Проверка:  bash automation/setup.sh --проверка"
