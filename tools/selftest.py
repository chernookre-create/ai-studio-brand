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

def load_slots():
    """Слоты текущей съёмки из refs/CURRENT.json — не зашиты в скрипт именами файлов."""
    import json
    path = os.path.join(ROOT, 'refs', 'CURRENT.json')
    if not os.path.exists(path):
        return None, 'refs/CURRENT.json не найден'
    try:
        d = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        return None, f'не читается: {e}'
    s = d.get('слоты') or {}
    if len(s) != 9:
        return None, f'слотов {len(s)}, должно быть 9'
    return [(k, v) for k, v in sorted(s.items())], d.get('серия', '')


SCRIPTS = ['preflight.py', 'check_prompt.py', 'face_id.py', 'qc_frame.py',
           'scale_fig.py', 'trim_border.py', 'deliver.py', 'readiness.py', 'registry.py', 'lineage.py']

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

    slots, series = load_slots()
    print(f'\n3. Девять слотов набора — серия «{series}»' if slots else '\n3. Девять слотов набора')
    if slots is None:
        check('refs/CURRENT.json', False, series)
    else:
        for role, rel in slots:
            p = os.path.join(ROOT, rel)
            ok = os.path.exists(p) and os.path.getsize(p) > 1000
            check(f'{role} → {rel}', ok, 'нет или пустой' if not ok else '')

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
    names = []
    for base, _, files in os.walk(pdir):
        # Судим только рабочие промпты — те, что отправим сегодня. Историю не судим:
        #   архив/    — тексты прежних серий этого изделия;
        #   материалы/ — разобранные прогоны, снятые до нынешних правил;
        #   эталоны/   — чужие промпты, от которых метод пошёл.
        # Реестр и эволюция их читают, предполётная проверка — нет.
        if any(os.sep + x in base + os.sep for x in ('архив', 'материалы', 'эталоны')):
            continue
        for f in sorted(files):
            if f.endswith('.txt'):
                names.append(os.path.relpath(os.path.join(base, f), pdir))
    names.sort()
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

    print('\n6б. Имена файлов конкретной съёмки не зашиты в скрипты')
    # маркеры берутся из самого CURRENT.json, а не пишутся литералами: иначе этот тест
    # пришлось бы править при каждой новой съёмке — то есть он был бы тем же дефектом.
    marks = set()
    for _, rel in (slots or []):
        parts = rel.split('/')
        marks.add(os.path.splitext(parts[-1])[0])
        if len(parts) > 2:
            marks.add(parts[1])
    hard = []
    for s in SCRIPTS + ['selftest.py']:
        lines = [l for l in open(os.path.join(TOOLS, s), encoding='utf-8')
                 if not l.lstrip().startswith('#')]
        txt = ''.join(lines)
        for m in sorted(marks):
            if m in txt:
                hard.append(f'{s}: {m}')
    check('набор описан данными, а не кодом', not hard, '; '.join(hard))

    if full:
        print('\n7. Калибровка метрики лица на заведомо одинаковом случае')
        anchor_rel = dict(slots).get('9_якорь') if slots else None
        anchor = os.path.join(ROOT, anchor_rel) if anchor_rel else ''
        if not anchor or not os.path.exists(anchor):
            check('якорь на месте', False, f'{anchor_rel or "слот 9"} не найден')
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
