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

# Разбор хвоста SCENE берётся из check_prompt — там же, где по нему судит правило P1.
# Своя копия этой функции здесь жила до 18.08 и на двух текстах из 77 отвечала иначе (Ф153).
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from check_prompt import scene_tails  # noqa: E402

# Подпись серии — по префиксу кода, а не по имени файла результатов: в одном файле лежат
# две разные серии (v4 — это S и R, v5 — это F и C). Прежняя карта «файл → подпись» ставила
# все кадры 360-круга под заголовок «юбка и обувь» и прятала их от поиска по реестру (Ф71).
SERIES_TITLE = {
    'v3:P': 'v3 — ореховая комната, первая принятая серия (15.08)',
    'v4:S': 'S — юбка и обувь, ореховая комната (16.08)',
    'v4:R': 'R — круг 360 по ореховой комнате (16–17.08)',
    'v5:F': 'F — дальние и общие планы с якорем, ореховая комната (17.08)',
    'v5:C': 'C — ближние планы с якорем (17.08)',
    'v6:ST': 'ST — студия, белая циклорама (17.08)',
    'final:P': 'P-финал — точки съёмки и планировка ореховой комнаты (17.08)',
}

# Хронологический порядок разделов; ключи вне списка идут в конец по алфавиту.
SERIES_ORDER = ['v3:P', 'v4:S', 'v4:R', 'v5:F', 'v5:C', 'v6:ST', 'final:P']


def series_key(fname_base, code):
    """Ключ серии: файл результатов плюс буквенный префикс кода кадра."""
    m = re.match(r'[A-Za-z]+', code or '')
    return f'{fname_base}:{m.group(0)}' if m else fname_base


def хвост_и_предхвост(text):
    """Последняя и предпоследняя фразы SCENE. Имя своё, чтобы не заслонять общую реализацию:
    `scene_tails` определён ровно в одном месте комплекта, и проверка 6з за этим следит."""
    последняя, предпоследняя = scene_tails(text, 2)
    return (последняя or None, предпоследняя or None)


AMBIGUOUS = []


def find_prompt(code, series=''):
    """Файл промпта по коду кадра, в пределах своей серии.

    Коды уникальны только внутри серии: `P05` есть и в v3, и в final. Прежняя версия
    искала по всему `prompts/` и брала первое совпадение — кадру final:P05 подставился
    текст архивного v3:P05, то есть чужой промпт под видом сохранённого (Ф95).
    Теперь архив серии v3 виден только кадрам v3, а всем остальным — нет; при остатке
    неоднозначности ссылка не ставится вовсе и попадает в отчёт `--проверка`.
    """
    hits = []
    for pat in (f'prompts/{code}.txt', f'prompts/*/{code}.txt',
                f'prompts/*/*/{code}.txt', f'prompts/*/*/*/{code}.txt'):
        hits += [os.path.relpath(h, ROOT) for h in sorted(glob.glob(os.path.join(ROOT, pat)))]
    hits = sorted(set(hits))
    in_v3 = series.startswith('v3')
    scoped = [h for h in hits if ('архив/v3' in h) == in_v3]
    if len(scoped) == 1:
        return scoped[0]
    if len(scoped) > 1:
        AMBIGUOUS.append(f'{series}:{code} → ' + ', '.join(scoped))
    return None


def short(s, n=90):
    if not s:
        return '—'
    s = ' '.join(s.split())
    return s if len(s) <= n else s[:n - 1] + '…'


