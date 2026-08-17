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

SLOTS = [
    ('refs/look_v4/UP1_face.jpg', 'слот 1 — лицо'),
    ('refs/look_v4/UP2_packshot.jpg', 'слот 2 — пэкшот на белом'),
    ('refs/look_v4/UP3_button.jpg', 'слот 3 — фурнитура крупно'),
    ('refs/look_v4/UP4_edges.jpg', 'слот 4 — края низа и манжет'),
    ('refs/look_v4/UP_wall.jpg', 'слот 5 — локация'),
    ('refs/look_v4/UP_skirt.jpg', 'слот 6 — низ'),
    ('refs/look_v4/UP_shoes.jpg', 'слот 7 — обувь'),
    ('refs/look_v4/UP8_placket.jpg', 'слот 8 — застёжка целиком'),
    ('refs/look_v4/UP9_anchor.jpg', 'слот 9 — якорный кадр'),
]

DOCS_REMINDER = [
    'ЗАКОНЫ — что доказано, что опровергнуто',
    'Состояние проекта',
]

OPTIONAL = []

ROOTS = ['/home/claude/AI-STUDIO', '/home/claude/projects/brand/..', '/home/claude']


def find(rel):
    for r in ROOTS:
        p = os.path.join(r, rel)
        if os.path.exists(p):
            return p
    tail = rel.split('/')[-1]
    for base, _, files in os.walk('/home/claude/projects/brand'):
        if tail in files:
            return os.path.join(base, tail)
    for base, _, files in os.walk('/home/claude/work/skills'):
        if tail in files:
            return os.path.join(base, tail)
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    video = '--видео' in sys.argv
    interior = '--интерьер' in sys.argv
    packshot = '--пэкшот' in sys.argv
    cost = None
    if '--кредиты' in sys.argv:
        cost = sys.argv[sys.argv.index('--кредиты') + 1]
    if not args:
        print('нужен файл промпта')
        return 1
    prompt_path = args[0]
    text = open(prompt_path, encoding='utf-8').read()

    print('=' * 78)
    print('ПРЕДПОЛЁТНАЯ ПРОВЕРКА — без неё генерация запрещена')
    print('=' * 78)

    # 1. набор референсов
    print('\n1. Набор референсов — девять слотов:\n')
    missing = 0
    for rel, why in SLOTS:
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
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
