#!/usr/bin/env python3
"""Срез чёрной рамки, которую модель иногда рисует по краю файла (Ф44).

    python3 tools/trim_border.py 03_images/v4/R03.png

Это кроп, а не правка содержимого: ни один пиксель кадра не перерисовывается, снимается только
тёмная кайма по периметру. Порог — средняя яркость полосы ниже 20 при яркости кадра выше 40.
"""
import sys

import numpy as np
from PIL import Image

THR = 22


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

    top = scan(lum.mean(axis=1))
    bot = scan(lum.mean(axis=1)[::-1])
    left = scan(lum.mean(axis=0))
    right = scan(lum.mean(axis=0)[::-1])
    if top + bot + left + right == 0:
        return None
    out = im.crop((left, top, w - right, h - bot))
    out.save(path)
    return (left, top, right, bot, out.size)


if __name__ == '__main__':
    for p in sys.argv[1:]:
        r = trim(p)
        print(f"{p.split('/')[-1]}: " + (f"срезано л{r[0]} в{r[1]} п{r[2]} н{r[3]} → {r[4][0]}×{r[4][1]}"
                                         if r else 'рамки нет'))
