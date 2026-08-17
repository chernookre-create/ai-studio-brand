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

# Источники делятся на два вида. Проверка 13.08.2026 в новой сессии показала, что прежний
# список был жёстче, чем реальность: он требовал на диске всю базу знаний, включая конспект курса
# на 300 КБ, которого в проекте нет вовсе. Из-за этого preflight не мог позеленеть НИКОГДА,
# то есть протокол запуска физически не выполнялся. Разделено на обязательные и справочные.

# без этих файлов промпт собрать нельзя — их отсутствие блокирует запуск
SOURCES = [
    ('00_RULES/RULES.md', 'конституция: инварианты и запреты'),
    ('03_PROJECTS/brand/02_prompts/METHOD_REFERENCE_PROMPT.md', 'разбор рабочего примера заказчика'),
    ('03_PROJECTS/brand/02_prompts/TEMPLATE_PHOTO.md', 'шаблон фото-промпта'),
    ('03_PROJECTS/brand/02_prompts/TEMPLATE_VIDEO.md', 'шаблон видео-промпта'),
    ('03_PROJECTS/brand/04_poses/POSES.md', 'библиотека поз и границы редактора'),
    ('03_PROJECTS/brand/00_readiness/READINESS.md', 'готовность и класс кадра'),
    ('03_PROJECTS/brand/00_readiness/state.json', 'состояние опросников для счёта готовности'),
]

# полезны, но их отсутствие не блокирует: это фон, а не рабочий источник промпта
OPTIONAL = [
    ('02_KNOWLEDGE/METHOD.md', 'конспект курса целиком'),
    ('02_KNOWLEDGE/VIDEO_REVISION.md', 'ревизия видео-каталога со ссылками'),
]
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

    # 1. источники знаний
    print('\n1. Источники знаний, по которым собран промпт:\n')
    missing = 0
    for rel, why in SOURCES:
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

    for rel, why in OPTIONAL:
        p = find(rel)
        if not p:
            print(f'   нет на диске (не блокирует)  {rel} — {why}')
            continue
        h = hashlib.sha1(open(p, 'rb').read()).hexdigest()[:8]
        d = time.strftime('%d.%m %H:%M', time.localtime(os.stat(p).st_mtime))
        print(f'   [{h}] {d}  {rel}')

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
