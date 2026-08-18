#!/usr/bin/env python3
"""Предполётная проверка. Печатает отчёт, который обязан появиться в чате ПЕРЕД каждой генерацией.

Смысл: сделать применение знаний видимым. Пока отчёт не напечатан и не зелёный — генерация
запрещена. Если в моём сообщении нет этого блока, значит я нарушил протокол, и это видно вам
без всякого доверия к моим словам.

    python3 tools/preflight.py <файл_промпта> [--видео] [--кредиты 3]

Код возврата 1 — генерация запрещена.
"""
import hashlib
import os
import subprocess
import sys
import time

# Что должно быть на диске перед запуском.
#
# Правка 17.08.2026. Прежний список требовал семь документов по путям 00_RULES/, 04_poses/,
# 00_readiness/ — они переехали в Project claude.ai и на диск больше не кладутся намеренно:
# два источника правил разъезжаются. Пока список оставался прежним, preflight печатал
# «ЗАПУСК ЗАПРЕЩЁН» на каждом кадре при полностью исправном промпте, то есть красная проверка
# врала. Проверка, которая срабатывает всегда, не проверяет ничего — её перестают читать.
#
# Теперь блокирует только то, что физически нужно кадру и лежит рядом: девять слотов набора.
# Документы проекта проверить с диска нельзя, поэтому про них печатается напоминание, а
# ответственность за «прочитано глазами» остаётся на операторе — как и было в инструкциях.

def load_slots():
    """Девять слотов текущей съёмки из refs/CURRENT.json.

    Правка 17.08.2026 вечером. До неё список слотов был зашит в скрипт именами файлов ореховой
    комнаты. Это неверно по существу: ореховая стена — значение слота 5 на сегодня, а не свойство
    метода. Со следующей съёмкой в другом месте проверка требовала бы файл прошлой локации.
    Теперь набор описан данными: новая съёмка — правка одного JSON, скрипты не трогаются.
    """
    import json
    path = os.path.join(ROOT, 'refs', 'CURRENT.json')
    if not os.path.exists(path):
        return None, 'refs/CURRENT.json не найден — набор текущей съёмки не описан'
    try:
        d = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        return None, f'refs/CURRENT.json не читается: {e}'
    slots = d.get('слоты') or {}
    if len(slots) != 9:
        return None, f'в refs/CURRENT.json описано слотов: {len(slots)}, должно быть 9'
    # Пустое значение допускается только у якоря и означает пилот серии: якоря ещё нет,
    # он появится из этого самого кадра. Правило заказчика от 18.08 — «первый кадр серии
    # становится якорем», и до него набор состоит из восьми картинок (Ф143).
    return ([(v, k.split('_', 1)[1] if '_' in k else k) for k, v in sorted(slots.items())],
            d.get('серия', ''))


DOCS_REMINDER = [
    'ЗАКОНЫ — что доказано, что опровергнуто',
    'Состояние проекта',
]

OPTIONAL = []

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ищем только внутри комплекта. Прежние запасные корни были абсолютными путями вида
# /home/claude/... — в сессии с другим домашним каталогом весь резервный поиск был мёртв
# и молча возвращал None, а документ уже объявлял такие пути несуществующими (Ф106, Ф128).
def find(rel):
    p = os.path.join(ROOT, rel)
    if os.path.exists(p):
        return p
    tail = rel.split('/')[-1]
    for base, _, files in os.walk(ROOT):
        if '.git' in base:
            continue
        if tail in files:
            return os.path.join(base, tail)
    return None



def detect_mode(text):
    """Определить тип кадра по самому тексту промпта.

    Ф62, 17.08.2026: проверка без флага измеряет не тот кадр — интерьерный промпт получал девять
    нарушений про лицо, позу и пуговицы, которых в кадре нет вовсе. Полагаться на память человека
    в этом месте нельзя: забытый флаг выглядит как настоящий брак и стоит захода. Тип определяется
    из текста, флаг остаётся как ручное переопределение.
    """
    low = text.lower()
    if 'this is an empty room' in low or 'no shadow of a person' in low:
        return 'интерьер'
    if 'studio product photograph' in low or 'seamless white background' in low:
        return 'пэкшот'
    if 'start frame' in low or 'end frame' in low or 'motion preset' in low:
        return 'видео'
    return 'фото'


