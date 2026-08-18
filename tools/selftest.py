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

# Читатель набора один на весь комплект — тот же, которым пользуется предполётная проверка.
# Своя копия здесь жила до 18.08: две функции решали, какой набор считать исправным, и
# каждую правку (пилот на восьми слотах) приходилось делать дважды (Ф155).
sys.path.insert(0, TOOLS)
from preflight import load_slots as _load_slots     # noqa: E402


def слоты_набора():
    """Слоты в виде (роль, путь) — preflight отдаёт (путь, роль). Имя своё: `load_slots`
    определён ровно в одном месте комплекта, проверка 6з за этим следит."""
    пары, серия = _load_slots()
    if пары is None:
        return None, серия
    return [(роль, путь) for путь, роль in пары], серия


SCRIPTS = ['preflight.py', 'check_prompt.py', 'face_id.py', 'qc_frame.py',
           'scale_fig.py', 'trim_border.py', 'deliver.py', 'readiness.py', 'registry.py',
           'lineage.py', 'rules_selftest.py', 'sharpness.py',
           'obs.py', 'obs_cli.py', 'obs_test.py', 'circles.py']

def без_текста(код):
    """Убрать комментарии и строки документации: пример вызова в docstring
    (`face_id.py --эталон ref.jpg кадр1.png`) — это не ссылка на файл, а образец
    команды. Первая редакция расширенной проверки поймала семь таких и была неправа."""
    import io, tokenize as _tk
    куски, prev = [], None
    try:
        for t in _tk.generate_tokens(io.StringIO(код).readline):
            if t.type == _tk.COMMENT:
                continue
            if t.type == _tk.STRING and (prev is None or prev in (_tk.INDENT, _tk.NEWLINE, _tk.NL)):
                continue          # docstring на своей строке
            куски.append(t.string)
            if t.type not in (_tk.NL, _tk.NEWLINE, _tk.INDENT, _tk.DEDENT):
                prev = t.type
            else:
                prev = t.type
    except Exception:
        return код
    return '\n'.join(куски)


fails = []


_напечатанные = []


