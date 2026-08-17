#!/usr/bin/env python3
"""Самопроверка комплекта. Один запуск вместо десяти ручных.

    python3 tools/selftest.py            быстрая, ~10 секунд
    python3 tools/selftest.py --полный   плюс калибровка метрики лица (качает модель ArcFace)

Зачем. 17.08.2026 первая же чистая сессия обнаружила, что `preflight.py` печатает
«ЗАПУСК ЗАПРЕЩЁН» на исправном промпте: он требовал семь документов, переехавших в Project
claude.ai. Дефект прожил в комплекте сутки, потому что проверять его было нечем — каждый запуск
делался руками и по памяти. Эта штука существует, чтобы такого не повторилось: одна команда,
один вердикт, ненулевой код возврата при любой поломке.

Запускать после каждого изменения комплекта и первым делом в новой сессии.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, 'tools')

SLOTS = [
    'refs/look_v4/UP1_face.jpg',
    'refs/look_v4/UP2_packshot.jpg',
    'refs/look_v4/UP3_button.jpg',
    'refs/look_v4/UP4_edges.jpg',
    'refs/look_v4/UP_wall.jpg',
    'refs/look_v4/UP_skirt.jpg',
    'refs/look_v4/UP_shoes.jpg',
    'refs/look_v4/UP8_placket.jpg',
    'refs/look_v4/UP9_anchor.jpg',
]

SCRIPTS = ['preflight.py', 'check_prompt.py', 'face_id.py', 'qc_frame.py',
           'scale_fig.py', 'trim_border.py', 'deliver.py', 'readiness.py']

fails = []


def check(name, ok, detail=''):
    print(f'  {"OK  " if ok else "СБОЙ"}  {name}' + (f' — {detail}' if detail else ''))
    if not ok:
        fails.append(name)


def main():
    full = '--полный' in sys.argv
    print('\nСАМОПРОВЕРКА КОМПЛЕКТА')
    print('=' * 70)

    print('\n1. Скрипты на месте и синтаксически целы')
    for s in SCRIPTS:
        p = os.path.join(TOOLS, s)
        if not os.path.exists(p):
            check(s, False, 'файла нет')
            continue
        r = subprocess.run([sys.executable, '-c', f'import ast;ast.parse(open({p!r}).read())'],
                           capture_output=True, text=True)
        check(s, r.returncode == 0, r.stderr.strip().splitlines()[-1] if r.returncode else '')

    print('\n2. Библиотеки')
    for mod in ('cv2', 'numpy', 'PIL', 'insightface', 'onnxruntime', 'rembg'):
        r = subprocess.run([sys.executable, '-c', f'import {mod}'], capture_output=True, text=True)
        check(mod, r.returncode == 0,
              'нет — pip install insightface onnxruntime rembg --break-system-packages'
              if r.returncode else '')

    print('\n3. Девять слотов набора')
    for rel in SLOTS:
        p = os.path.join(ROOT, rel)
        ok = os.path.exists(p) and os.path.getsize(p) > 1000
        check(rel.split('/')[-1], ok, 'нет или пустой' if not ok else '')

    print('\n4. Имена файлов не схлопываются по регистру (macOS)')
    seen, clash = {}, []
    for base, _, files in os.walk(ROOT):
        if '.git' in base:
            continue
        for f in files:
            key = os.path.join(base, f).lower()
            if key in seen:
                clash.append(f'{seen[key]} ↔ {os.path.join(base, f)}')
            seen[key] = os.path.join(base, f)
    check('коллизий регистра нет', not clash, '; '.join(clash))

    print('\n5. Промпты проходят предполётную проверку')
    pdir = os.path.join(ROOT, 'prompts')
    names = sorted(f for f in os.listdir(pdir) if f.endswith('.txt'))
    bad = []
    for f in names:
        r = subprocess.run([sys.executable, os.path.join(TOOLS, 'preflight.py'),
                            os.path.join(pdir, f), '--кредиты', '0'],
                           capture_output=True, text=True)
        if r.returncode != 0:
            bad.append(f)
    check(f'{len(names) - len(bad)} из {len(names)} зелёные', not bad, ', '.join(bad))

    print('\n6. Скрипты не ссылаются на удалённые документы')
    dead = []
    for s in SCRIPTS:
        # комментарии не считаются: в них эти пути упоминаются как история правки
        lines = [l for l in open(os.path.join(TOOLS, s), encoding='utf-8')
                 if not l.lstrip().startswith('#')]
        txt = ''.join(lines)
        for marker in ("'RULES ", "'METHOD §", '00_RULES/', '03_PROJECTS/', '04_poses/'):
            if marker in txt:
                dead.append(f'{s}: {marker.strip()}')
    check('мёртвых ссылок нет', not dead, '; '.join(dead))

    if full:
        print('\n7. Калибровка метрики лица на заведомо одинаковом случае')
        anchor = os.path.join(ROOT, 'refs', 'ЯКОРЬ_S03.jpg')
        if not os.path.exists(anchor):
            check('якорь на месте', False, 'refs/ЯКОРЬ_S03.jpg не найден')
        else:
            r = subprocess.run([sys.executable, os.path.join(TOOLS, 'face_id.py'),
                                '--эталон', anchor, anchor], capture_output=True, text=True)
            out = r.stdout
            ok = '1.00' in out or '0.99' in out
            check('якорь сам к себе ≈ 1.00', ok, out.strip().splitlines()[-1] if out else r.stderr[:120])
    else:
        print('\n7. Калибровка метрики лица — пропущена (запусти с --полный)')

    print('\n' + '=' * 70)
    if fails:
        print(f'УПАЛО: {len(fails)} — ' + ', '.join(fails))
        print('Комплект использовать нельзя, пока это не починено.')
        print('=' * 70 + '\n')
        return 1
    print('ПРОШЛО — комплект исправен')
    print('=' * 70 + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
