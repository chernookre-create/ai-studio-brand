#!/usr/bin/env python3
"""Сборка папки на скачку после прогона: подписанные кадры, контактный лист, README, архив.

Появился 15.08.2026 по просьбе человека: после каждого прогона отдавать сразу папку, где у
каждого кадра видно, что это за кадр и прошёл ли он счёт. Оригиналы PNG не трогаются — подпись
живёт в имени файла, в контактном листе и в README, а не поверх картинки.

    python3 tools/deliver.py <прогон> <папка_с_png>
"""
import csv
import json
import os
import shutil
import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from obs import операция
except Exception:                                                # noqa: BLE001
    операция = None                    # наблюдаемость необязательна: сдача важнее журнала
from PIL import Image, ImageDraw, ImageFont

F = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


# Данные конкретной съёмки — из refs/CURRENT.json, а не из кода: эталон узора и разрешение
# оригинала были зашиты здесь литералами и переезжали бы вместе со сменой съёмки молча (Ф125).
def _текущее(ключ, по_умолчанию):
    import json as _j
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'refs', 'CURRENT.json')
    try:
        return _j.load(open(p, encoding='utf-8')).get(ключ, по_умолчанию)
    except Exception:
        return по_умолчанию


ЭТАЛОН = _текущее('эталон_узора', 'не задан')
РАЗРЕШЕНИЕ = _текущее('разрешение_оригинала', 'не задано')


