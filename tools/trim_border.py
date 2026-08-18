#!/usr/bin/env python3
"""Срез чёрной рамки, которую модель иногда рисует по краю файла (Ф44).

    python3 tools/trim_border.py 03_images/v4/R03.png

Это кроп, а не правка содержимого: ни один пиксель кадра не перерисовывается, снимается только
тёмная кайма по периметру.

Условия среза (все три, иначе кадр не трогается):
    средняя яркость полосы ниже THR;
    средняя яркость всего кадра выше FRAME_MIN — иначе это тёмный кадр, а не кайма;
    суммарный срез по стороне не больше MAX_FRAC от размера.

**Результат пишется рядом, оригинал не трогается.** До 18.08 скрипт сохранял поверх исходника:
кадр 800×600 с тёмной полосой 180 px (тень на стене, не кайма) превращался в 600×620 без
возможности вернуть. Второе условие в этой строке было обещано с самого начала и в коде
отсутствовало (Ф141).
"""
import sys

import numpy as np
from PIL import Image

THR = 22          # ниже этой средней яркости полоса считается каймой
FRAME_MIN = 40    # если весь кадр темнее — это ночная сцена, не кайма
MAX_FRAC = 0.12   # больше этой доли стороны не срезаем: значит, это содержимое


def trim(path):
    im = Image.open(path).convert('RGB')
    a = np.array(im).astype(np.float32)
    h, w = a.shape[:2]
    lum = a.mean(axis=2)

    def scan(vals):
        i = 0
        while i < len(vals) and vals[i] < THR:
            i += 1
        return i

    if lum.mean() < FRAME_MIN:
        return None, 'кадр темнее порога — это не кайма, а тёмная сцена'

    top = scan(lum.mean(axis=1))
    bot = scan(lum.mean(axis=1)[::-1])
    left = scan(lum.mean(axis=0))
    right = scan(lum.mean(axis=0)[::-1])
    if top + bot + left + right == 0:
        return None, 'рамки нет'
    if max(top + bot, left + right) > MAX_FRAC * min(h, w):
        return None, f'срез больше {int(MAX_FRAC * 100)}% стороны — похоже на содержимое, не трогаю'

    out = im.crop((left, top, w - right, h - bot))
    dst = path.rsplit('.', 1)
    dst = f'{dst[0]}_trim.{dst[1]}' if len(dst) == 2 else path + '_trim'
    out.save(dst)
    return (left, top, right, bot, out.size, dst), None


if __name__ == '__main__':
    for p in sys.argv[1:]:
        r, why = trim(p)
        if r:
            print(f"{p.split('/')[-1]}: срезано л{r[0]} в{r[1]} п{r[2]} н{r[3]} → "
                  f"{r[4][0]}×{r[4][1]}, записано в {r[5].split('/')[-1]} (оригинал цел)")
        else:
            print(f"{p.split('/')[-1]}: {why}")