def _журнал(файл, разрешено, нарушений):
    """Записать решение предполётной проверки. Это Validation в терминах наблюдаемости:
    единственное место, где комплект говорит «запускать можно» или «нельзя»."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from obs import операция
    except Exception:                                            # noqa: BLE001
        return
    try:
        with операция('preflight', код=os.path.basename(файл), ключ='предполётная проверка') as оп:
            оп.этап('Validation')
            if разрешено:
                оп.проверил('предполётная проверка', 'РАЗРЕШЕНО', 'ноль нарушений', True)
                оп.готово('разрешено')
            else:
                оп.сбой('E_PREFLIGHT', f'нарушений: {нарушений}')
                оп.готово('запрещено')
    except Exception:                                            # noqa: BLE001
        pass


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    video = '--видео' in sys.argv
    interior = '--интерьер' in sys.argv
    packshot = '--пэкшот' in sys.argv
    cost = None
    if '--кредиты' in sys.argv:
        cost = sys.argv[sys.argv.index('--кредиты') + 1]
    if not args:
        print()
        print('preflight.py — предполётная проверка. Нужен файл промпта.')
        print()
        print('  python3 tools/preflight.py prompts/base_v4.txt --кредиты 0')
        print()
        print('Тип кадра определяется по тексту сам; флаг нужен только чтобы переопределить:')
        print('  --интерьер   кадр без человека')
        print('  --пэкшот     предметка на белом')
        print('  --видео      видео-промпт')
        print()
        print('Проверить весь комплект разом:  python3 tools/selftest.py')
        print()
        return 1
    prompt_path = args[0]
    text = open(prompt_path, encoding='utf-8').read()

    # тип кадра: флаг человека сильнее, но при его отсутствии определяем сами
    auto = detect_mode(text)
    if not (video or interior or packshot):
        video = auto == 'видео'
        interior = auto == 'интерьер'
        packshot = auto == 'пэкшот'
        auto_note = f'определён по тексту: {auto}'
    else:
        given = 'видео' if video else 'интерьер' if interior else 'пэкшот'
        auto_note = f'задан флагом: {given}'
        if given != auto:
            auto_note += f' (по тексту похоже на «{auto}» — проверь, тот ли файл)'

    print('=' * 78)
    print('ПРЕДПОЛЁТНАЯ ПРОВЕРКА — без неё генерация запрещена')
    print(f'{prompt_path} · тип кадра {auto_note}')
    print('=' * 78)

    # 1. набор референсов
    slots, series = load_slots()
    if slots is None:
        print(f'\n1. Набор референсов: {series}')
        print('\n' + '=' * 78)
        print('ЗАПУСК ЗАПРЕЩЁН — набор не описан')
        print('=' * 78 + '\n')
        return 1
    пилот = any((not rel) and 'якорь' in why for rel, why in slots)
    заголовок = ('восемь слотов, пилот серии — якоря ещё нет' if пилот
                 else 'девять слотов')
    print(f'\n1. Набор референсов — {заголовок}, серия «{series}»:\n')
    missing = 0
    for rel, why in slots:
        if not rel and 'якорь' in why:
            print(f'  ПИЛОТ  9 якорь — пуст. Этот кадр и станет якорем серии после приёмки.')
            continue
        p = find(rel)
        if not p:
            print(f'   ОТСУТСТВУЕТ  {rel} — {why}')
            missing += 1
            continue
        st = os.stat(p)
        h = hashlib.sha1(open(p, 'rb').read()).hexdigest()[:8]
        d = time.strftime('%d.%m %H:%M', time.localtime(st.st_mtime))
        print(f'   [{h}] {d}  {rel}')
        print(f'              {why}')

    print('\n   Документы проекта живут в Project claude.ai и с диска не проверяются.')
    print('   Перед запуском они должны быть прочитаны глазами:')
    for name in DOCS_REMINDER:
        print(f'      — «{name}»')
    print('   Отдельно: слоты сверяются в браузере поимённо — после переподключения')
    print('   тумблер Unlimited выключается, а часть слотов пустеет.')

    # 2. проверка промпта
    print('\n2. Проверка промпта по правилам:')
    tools = os.path.dirname(os.path.abspath(__file__))
    cmd = [sys.executable, os.path.join(tools, 'check_prompt.py'), prompt_path]
    if video:
        cmd.append('--видео')
    if interior:
        cmd.append('--интерьер')
    if packshot:
        cmd.append('--пэкшот')
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout.rstrip())

    # 3. готовность
    print('\n3. Готовность проекта:')
    r2 = subprocess.run([sys.executable, os.path.join(tools, 'readiness.py')],
                        capture_output=True, text=True, cwd=os.path.dirname(tools))
    print('\n'.join(r2.stdout.strip().splitlines()[:6]))

    # 4. смета
    print(f'\n4. Стоимость запуска: {cost or "НЕ УКАЗАНА"} кредитов')

    ok = (r.returncode == 0) and missing == 0 and cost is not None
    print('\n' + '=' * 78)
    print('РАЗРЕШЕНО ЗАПУСКАТЬ' if ok else 'ЗАПУСК ЗАПРЕЩЁН — см. нарушения выше')
    print('=' * 78 + '\n')
    _журнал(args[0] if args else '—', ok, 0 if ok else (r.returncode or 1))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