def collect():
    rows = []
    for f in sorted(glob.glob(os.path.join(ROOT, 'results', '*.json'))):
        base = os.path.splitext(os.path.basename(f))[0]
        data = json.load(open(f, encoding='utf-8'))
        for fname, v in data.items():
            if not isinstance(v, dict):
                continue
            verdict = str(v.get('вердикт', '')).lower()
            code = v.get('код') or os.path.splitext(fname)[0]
            series = series_key(base, code)
            path = find_prompt(code, series)
            tail = prev = None
            if path:
                tail, prev = хвост_и_предхвост(open(os.path.join(ROOT, path), encoding='utf-8').read())
            rows.append({
                'серия': series, 'код': code, 'файл_кадра': fname,
                'название': v.get('название', ''), 'лицо': v.get('лицо', ''),
                'узор': v.get('узор', ''), 'счёт': v.get('счёт', ''),
                'принят': ('ок' in verdict or 'принят' in verdict),
                'кроп': v.get('тип') == 'кроп',
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
    # Кроп из принятого кадра — не генерация: по законам C3 и D3 такие планы не снимаются
    # вовсе. Их нельзя считать ни в «снято», ни в «пробелах»: промпта у них не бывает
    # по устройству, а не по недосмотру (Ф96).
    gen = [r for r in rows if not r['кроп']]
    crops = [r for r in ok if r['кроп']]
    lost = [r for r in ok if not r['промпт'] and not r['кроп']]
    out = []
    A = out.append

    A('# РЕЕСТР ПРОМПТОВ — что сработало\n')
    A('Собирается скриптом `tools/registry.py` из `results/*.json` и текстов промптов.')
    A('Руками не правится: правка потеряется при следующей сборке.\n')
    A(f'Сгенерировано кадров: **{len(gen)}**, принято **{len(ok) - len(crops)}**. '
      f'Плюс {len(crops)} кропа из принятых кадров — это не генерации.\n')
    A(f'Текст промпта сохранён у **{len(ok) - len(crops) - len(lost)}** принятых кадров, '
      f'потерян у **{len(lost)}**.\n')
    A('Числа «сколько кадров вышло с первого раза» здесь нет и не будет: в `results/` нет '
      'поля, которое бы это фиксировало. Всё, что считалось по именам файлов или по суффиксам '
      'кодов, давало разные ответы и оказалось выдумкой (Ф97).\n')

    A('## Как этим пользоваться\n')
    A('Ищешь строку с нужным планом, берёшь её файл промпта за основу и меняешь два-три блока.')
    A('Колонка «последняя фраза SCENE» — это приоритетная позиция: самое сильное место промпта,')
    A('в неё ставится признак, который на этом плане ломается чаще всего.\n')

    by_product = {}
    for r in ok:
        by_product.setdefault('кардиган шоколадный в кремовый горошек', []).append(r)

    for product, items in by_product.items():
        A(f'## Изделие: {product}\n')
        keys = {i['серия'] for i in items}
        ordered = [k for k in SERIES_ORDER if k in keys] + sorted(keys - set(SERIES_ORDER))
        for series in ordered:
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
    lost = [r for r in ok if not r['промпт'] and not r['кроп']]
    crops = [r for r in ok if r['кроп']]
    gen = [r for r in rows if not r['кроп']]
    if '--проверка' in sys.argv:
        print(f'сгенерировано {len(gen)}, принято {len(ok) - len(crops)}, '
              f'кропов {len(crops)}, без промпта {len(lost)}')
        for r in lost:
            print(f'  {r["серия"]}/{r["код"]}  {r["название"]}')
        if AMBIGUOUS:
            print('НЕОДНОЗНАЧНЫЕ ССЫЛКИ НА ПРОМПТ (один код в двух местах):')
            for a in AMBIGUOUS:
                print('  ' + a)
            return 1
        print('неоднозначных ссылок нет')
        return 0
    dst = os.path.join(ROOT, 'prompts', 'РЕЕСТР.md')
    open(dst, 'w', encoding='utf-8').write(text)
    print(f'prompts/РЕЕСТР.md собран: сгенерировано {len(gen)}, принято '
          f'{len(ok) - len(crops)} плюс {len(crops)} кропа; '
          f'с промптом {len(ok) - len(crops) - len(lost)}, без {len(lost)}.')
    return 1 if AMBIGUOUS else 0


if __name__ == '__main__':
    sys.exit(main())
