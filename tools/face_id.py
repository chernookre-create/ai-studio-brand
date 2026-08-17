#!/usr/bin/env python3
"""Похожесть лица к эталону по эмбеддингу ArcFace (insightface buffalo_l).

Заменяет самодельную нормированную корреляцию из qc_frame.py. Причина замены — 15.08.2026:
корреляция по серому патчу дала −0.13 кадру, на котором заказчик и я глазами видим ту же
женщину, и 0.30 кадру с другим лицом. Она мерила ПОЗУ и свет, а не личность: любой поворот
головы и прядь на щеке обрушивали её к нулю. Числа старого журнала (0.11 … 0.66) этим и
объясняются: они ранжировали кадры по тому, насколько человек смотрит строго в объектив.

ArcFace сравнивает векторы признаков после выравнивания по глазам, поэтому поворот головы
до трёх четвертей и смена света его почти не двигают.

Шкала косинуса ArcFace (буфало_l, официальный порог верификации 0.28 при FMR 1e-4):
    ≥0.60  тот же человек, сомнений нет
    0.45-0.60  тот же человек
    0.28-0.45  вероятно тот же, но дрейф виден при сравнении рядом
    <0.28  другой человек — брак

    python3 tools/face_id.py --эталон ref.jpg кадр1.png кадр2.png
"""
import sys
import cv2
import numpy as np
from insightface.app import FaceAnalysis

_app = None


def app():
    global _app
    if _app is None:
        import logging
        logging.getLogger().setLevel(logging.ERROR)
        _app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
        _app.prepare(ctx_id=-1, det_size=(640, 640))
    return _app


def embed(path):
    im = cv2.imread(path)
    if im is None:
        return None, None
    h = im.shape[0]
    if h > 2000:                      # детектор не любит 4800 px по высоте
        k = 2000 / h
        im = cv2.resize(im, (int(im.shape[1] * k), 2000))
    fs = app().get(im)
    if not fs:
        return None, None
    f = max(fs, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
    w = float(f.bbox[2] - f.bbox[0])
    return f.normed_embedding, w


def verdict(s):
    if s is None:
        return 'лицо не найдено'
    if s >= 0.60:
        return 'тот же человек'
    if s >= 0.45:
        return 'тот же человек'
    if s >= 0.28:
        return 'вероятно тот же, дрейф виден'
    return 'ДРУГОЙ ЧЕЛОВЕК — брак'


def main():
    args = sys.argv[1:]
    i = args.index('--эталон')
    ref_path = args[i + 1]
    files = args[:i] + args[i + 2:]
    ref, rw = embed(ref_path)
    if ref is None:
        print('на эталоне лицо не найдено')
        return 1
    print(f"\nэталон: {ref_path.split('/')[-1]}  (лицо {rw:.0f} px в рабочем масштабе)")
    print(f"\n{'кадр':<26}{'лицо px':>9}{'косинус':>9}  вердикт")
    for p in files:
        e, w = embed(p)
        s = None if e is None else float(np.dot(ref, e))
        print(f"{p.split('/')[-1]:<26}{(f'{w:.0f}' if w else '—'):>9}"
              f"{(f'{s:.3f}' if s is not None else '—'):>9}  {verdict(s)}")
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