def load_meta(src):
    """meta.json рядом с кадрами: {файл: {название, лицо, узор, счёт, вердикт}}"""
    p = os.path.join(src, 'meta.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}


def slug(s):
    return s.replace(' ', '-').replace('/', '-')


def build(run, src):
    meta = load_meta(src)
    out = f'05_deliver/{run}'
    # Прежде здесь стоял безусловный rmtree: повторный запуск с тем же именем прогона молча
    # стирал предыдущую сдачу вместе с тем, что заказчик мог туда положить (Ф142).
    if os.path.exists(out):
        if '--перезаписать' in sys.argv:
            shutil.rmtree(out, ignore_errors=True)
        else:
            i = 2
            while os.path.exists(f'{out}-{i}'):
                i += 1
            print(f'Папка {out} уже есть — собираю рядом: {out}-{i}. '
                  f'Перезаписать поверх: --перезаписать')
            out = f'{out}-{i}'
    os.makedirs(f'{out}/кадры', exist_ok=True)

    rows, tiles = [], []
    for name in sorted(meta):
        p = os.path.join(src, name)
        if not os.path.exists(p):
            continue
        m = meta[name]
        v = m['вердикт']
        mark = 'ОК' if v == 'ок' else 'БРАК'
        new = f"{m['код']}_{slug(m['название'])}_{mark}.jpg"
        im = cv2.imread(p)
        cv2.imwrite(f'{out}/кадры/{new}', im, [cv2.IMWRITE_JPEG_QUALITY, 95])
        rows.append((m['код'], m['название'], m['лицо'], m['узор'], m['счёт'], mark, new))

        # плитка для контактного листа: кадр + подпись под ним.
        # Подпись переносится по ширине плитки — иначе длинные названия уезжают за край
        # (проверено 15.08: первый лист вышел с обрезанным текстом).
        W, H, CAP = 380, 507, 150
        t = cv2.resize(im, (W, H))
        tile = Image.fromarray(cv2.cvtColor(np.vstack([t, np.full((CAP, W, 3), 18, np.uint8)]),
                                            cv2.COLOR_BGR2RGB))
        d = ImageDraw.Draw(tile)
        col = (150, 230, 120) if mark == 'ОК' else (240, 130, 120)

        def wrap(text, font, width):
            words, lines, cur = text.split(), [], ''
            for w_ in words:
                probe = (cur + ' ' + w_).strip()
                if d.textlength(probe, font=font) <= width:
                    cur = probe
                else:
                    lines.append(cur)
                    cur = w_
            if cur:
                lines.append(cur)
            return lines

        f_hd, f_md, f_sm = (ImageFont.truetype(FB, 17), ImageFont.truetype(F, 15),
                            ImageFont.truetype(F, 14))
        y = H + 7
        for ln in wrap(f"{m['код']}  {m['название']}", f_hd, W - 20)[:2]:
            d.text((10, y), ln, font=f_hd, fill=(240, 240, 240))
            y += 21
        d.text((10, y), f"лицо {m['лицо']}   узор {m['узор']}", font=f_md, fill=(175, 175, 175))
        y += 22
        for ln in wrap(m['счёт'], f_sm, W - 20)[:3]:
            d.text((10, y), ln, font=f_sm, fill=col)
            y += 18
        tiles.append(cv2.cvtColor(np.array(tile), cv2.COLOR_RGB2BGR))

    while len(tiles) % 3:
        tiles.append(np.full_like(tiles[0], 18))
    sheet = np.vstack([np.hstack(tiles[i:i + 3]) for i in range(0, len(tiles), 3)])
    cv2.imwrite(f'{out}/КОНТАКТНЫЙ-ЛИСТ.jpg', sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])

    with open(f'{out}/ЗАМЕРЫ.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['код', 'название', 'лицо ArcFace', 'узор к эталону', 'счёт глазами',
                    'вердикт', 'файл'])
        w.writerows(rows)

    ok = [r for r in rows if r[5] == 'ОК']
    with open(f'{out}/README.md', 'w', encoding='utf-8') as f:
        f.write(f'# Прогон {run}\n\n')
        f.write(f'Кадров в прогоне: {len(rows)}. Прошли счёт: {len(ok)}.\n\n')
        f.write(f'Норма: лицо ArcFace ≥0.45 (цель ≥0.60), узор ±12% от эталона {ЭТАЛОН}.\n')
        f.write(f'Оригиналы PNG {РАЗРЕШЕНИЕ} остаются в проекте, здесь JPEG качества 95.\n\n')
        f.write('| Код | Кадр | Лицо | Узор | Счёт глазами | Вердикт |\n|---|---|---|---|---|---|\n')
        for c, n, lf, uz, sc, mk, _ in rows:
            f.write(f'| {c} | {n} | {lf} | {uz} | {sc} | **{mk}** |\n')

    # Код возврата проверяется: без zip в системе команда просто не выполнится, а скрипт
    # печатал «архив собран» и возвращал путь к несуществующему файлу (Ф137).
    try:
        r = subprocess.run(['zip', '-qr', f'{out}.zip', out])
        code = r.returncode
    except FileNotFoundError:
        code = 127
    if code != 0 or not os.path.exists(f'{out}.zip'):
        print(f'ОШИБКА: архив не собран (код {code}). Папка готова: {out}')
        return out
    print(f'{out}.zip — кадров {len(rows)}, ОК {len(ok)}')
    return f'{out}.zip'


ПОДСКАЗКА = """
    python3 tools/deliver.py <имя_прогона> <папка_с_кадрами>

Имя прогона — как назвать сдачу, например `18-08_серия-E`. Папка с кадрами — та, куда
скачаны PNG из сервиса. Результат ложится в 05_deliver/<имя_прогона> рабочей директории.
Повторный запуск с тем же именем собирает рядом, старую сдачу не трогает; затереть
поверх — флаг --перезаписать.
"""


if __name__ == '__main__':
    # Без аргументов скрипт печатал трассировку IndexError: человек видел питон вместо
    # строчки «скажи, как назвать прогон» (тот же класс, что Ф150 у face_id).
    _args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(_args) < 2:
        print('Нужны два аргумента: имя прогона и папка с кадрами.' + ПОДСКАЗКА)
        sys.exit(2)
    if not os.path.isdir(_args[1]):
        print(f'Папки с кадрами нет: {_args[1]}' + ПОДСКАЗКА)
        sys.exit(2)
    if операция is None:
        build(_args[0], _args[1])
    else:
        with операция('сдача', код=_args[0], ключ='сдача прогона') as оп:
            оп.этап('Validation')
            оп.этап('Writes')
            путь = build(_args[0], _args[1])
            оп.записал(str(путь))
            оп.этап('Result')
            оп.готово('собрано')
