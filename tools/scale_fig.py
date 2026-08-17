#!/usr/bin/env python3
"""Масштаб узора, нормированный ростом фигуры, а не шириной лица.

    python3 tools/scale_fig.py --эталон 03_images/v4/S01c.png 03_images/v4/S02.png

Зачем: штатная метрика tools/qc_frame.py делит шаг горошка на ширину лица. При повороте
головы ширина лица падает сама по себе, и метрика показывает рост узора там, где узор не
менялся (Ф32). Рост фигуры от макушки до пола при повороте корпуса меняется на единицы
процентов, поэтому здесь нормировка идёт на него.

Ограничения: работает только на кадрах, где фигура видна целиком и не обрезана рамкой. Для
кроп-кадров бессмысленно — там нормировать не на что, пользоваться qc_frame.py.

Калибровка 16.08.2026: S01c и S02 сняты одним набором и одним промптом, отличается только
поза. qc_frame даёт +11% и +19% (разница 8%), scale_fig даёт 15.97 и 16.34 (разница 2.3%).
Вывод: восемь процентов из девятнадцати — артефакт поворота головы, а не узор.
"""
import io
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from qc_frame import dot_pitch, to_work  # noqa: E402

TOL = 0.12


def figure_height(im):
    """Высота фигуры в пикселях рабочего масштаба, по маске rembg."""
    from rembg import remove
    ok, buf = cv2.imencode('.png', im)
    a = np.array(Image.open(io.BytesIO(remove(buf.tobytes()))).convert('RGBA'))[..., 3]
    ys, _ = np.where(a > 128)
    if len(ys) < 1000:
        return None
    return float(ys.max() - ys.min())


def measure(path):
    im = cv2.imread(path)
    if im is None:
        return None
    im = to_work(im)
    dp = dot_pitch(im)
    fh = figure_height(im)
    pitch = dp[0] if dp else None
    return {'pitch': pitch, 'fig': fh,
            'ratio': (pitch / fh * 1000) if (pitch and fh) else None}


def main():
    args = sys.argv[1:]
    ref_path = None
    if '--эталон' in args:
        i = args.index('--эталон')
        ref_path = args[i + 1]
        args = args[:i] + args[i + 2:]

    ref = measure(ref_path) if ref_path else None
    if ref_path and (ref is None or ref['ratio'] is None):
        print(f'\nЭталон {ref_path} не посчитан: фигура или горошек не найдены.\n')
        return 1

    bad = 0
    print(f"\n{'кадр':<22}{'шаг':>8}{'рост':>8}{'шаг/рост':>10}{'откл.':>8}  вердикт")
    for p in args:
        r = measure(p)
        name = p.split('/')[-1]
        if r is None or r['ratio'] is None:
            print(f'{name:<22}  НЕ ПОСЧИТАН: фигура целиком не видна или горошек не найден')
            bad += 1
            continue
        dev = (r['ratio'] / ref['ratio'] - 1) if ref else None
        if dev is None:
            verdict = 'замер снят, эталон не задан'
        elif abs(dev) > TOL:
            verdict, bad = f'БРАК: узор {dev * 100:+.0f}%', bad + 1
        else:
            verdict = 'ОК по узору'
        print(f"{name:<22}{r['pitch']:>8.1f}{r['fig']:>8.0f}{r['ratio']:>10.2f}"
              f"{(f'{dev * 100:+.0f}%' if dev is not None else '—'):>8}  {verdict}")
    print()
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
