#!/usr/bin/env python3
"""Реестр промптов: что сработало, на каком плане, с каким числом.

    python3 tools/registry.py            собрать prompts/РЕЕСТР.md
    python3 tools/registry.py --проверка  только показать пробелы, ничего не писать

Зачем. До 17.08 проект записывал почти только отрицательные результаты: шестьдесят с лишним
факапов с числами и ни одной таблицы «вот этот хвост дал 0.88 на таком плане». Из-за этого
следующий кадр начинался с памяти сессии, а память сессии умирает вместе с контейнером.

Реестр строится из двух источников и ничего не выдумывает:
  results/<серия>.json  — вердикты и замеры прогонов;
  prompts/**.txt        — тексты промптов; из них берётся последняя фраза SCENE, то есть
                          приоритетная позиция, ради которой всё и затевалось.

Кадры, для которых текст промпта не сохранён, помечаются прямо в таблице. Это не косметика:
пробел в реестре — это то, что нельзя воспроизвести.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BLOCKS = ['REFERENCES', 'PRESERVE', 'HAIR', 'OUTFIT', 'LOCATION', 'STREET GEOGRAPHY',
          'GEOGRAPHY', 'CAMERA', 'SCENE', 'LIGHT', 'GRADE', 'EXCLUDE']

SERIES_TITLE = {
    'v3': 'v3 — ореховая комната, первая принятая серия',
    'v4': 'S — юбка и обувь, ореховая комната',
    'v5': '360 — круг по ореховой комнате',
    'v6': 'ST — студия, белая циклорама',
    'final': 'финальная выборка v3',
}


def scene_tail(text):
    """Последняя и предпоследняя фразы блока SCENE — приоритетная позиция промпта."""
    if 'SCENE' not in text:
        return None, None
    body = text.split('SCENE', 1)[1]
    for b in BLOCKS:
        if f'\n{b}' in body:
            body = body.split(f'\n{b}', 1)[0]
    body = body.strip()
    sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', body) if s.strip()]
    if not sents:
        return None, None
    return (sents[-1], sents[-2] if len(sents) > 1 else None)


def find_prompt(code):
    """Файл промпта по коду кадра. Ищем и в корне prompts/, и в подпапках серий."""
    for pat in (f'prompts/{code}.txt', f'prompts/*/{code}.txt',
                f'prompts/*/*/{code}.txt', f'prompts/*/*/*/{code}.txt'):
        hits = sorted(glob.glob(os.path.join(ROOT, pat)))
        if hits:
            return os.path.relpath(hits[0], ROOT)
    return None


def short(s, n=90):
    if not s:
        return '—'
    s = ' '.join(s.split())
    return s if len(s) <= n else s[:n - 1] + '…'


def collect():
    rows = []
    for f in sorted(glob.glob(os.path.join(ROOT, 'results', '*.json'))):
        series = os.path.splitext(os.path.basename(f))[0]
        data = json.load(open(f, encoding='utf-8'))
        for fname, v in data.items():
            if not isinstance(v, dict):
                continue
            verdict = str(v.get('вердикт', '')).lower()
            code = v.get('код') or os.path.splitext(fname)[0]
            path = find_prompt(code)
            tail = prev = None
            if path:
                tail, prev = scene_tail(open(os.path.join(ROOT, path), encoding='utf-8').read())
            rows.append({
                'серия': series, 'код': code, 'файл_кадра': fname,
                'название': v.get('название', ''), 'лицо': v.get('лицо', ''),
                'узор': v.get('узор', ''), 'счёт': v.get('счёт', ''),
                'принят': ('ок' in verdict or 'принят' in verdict),
                'промпт': path, 'хвост': tail, 'предпоследняя': prev,
            })
    return rows


def face_num(s):
    try:
        return float(str(s).replace(',', '.'))
    except ValueError:
        return None


def build(rows):
    ok = [r for r in rows if r['принят']]
    lost = [r for r in ok if not r['промпт']]
    out = []
    A = out.append

    A('# РЕЕСТР ПРОМПТОВ — что сработало\n')
    A('Собирается скриптом `tools/registry.py` из `results/*.json` и текстов промптов.')
    A('Руками не правится: правка потеряется при следующей сборке.\n')
    A(f'Принятых кадров: **{len(ok)}** из {len(rows)} снятых. '
      f'Текст промпта сохранён у **{len(ok) - len(lost)}**, потерян у **{len(lost)}**.\n')

    A('## Как этим пользоваться\n')
    A('Ищешь строку с нужным планом, берёшь её файл промпта за основу и меняешь два-три блока.')
    A('Колонка «последняя фраза SCENE» — это приоритетная позиция: самое сильное место промпта,')
    A('в неё ставится признак, который на этом плане ломается чаще всего.\n')

    by_product = {}
    for r in ok:
        by_product.setdefault('кардиган шоколадный в кремовый горошек', []).append(r)

    for product, items in by_product.items():
        A(f'## Изделие: {product}\n')
        for series in sorted({i['серия'] for i in items}):
            A(f'### {SERIES_TITLE.get(series, series)}\n')
            A('| код | план | лицо | узор | последняя фраза SCENE | промпт |')
            A('|---|---|---|---|---|---|')
            for r in sorted([i for i in items if i['серия'] == series], key=lambda x: x['код']):
                A(f'| {r["код"]} | {short(r["название"], 40)} | {r["лицо"] or "—"} | '
                  f'{r["узор"] or "—"} | {short(r["хвост"], 100)} | '
                  f'{"`" + r["промпт"] + "`" if r["промпт"] else "**не сохранён**"} |')
            A('')

    withp = [r for r in ok if r['хвост']]
    if withp:
        from collections import Counter
        c = Counter(r['хвост'] for r in withp)
        top, n = c.most_common(1)[0]
        if n >= max(3, len(withp) // 2):
            A('## Что видно по хвостам — и чего не видно\n')
            A(f'У **{n}** из {len(withp)} сохранённых промптов последняя фраза SCENE одна и та же:\n')
            A(f'> {top}\n')
            A('Это фраза настроения, а не признак. То есть закон «последняя строка SCENE — самая')
            A('сильная» в сохранённых текстах **не виден**: он выведен на серии R (16.08), где')
            A('строка про застёжку переносилась в конец, и тексты той серии не сохранились.')
            A('Закон подтверждён контрольным прогоном и записан в «ЗАКОНАХ», но реестр его пока')
            A('не подтверждает — доказательство лежит в журнале, а не в базе промптов.\n')
            A('Практический вывод: в новых кадрах приоритетная строка ставится последней явно, и')
            A('тогда следующая пересборка реестра покажет её в этой колонке.\n')

    scored = [(face_num(r['лицо']), r) for r in ok]
    scored = sorted([s for s in scored if s[0] is not None], key=lambda x: -x[0])[:8]
    if scored:
        A('## Лучшие по лицу\n')
        A('| лицо | код | план | последняя фраза SCENE |')
        A('|---|---|---|---|')
        for val, r in scored:
            A(f'| **{val:.3f}** | {r["код"]} | {short(r["название"], 40)} | {short(r["хвост"], 110)} |')
        A('')

    if lost:
        A('## Пробелы — принятые кадры без сохранённого промпта\n')
        A('Эти кадры воспроизвести нельзя: числа есть, текста нет. Серия снималась правкой')
        A('блоков в браузере от общей базы, и каждый вариант не сохранялся на диск.\n')
        A('| серия | код | план | лицо |')
        A('|---|---|---|---|')
        for r in sorted(lost, key=lambda x: (x['серия'], x['код'])):
            A(f'| {r["серия"]} | {r["код"]} | {short(r["название"], 45)} | {r["лицо"] or "—"} |')
        A('')
        A('**Правило, выведенное отсюда:** текст каждого отправленного кадра пишется в')
        A('`prompts/<код>.txt` в момент отправки, а не после приёмки. Кадр без сохранённого')
        A('промпта считается неповторимым, каким бы удачным он ни вышел.\n')

    return '\n'.join(out)


def main():
    rows = collect()
    if not rows:
        print('results/*.json пусты — реестр собирать не из чего')
        return 1
    text = build(rows)
    ok = [r for r in rows if r['принят']]
    lost = [r for r in ok if not r['промпт']]
    if '--проверка' in sys.argv:
        print(f'принятых {len(ok)}, без промпта {len(lost)}')
        for r in lost:
            print(f'  {r["серия"]}/{r["код"]}  {r["название"]}')
        return 0
    dst = os.path.join(ROOT, 'prompts', 'РЕЕСТР.md')
    open(dst, 'w', encoding='utf-8').write(text)
    print(f'prompts/РЕЕСТР.md собран: {len(ok)} принятых кадров, '
          f'{len(ok) - len(lost)} с промптом, {len(lost)} без.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