def пункт(заголовок):
    """Напечатать заголовок пункта и запомнить его номер: по этому списку сверяется,
    что находка не «закрыта» ссылкой на пункт, которого в отчёте нет."""
    print('\n' + заголовок)
    m = __import__('re').match(r'^(\d+[а-яё]?)\.', заголовок)
    if m:
        _напечатанные.append(m.group(1))


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
    # __pycache__ считать нельзя: он появляется от самого запуска, и число файлов
    # прыгает 167 → 169 между двумя одинаковыми прогонами в свежем клоне (Ф146).
    ПРОПУСК = ('.git', '__pycache__', '.pytest_cache')
    n = sum(len(fs) for base, _, fs in os.walk(ROOT)
            if not any(f'{os.sep}{d}' in base or base.endswith(d) for d in ПРОПУСК))
    print(f'\nФайлов в комплекте: {n}')

    пункт('1. Скрипты на месте и синтаксически целы')
    for s in SCRIPTS + ['selftest.py']:
        p = os.path.join(TOOLS, s)
        if not os.path.exists(p):
            check(s, False, 'файла нет')
            continue
        r = subprocess.run([sys.executable, '-c', f'import ast;ast.parse(open({p!r}).read())'],
                           capture_output=True, text=True)
        check(s, r.returncode == 0, r.stderr.strip().splitlines()[-1] if r.returncode else '')

    пункт('2. Библиотеки — не импортом, а вызовом')
    # Импорт ничего не доказывает. 18.08 чистая сессия поставила `rembg` со сменившимся
    # дефолтом модели (`bria-rmbg-2.0`, 1.02 ГБ), вызов получал SIGKILL — то есть `scale_fig`
    # и `sharpness` не работали вовсе, а этот пункт был зелёный: `import rembg` проходит за
    # долю секунды (Ф159). Закон F5 в чистом виде: проверка искала слово, а не факт.
    # SIGKILL нельзя поймать try/except, поэтому каждая проба идёт в дочернем процессе.
    ПРОБЫ = [
        ('cv2', "import cv2, numpy as np; "
                "assert cv2.Laplacian(np.zeros((8, 8), np.uint8), cv2.CV_64F).shape == (8, 8)"),
        ('numpy', "import numpy as np; assert float(np.zeros(4).var()) == 0.0"),
        ('PIL', "from PIL import Image; Image.new('RGB', (8, 8)).tobytes()"),
        ('onnxruntime', "import onnxruntime; assert onnxruntime.get_available_providers()"),
        ('insightface', "from insightface.app import FaceAnalysis"),
        ('rembg · вырезание фигуры моделью u2net',
         "import io, sys, os; sys.path.insert(0, os.path.join(%r, 'tools')); "
         "from PIL import Image; from rembg import remove; "
         "from scale_fig import сессия_вырезания; "
         "b = io.BytesIO(); Image.new('RGB', (64, 64), (200, 120, 60)).save(b, 'PNG'); "
         "out = remove(b.getvalue(), session=сессия_вырезания()); "
         "assert Image.open(io.BytesIO(out)).mode == 'RGBA'" % ROOT),
    ]
    for имя, код in ПРОБЫ:
        r = subprocess.run([sys.executable, '-c', код], capture_output=True, text=True, timeout=900)
        деталь = ''
        if r.returncode != 0:
            хвост = (r.stderr.strip().splitlines() or [''])[-1]
            if r.returncode < 0 or r.returncode == 137:
                хвост = (f'процесс убит сигналом (код {r.returncode}) — чаще всего это нехватка '
                         'памяти; try/except такое не ловит, поэтому проба и идёт отдельным процессом')
            деталь = хвост or 'нет — pip install insightface onnxruntime rembg --break-system-packages'
        check(имя, r.returncode == 0, деталь)

    slots, series = слоты_набора()
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

    пункт('4. Имена файлов не схлопываются по регистру (macOS)')
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

    пункт('5. Промпты проходят предполётную проверку')
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

    пункт('5б. Каждое правило check_prompt умеет покраснеть')
    # Счёт 18.08: из 53 правил четырёх классов 35 не сработали ни разу за всю историю.
    # Правило, которое ни разу не падало, неотличимо от правила, которое упасть не может —
    # два таких уже нашлись (Ф119, Ф120), и этот прогон нашёл ещё четыре (Ф149, Ф150).
    r = subprocess.run([sys.executable, os.path.join(TOOLS, 'rules_selftest.py')],
                       capture_output=True, text=True)
    строки = [l for l in r.stdout.strip().splitlines() if l.strip()]
    check(строки[0] if строки else 'rules_selftest.py', r.returncode == 0,
          '; '.join(l.strip() for l in строки if 'СБОЙ' in l)[:300])

    пункт('6. Скрипты не ссылаются на несуществующие файлы')
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
    # obs_test.py выдумывает пути нарочно — это его работа: он проверяет счётчики записей
    # на выдуманных именах, ничего не записывая. Судить его этим пунктом бессмысленно.
    for sc in [x for x in SCRIPTS if x != 'obs_test.py']:
        txt = без_текста(open(os.path.join(TOOLS, sc), encoding='utf-8').read())
        # Картинки тоже: ссылка на несуществующий .jpg ломает счёт ровно так же, как
        # ссылка на несуществующий .json, а проверка её не видела (Ф147).
        for m in _re.finditer(
                r'[A-Za-zА-Яа-я0-9_./-]+\.(?:md|json|jpg|jpeg|png|webp)(?![A-Za-z0-9])', txt):
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

    пункт('6б. Имена файлов конкретной съёмки не зашиты в скрипты')
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
        # Комментарии и docstring вырезаются тем же токенизатором, что в пункте 6: имя съёмки
        # в объяснении «почему так сделано» — это документация, а не зашитое в код имя. Первая
        # редакция резала только строки с `#` и ругалась на разбор в docstring (Ф164).
        txt = без_текста(open(os.path.join(TOOLS, s), encoding='utf-8').read())
        for m in sorted(marks):
            if m in txt:
                hard.append(f'{s}: {m}')
    check('набор описан данными, а не кодом', not hard, '; '.join(hard))

    пункт('6в. Комплект: нет побайтных дублей (тексты и картинки)')
    # Первая редакция смотрела только prompts/*.txt, а дубли картинок в refs/ — 24 файла
    # без единой ссылки и пара MIRA_* — так и лежали. Дубль картинки дороже дубля текста:
    # он занимает слот в наборе и уводит модель (Ф148).
    import hashlib
    seen_hash, dupes = {}, []
    ДУБЛИ_ГДЕ = [os.path.join(ROOT, 'prompts'), os.path.join(ROOT, 'refs')]
    for корень in ДУБЛИ_ГДЕ:
      for base, _, files in os.walk(корень):
        if '__pycache__' in base or '_снято_с_учёта' in base:
            continue
        for f in sorted(files):
            if not f.lower().endswith(('.txt', '.jpg', '.jpeg', '.png', '.webp')):
                continue
            full_p = os.path.join(base, f)
            h = hashlib.md5(open(full_p, 'rb').read()).hexdigest()
            rel = os.path.relpath(full_p, ROOT)
            if h in seen_hash:
                dupes.append(f'{seen_hash[h]} ↔ {rel}')
            seen_hash[h] = rel
    check('дублей текста нет', not dupes, '; '.join(dupes))

    пункт('6г. ИСТОЧНИКИ.json ссылается на существующие файлы')
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

    пункт('6д. Реестр: ни одна ссылка на промпт не двусмысленна')
    r = subprocess.run([sys.executable, os.path.join(TOOLS, 'registry.py'), '--проверка'],
                       capture_output=True, text=True)
    check('одинаковый код в двух сериях не связывается с чужим текстом', r.returncode == 0,
          r.stdout.strip().splitlines()[-1] if r.stdout else '')

    пункт('6е. Опросник готовности: состояние совпадает со списком пунктов')
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

    пункт('6ж. Поля «лицо» и «узор» в results/*.json: либо число, либо причина из словаря')
    # За сутки одно поле обзавелось семью написаниями одного и того же: «—», «не мерено»,
    # «не мерено, лица нет», «нет в кадре», «со спины», «профиль». Свободный текст в поле,
    # по которому потом считают, — это метрика, которой нет (F7). Словарь закрыт, восьмого
    # написания не будет: проверка падает на любом значении вне списка.
    import glob as _g, json as _j3, re as _re3
    # Два поля, по которым в проекте считают, и два закрытых словаря к ним. Свободный текст
    # в таком поле — это метрика, которой нет (F7): у «лица» набралось семь написаний одного
    # и того же (Ф147), у «узора» — четырнадцать, включая «+13% на грани» и «база» (Ф154).
    СЛОВАРИ = {
        'лицо': ({'не мерено', 'со спины', 'профиль', 'лица нет в кадре'},
                 _re3.compile(r'^\d\.\d{3}$')),
        # Знак обязателен: отклонение без знака не читается ни как рост, ни как падение.
        # Исключение одно — ровный ноль.
        'узор': ({'не мерено', 'эталон серии', 'на глаз, числа нет', 'не применим'},
                 _re3.compile(r'^(0%|[+-]\d{1,3}%)$')),
    }
    res = sorted(_g.glob(os.path.join(ROOT, 'results', '*.json')))
    if not res:
        check('results/*.json', False, 'файлов нет')
    else:
        плохие, всего = [], 0
        for f in res:
            try:
                d = _j3.load(open(f, encoding='utf-8'))
            except Exception as e:
                плохие.append(f'{os.path.basename(f)}: не читается ({e})')
                continue
            for k, it in d.items():
                if not isinstance(it, dict):
                    continue
                for поле, (ПРИЧИНЫ, ЧИСЛО) in СЛОВАРИ.items():
                    if поле not in it:
                        continue
                    всего += 1
                    v = it[поле]
                    # Тип тоже часть словаря: число float молча пройдёт по виду, но 0.6
                    # сериализуется как «0.6», а 0.60 — как «0.6», и три знака теряются.
                    if not isinstance(v, str) or (not ЧИСЛО.match(v) and v not in ПРИЧИНЫ):
                        плохие.append(f'{os.path.basename(f)}:{k}.{поле} = {v!r}')
        check(f'{всего - len(плохие)} из {всего} записей по словарю', not плохие,
              '; '.join(плохие[:6]) + (' …' if len(плохие) > 6 else ''))

    пункт('6з. Одна идея — одна реализация: общие имена не определены дважды')
    # 18.08: `scene_tail` был написан дважды — в check_prompt (по нему судит правило P1) и в
    # registry (по нему пишется колонка реестра). На двух текстах из 77 они отвечали разное,
    # то есть про главный закон проекта в комплекте было два ответа (Ф153). Рядом нашлись
    # ещё два таких: `load_slots` (правку про пилот пришлось делать дважды) и `TOL = 0.12`.
    import ast as _ast
    ОБЩИЕ = ['scene_tail', 'scene_tails', 'load_slots', 'dot_pitch', 'to_work',
             'BLOCKS', 'TOL', 'ЛОМКОЕ', 'ОГРАНИЧЕНИЕ', 'ПОСТОБРАБОТКА', 'ПРИЧЁСКА']
    где = {}
    for sc in SCRIPTS + ['selftest.py']:
        try:
            tree = _ast.parse(open(os.path.join(TOOLS, sc), encoding='utf-8').read())
        except SyntaxError:
            continue
        for node in tree.body:                       # только верхний уровень модуля
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                где.setdefault(node.name, []).append(sc)
            elif isinstance(node, _ast.Assign):
                for t in node.targets:
                    if isinstance(t, _ast.Name):
                        где.setdefault(t.id, []).append(sc)
    двойные = [f'{имя}: ' + ', '.join(где[имя]) for имя in ОБЩИЕ if len(где.get(имя, [])) > 1]
    check(f'{len(ОБЩИЕ)} общих имён, у каждого один хозяин', not двойные, '; '.join(двойные))

    пункт('6и. Каждая картинка refs/ названа: либо слот, либо строка инвентаря')
    # 21 картинка из 32 не была упомянута нигде: ни в слотах, ни в скриптах, ни в документах.
    # Через сутки такой файл неотличим от рабочего — а одна из них (UP_INT03) показывает ровно
    # тот дефект локации, который мы лечим текстом, и попади она в слот 5, приехала бы в кадр
    # вместе с ним (Ф157).
    инв = os.path.join(ROOT, 'refs', 'ЧТО_ЗДЕСЬ.md')
    if not os.path.exists(инв):
        check('refs/ЧТО_ЗДЕСЬ.md', False, 'инвентаря нет')
    else:
        текст_инв = open(инв, encoding='utf-8').read()
        в_слотах = {os.path.basename(rel) for _, rel in (slots or []) if rel}
        безымянные, всего_кар = [], 0
        for base, _, files in os.walk(os.path.join(ROOT, 'refs')):
            if '_снято_с_учёта' in base:
                continue
            for f in sorted(files):
                if not f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    continue
                всего_кар += 1
                if f in в_слотах or f in текст_инв:
                    continue
                безымянные.append(os.path.relpath(os.path.join(base, f), ROOT))
        check(f'{всего_кар - len(безымянные)} из {всего_кар} картинок названы',
              not безымянные, ', '.join(безымянные[:5]) + (' …' if len(безымянные) > 5 else ''))

    пункт('6к. Паспорта изделий не описывают предмет, которого в наборе нет')
    # Правило check_prompt A1 сторожит промпты — но закон A1 отсылает сверять текст с
    # ПАСПОРТОМ, а паспорт лука трое суток описывал бордовые лоферы, которых в слоте 7 нет.
    # Механизм «не_путать» не покрывал единственный файл, к которому закон и отсылает (Ф161).
    # Раздел «Снято с учёта» — законное место для прежнего предмета, он пропускается.
    import json as _j4, re as _re4
    _cur_p = os.path.join(ROOT, 'refs', 'CURRENT.json')
    _карта = {}
    try:
        _карта = _j4.load(open(_cur_p, encoding='utf-8')).get('не_путать') or {}
    except Exception:                                             # noqa: BLE001
        pass
    паспорта = []
    for base, _, files in os.walk(os.path.join(ROOT, 'refs', 'approved')):
        паспорта += [os.path.join(base, f) for f in sorted(files) if f.endswith('.md')]
    грязные = []
    for пп in паспорта:
        текст = open(пп, encoding='utf-8').read()
        живое = текст.split('## Снято с учёта')[0]
        for слот, слова in _карта.items():
            for w in слова:
                for м in _re4.finditer(r'\b' + _re4.escape(w) + r'\b', живое, _re4.I):
                    # Отрицание — законное употребление: строка «не гладкий купол и не широкое
                    # кольцо» в паспорте кардигана помогает человеку сверять глазами и ничего
                    # не описывает. Проверка на этом падать не должна, а на утверждении должна.
                    # Между отрицанием и словом по-английски почти всегда стоит артикль:
                    # «not **a** smooth polished dome», «never **a** broad ring». Первая
                    # редакция требовала только пробелы и тире — то есть умела отличать
                    # отрицание по-русски, а промпты у нас английские (Ф166).
                    перед = живое[max(0, м.start() - 28):м.start()].lower()
                    if _re4.search(r'\b(не|ни|нет|вместо|no|not|never|rather than|instead of)\b'
                                   r'(\s+(a|an|the|any|its|his|her|their))?[\s,;:–—-]*$', перед):
                        continue
                    грязные.append(f'{os.path.relpath(пп, ROOT)}: «{w}» (слот {слот})')
    check(f'{len(паспорта)} паспортов, ни одного слова снятого предмета',
          not грязные and bool(паспорта),
          '; '.join(грязные) if грязные else ('паспортов нет' if not паспорта else ''))

    пункт('6л. Обязательные куски текста стоят во ВСЕХ рабочих промптах изделия')
    # Правка рельефа пуговицы (Ф144) дошла до четырёх баз из шести: E02–E05 её получили,
    # S04 и S05 нет, а журнал записал «применили к шести». Четвёртый повтор класса «правка,
    # применённая не везде, — это не правка» (Ф162). Список кусков — в CURRENT.json, потому
    # что он про сегодняшнее изделие, а не про метод.
    _треб = {}
    _папка = ''
    try:
        _c = _j4.load(open(_cur_p, encoding='utf-8'))
        _треб = _c.get('обязательно_в_промптах') or {}
        _папка = _c.get('папка_промптов') or ''
    except Exception:                                             # noqa: BLE001
        pass
    if not _треб or not _папка:
        check('обязательно_в_промптах в refs/CURRENT.json', False,
              'поля нет — проверять нечего, а значит правку снова можно недоделать')
    else:
        рабочие = []
        корень = os.path.join(ROOT, _папка)
        for base, _, files in os.walk(корень):
            if any(os.sep + x in base + os.sep for x in ('архив', 'материалы', 'эталоны')):
                continue
            рабочие += [os.path.join(base, f) for f in sorted(files) if f.endswith('.txt')]
        пробелы = []
        for пр in рабочие:
            т = open(пр, encoding='utf-8').read()
            for имя, кусок in _треб.items():
                if кусок.lower() not in т.lower():
                    пробелы.append(f'{os.path.basename(пр)}: нет «{имя}»')
        check(f'{len(рабочие)} промптов изделия, {len(_треб)} обязательных кусков',
              not пробелы and bool(рабочие), '; '.join(пробелы[:6]))

    пункт('6м. В README нет чисел, которые умеет посчитать скрипт')
    # Закон F6: у каждого числа один источник. 18.08 README в одной строке говорил
    # «тринадцать скриптов», в другой «одиннадцать», а на диске было тринадцать — две строки
    # одного файла спорили друг с другом (Ф163). Проверяем ровно те величины, которые печатают
    # скрипты: число скриптов, число правил, число файлов, число текстов.
    # Ловим число рядом со СЧЁТНЫМ существительным, и только тем, которое печатает скрипт:
    # скрипты, правила, тексты, файлы комплекта. «Девять слотов» — это не счёт, а свойство
    # метода, набор девятислотный по определению; ругаться на него значило бы сделать
    # проверку широкой ровно настолько, насколько прежняя была узкой (Ф167).
    ЧИСЛА_СЛОВАМИ = ('один', 'одна', 'одно', 'два', 'две', 'три', 'четыре', 'пять', 'шесть',
                     'семь', 'восемь', 'девять', 'десять', 'одиннадцать', 'двенадцать',
                     'тринадцать', 'четырнадцать', 'пятнадцать', 'шестнадцать', 'семнадцать',
                     'восемнадцать', 'девятнадцать', 'двадцать', 'тридцать', 'сорок',
                     'пятьдесят', 'сто')
    СЧЁТНЫЕ = r'(?:скрипт\w*|правил\w*|текст\w*|файл\w*\s+в\s+комплекте)'
    ЧИСЛО_РЯДОМ = (r'\b(?:' + '|'.join(ЧИСЛА_СЛОВАМИ) + r'|\d{1,4})\s+'
                   + СЧЁТНЫЕ)
    rd_p = os.path.join(ROOT, 'README.md')
    найдено = []
    if os.path.exists(rd_p):
        for i, стр in enumerate(open(rd_p, encoding='utf-8'), 1):
            for м in _re4.finditer(ЧИСЛО_РЯДОМ, стр.lower()):
                найдено.append(f'README.md:{i} — «{м.group(0)[:34]}»')
    check('число, которое печатает скрипт, в прозе README не повторяется',
          not найдено, '; '.join(найдено[:6]))

    пункт('6н. Ни одна находка не закрыта ссылкой на пункт, которого нет')
    # Ф115 в машинном виде: «закрыто» пишется только о том, что можно проверить самому.
    # Реестр находок хранит, каким пунктом удержана каждая; здесь сверяется, что пункт
    # реально печатается в этом самом отчёте. Ссылка на несуществующий пункт — это
    # «закрыто» без основания, и человек его глазами не поймает: пунктов девятнадцать.
    рп = os.path.join(ROOT, '00_obs', 'находки.json')
    if not os.path.exists(рп):
        check('00_obs/находки.json', True, 'реестра нет — учёт находок не ведётся')
    else:
        import json as _j5
        try:
            _нах = _j5.load(open(рп, encoding='utf-8')).get('находки') or {}
        except Exception as e:                                    # noqa: BLE001
            _нах = {}
            check('00_obs/находки.json', False, f'не читается: {e}')
        # Живые пункты — те, что напечатаны выше в этом же прогоне, плюс сам этот пункт.
        живые = set(_напечатанные) | {'6н'}
        ложные = [f'{n}→{f["проверка"]}' for n, f in sorted(_нах.items())
                  if f.get('проверка') and f['проверка'] not in живые]
        check(f'{len(_нах)} находок в реестре, ссылок на несуществующие пункты нет',
              not ложные, '; '.join(ложные[:8]))

    if full:
        пункт('7. Калибровка метрики лица на заведомо одинаковом случае')
        # Роль, а не ключ JSON: ключ `9_якорь` живёт только внутри CURRENT.json, наружу
        # оба читателя отдают роль без цифры.
        anchor_rel = dict(slots).get('якорь') if slots else None
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
        пункт('7. Калибровка метрики лица — пропущена (запусти с --полный)')

    пункт('8. Наблюдаемость: тесты журнала, вырезания секретов и детектора цикла')
    r = subprocess.run([sys.executable, os.path.join(TOOLS, 'obs_test.py')],
                       capture_output=True, text=True, timeout=1800)
    строки = [l.strip() for l in (r.stdout or '').strip().splitlines() if l.strip()]
    check(строки[-1] if строки else 'obs_test.py', r.returncode == 0,
          '; '.join(l for l in строки if 'СБОЙ' in l)[:300])

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
