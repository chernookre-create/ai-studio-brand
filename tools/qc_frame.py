#!/usr/bin/env python3
"""Проверка кадра до показа заказчику. Ничего не генерирует и не правит — только считает.

    python3 tools/qc_frame.py --эталон 03_images/v3/P01b.png 03_images/v3/*.png

Что меряется здесь: масштаб узора — шаг горошка, отнесённый к ширине лица (норма ±12% от
эталона). Похожесть лица здесь НЕ меряется: см. Ф11, корреляция по серому патчу ранжировала
кадры по разрешению и позе, а не по личности. Лицо меряется отдельно, tools/face_id.py (ArcFace).

Переписано 15.08.2026 (Ф17). Рамки нет вовсе — горошины ищутся по всему кадру двумя
признаками: локальный контраст (светлее окружения на 12 единиц L) и цветность (a* < 12,
b* < 28). Ложное лицо на кадре без головы отсекается порогом MIN_FACE_FRAC.
"""
import sys

import cv2
import numpy as np

FACE = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

WORK_W = 1600          # все замеры на одной ширине, иначе кадры разного размера несравнимы
MIN_FACE_FRAC = 0.08   # бокс уже этой доли ширины кадра — не лицо, а ложное срабатывание
TOL = 0.12             # допуск по масштабу узора


def to_work(im):
    h, w = im.shape[:2]
    return cv2.resize(im, (WORK_W, int(h * WORK_W / w)), interpolation=cv2.INTER_AREA)


def face_width(im):
    """Ширина лица в пикселях рабочего масштаба. None, если лица нет."""
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    f = FACE.detectMultiScale(g, 1.1, 5, minSize=(60, 60))
    if len(f) == 0:
        return None
    b = sorted(f, key=lambda r: -r[2] * r[3])[0]
    if b[2] < MIN_FACE_FRAC * im.shape[1]:
        return None
    return float(b[2])


def dot_pitch(im):
    """Шаг горошка: медиана расстояния до двух ближайших соседей по облаку горошин."""
    lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB)
    L = lab[..., 0].astype(np.float32)
    A = lab[..., 1].astype(np.float32) - 128
    B = lab[..., 2].astype(np.float32) - 128

    local = L - cv2.GaussianBlur(L, (0, 0), 25)
    m = ((local > 12) & (A < 12) & (B < 28)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))

    n, _, st, cen = cv2.connectedComponentsWithStats(m)
    cand = [(st[i, 4], cen[i], st[i, 2], st[i, 3]) for i in range(1, n) if st[i, 4] > 25]
    if len(cand) < 12:
        return None
    med = np.median([c[0] for c in cand])
    keep = [c for c in cand if 0.45 * med < c[0] < 2.2 * med and 0.5 < c[2] / max(c[3], 1) < 2.0]
    if len(keep) < 12:
        return None

    pts = np.array([c[1] for c in keep])
    d = np.linalg.norm(pts[:, None] - pts[None], axis=2)
    nn = np.sort(d, axis=1)[:, 1:4].mean(axis=1)
    pts = pts[nn < 1.8 * np.median(nn)]
    if len(pts) < 12:
        return None

    d = np.linalg.norm(pts[:, None] - pts[None], axis=2)
    return float(np.median(np.sort(d, axis=1)[:, 1:3])), int(len(pts))


def measure(path):
    im = cv2.imread(path)
    if im is None:
        return None
    im = to_work(im)
    fw = face_width(im)
    dp = dot_pitch(im)
    pitch, ndots = dp if dp else (None, 0)
    ratio = (pitch / fw) if (pitch and fw) else None
    return {'pitch': pitch, 'face': fw, 'ratio': ratio, 'n': ndots}


def fmt(v, spec):
    return format(v, spec) if v is not None else '—'


def main():
    args = sys.argv[1:]
    ref_path = None
    if '--эталон' in args:
        i = args.index('--эталон')
        ref_path = args[i + 1]
        args = args[:i] + args[i + 2:]

    ref = measure(ref_path) if ref_path else None
    if ref_path and (ref is None or ref['ratio'] is None):
        why = 'файл не прочитан' if ref is None else 'нет лица или нет горошка'
        print(f'\nЭталон {ref_path} не посчитан: {why}. Сравнивать не с чем.\n')
        return 1

    bad_total = 0
    print(f"\n{'кадр':<22}{'шаг':>8}{'лицо':>8}{'шаг/лицо':>10}{'откл.':>8}  вердикт")
    for p in args:
        r = measure(p)
        name = p.split('/')[-1]
        if r is None:
            print(f'{name:<22}  не прочитан')
            bad_total += 1
            continue

        nomeasure = []
        if r['pitch'] is None:
            nomeasure.append('узор не измерен')
        if r['face'] is None:
            nomeasure.append('лицо не найдено, нормировать не на что')

        dev = None
        bad = []
        if ref and r['ratio']:
            dev = r['ratio'] / ref['ratio'] - 1
            if abs(dev) > TOL:
                bad.append(f'узор {dev * 100:+.0f}%')

        if bad:
            verdict, rc = 'БРАК: ' + ', '.join(bad), 1
        elif nomeasure:
            verdict, rc = 'НЕ ПОСЧИТАН: ' + ', '.join(nomeasure), 1
        elif ref is None:
            verdict, rc = 'замер снят, эталон не задан — сравнения нет', 0
        else:
            verdict, rc = 'ОК по узору', 0
        bad_total += rc

        print(f"{name:<22}{fmt(r['pitch'], '.1f'):>8}{fmt(r['face'], '.0f'):>8}"
              f"{fmt(r['ratio'], '.4f'):>10}"
              f"{(f'{dev * 100:+.0f}%' if dev is not None else '—'):>8}  {verdict}")

    print('\nЛицо этим скриптом НЕ меряется — tools/face_id.py, ArcFace, порог 0.45, цель 0.60.')
    print('Далее глазами: три пуговицы и ни одной больше, рисунок пуговицы — гладкий купол в узком')
    print('витом ободке, V-вырез, нет полосы по низу и манжетам, низ перекрывает верх кармана.\n')
    return 1 if bad_total else 0


if __name__ == '__main__':
    sys.exit(main())
