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

    # Число файлов печатается, а не записывается в документы: документ с зашитым числом
    # устаревает при первом же удалении файла и начинает врать (Ф78).
    n = sum(len(fs) for base, _, fs in os.walk(ROOT) if '.git' not in base)
    print(f'\nФайлов в комплекте: {n}')

    print('\n1. Скрипты на месте и синтаксически целы')
    for s in SCRIPTS + ['selftest.py']:
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
            # Пустой якорь — это пилот серии: первый кадр серии сам станет якорем (Ф143).
            if not rel and 'якорь' in role:
                check(f'{role} → пилот серии, якоря ещё нет', True)
                continue
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

    print('\n6. Скрипты не ссылаются на несуществующие файлы')
    # Проверяем не по списку запрещённых слов, а по факту: каждый упомянутый в коде путь
    # к .md/.json должен где-то в комплекте существовать. Прежний список маркеров
    # ("'RULES ") требовал кавычку с пробелом и пропускал ссылку «как в RULES.md»
    # в комментарии, а маркер '00_readiness/' наоборот ругался на живой файл (Ф86).
    import re as _re
    # Прежняя версия считала ссылку живой, если файл с таким ИМЕНЕМ есть где угодно в
    # комплекте. Из-за этого проходила ссылка вида 00_RULES/старое/CURRENT.json — имя
    # существует, путь нет (Ф122). Теперь сверяется путь; имя допускается только тогда,
    # когда в ссылке пути нет вовсе (`РЕЕСТР.md`, `state.json`).
    known = set()
    for base, _, files in os.walk(ROOT):
        if '.git' in base:
            continue
        for f in files:
            known.add(f)
    dead = []
    # meta.json создаётся deliver.py в момент сдачи — это цель записи, а не ссылка.
    RUNTIME = {'meta.json'}
    for sc in SCRIPTS:
        txt = open(os.path.join(TOOLS, sc), encoding='utf-8').read()
        for m in _re.finditer(r'[A-Za-zА-Яа-я0-9_./-]+\.(?:md|json)(?![A-Za-z0-9])', txt):
            ref = m.group(0)
            # Путь, собранный из f-строки (`f'{out}/README.md'`), — это цель записи, а не
            # ссылка: проверять нечего, каталог создаётся в момент сдачи.
            if m.start() and txt[m.start() - 1] == '}':
                continue
            bare = '/' not in ref
            if (os.path.exists(os.path.join(ROOT, ref))
                    or (bare and ref in known)
                    or os.path.basename(ref) in RUNTIME):
                continue
            dead.append(f'{sc}: {ref}')
    check('мёртвых ссылок нет', not dead, '; '.join(sorted(set(dead))))

    print('\n6б. Имена файлов конкретной съёмки не зашиты в скрипты')
    # маркеры берутся из самого CURRENT.json, а не пишутся литералами: иначе этот тест
    # пришлось бы править при каждой новой съёмке — то есть он был бы тем же дефектом.
    marks = set()
    for _, rel in (slots or []):
        if not rel:          # пустой якорь пилота — маркера из него не бывает
            continue
        parts = rel.split('/')
        marks.add(os.path.splitext(parts[-1])[0])
        if len(parts) > 2:
            marks.add(parts[1])
    # Не только имена слотов: любое скалярное значение съёмки из CURRENT.json (эталон узора,
    # разрешение оригинала) не должно встречаться в коде литералом — иначе оно переедет в
    # следующую съёмку молча, как это было с «E05» в deliver.py (Ф125).
    try:
        import json as _j3
        _cur = _j3.load(open(os.path.join(ROOT, 'refs', 'CURRENT.json'), encoding='utf-8'))
        for k, v in _cur.items():
            if k != 'слоты' and isinstance(v, str) and len(v) >= 3 and '—' not in v:
                marks.add(v)
        marks.discard('')
    except Exception:
        pass
    hard = []
    for s in SCRIPTS + ['selftest.py']:
        lines = [l for l in open(os.path.join(TOOLS, s), encoding='utf-8')
                 if not l.lstrip().startswith('#')]
        txt = ''.join(lines)
        for m in sorted(marks):
            if m in txt:
                hard.append(f'{s}: {m}')
    check('набор описан данными, а не кодом', not hard, '; '.join(hard))

    print('\n6в. База промптов: нет побайтных дублей')
    import hashlib
    seen_hash, dupes = {}, []
    for base, _, files in os.walk(os.path.join(ROOT, 'prompts')):
        for f in sorted(files):
            if not f.endswith('.txt'):
                continue
            full_p = os.path.join(base, f)
            h = hashlib.md5(open(full_p, 'rb').read()).hexdigest()
            rel = os.path.relpath(full_p, ROOT)
            if h in seen_hash:
                dupes.append(f'{seen_hash[h]} ↔ {rel}')
            seen_hash[h] = rel
    check('дублей текста нет', not dupes, '; '.join(dupes))

    print('\n6г. ИСТОЧНИКИ.json ссылается на существующие файлы')
    src = os.path.join(ROOT, 'prompts', 'ИСТОЧНИКИ.json')
    if not os.path.exists(src):
        check('prompts/ИСТОЧНИКИ.json', False, 'файла нет')
    else:
        import json as _json
        recs = _json.load(open(src, encoding='utf-8'))
        broken = [r.get('№', '?') for r in recs
                  if not r.get('файл') or not os.path.exists(os.path.join(ROOT, r['файл']))]
        check(f'{len(recs) - len(broken)} из {len(recs)} записей с живым файлом',
              not broken, 'без файла: ' + ', '.join(broken) if broken else '')

    print('\n6д. Реестр: ни одна ссылка на промпт не двусмысленна')
    r = subprocess.run([sys.executable, os.path.join(TOOLS, 'registry.py'), '--проверка'],
                       capture_output=True, text=True)
    check('одинаковый код в двух сериях не связывается с чужим текстом', r.returncode == 0,
          r.stdout.strip().splitlines()[-1] if r.stdout else '')

    print('\n6е. Опросник готовности: состояние совпадает со списком пунктов')
    import re as _re2
    rd = open(os.path.join(TOOLS, 'readiness.py'), encoding='utf-8').read()
    # Один разряд не годится: в опроснике уже есть A10, а в «Позах» коды доходят до A12 (Ф123).
    ids = set(_re2.findall(r'\("([A-Z]\d{1,2})",', rd))
    st_p = os.path.join(ROOT, '00_readiness', 'state.json')
    if not os.path.exists(st_p):
        check('00_readiness/state.json', False, 'файла нет')
    else:
        import json as _j2
        st = _j2.load(open(st_p, encoding='utf-8'))
        got = set(st.get('готово', [])) | set(st.get('нет', []))
        extra, missing = sorted(got - ids), sorted(ids - got)
        det = (('лишние: ' + ', '.join(extra) + ' ') if extra else '') + \
              (('не заполнены: ' + ', '.join(missing)) if missing else '')
        check(f'{len(ids)} пунктов опросника, все отмечены', not extra and not missing, det)

        # Ключи самого файла — вторая половина проверки. Первая редакция сверяла только
        # списки пунктов, а посторонний ключ верхнего уровня не видела вовсе, хотя README
        # обещал именно проверку ключей. Ф104 закрывался как раз на «состояние содержит
        # ключи, которых в опроснике нет» — та половина оставалась открытой до Ф110.
        ALLOWED = {'проект', 'обновлено', 'правило', 'готово', 'нет'}
        stray = sorted(set(st) - ALLOWED)
        check('в state.json нет посторонних полей', not stray,
              ('лишние поля: ' + ', '.join(stray)) if stray else '')

        bad_type = [k for k in ('готово', 'нет') if not isinstance(st.get(k), list)]
        check('готово и нет — списки', not bad_type, ', '.join(bad_type))

        both = sorted(set(st.get('готово', [])) & set(st.get('нет', [])))
        check('пункт не стоит одновременно в готово и в нет', not both, ', '.join(both))

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
