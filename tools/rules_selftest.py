#!/usr/bin/env python3
"""Проверка самих правил check_prompt: каждое обязано уметь упасть.

    python3 tools/rules_selftest.py

Зачем. 18.08.2026 счёт показал: из 53 правил четырёх классов **35 не сработали ни разу**
за всю историю проекта. Правило, которое ни разу не падало, ничем не отличается от правила,
которое упасть не может — а два таких уже находили: `E3` требовало вписывать запрет свойства,
неисполнимый по закону A7 (Ф119), `L1` искало одинокое слово `identical`, которое есть в любом
промпте из-за `pixel-identical` про лицо, и не падало никогда (Ф120).

Как устроено. Для каждого правила лежит пара: образец своего класса (заведомо зелёный) и
**поломка** — минимальная правка текста, после которой это правило обязано покраснеть.
Проверяются оба конца: на целом образце правило зелёное, на сломанном — красное. Если
поломка не роняет правило, значит правило не умеет падать, и виноват не образец.

Код возврата 1 при любом расхождении. Запускается из selftest.py пунктом 5б.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import check_prompt as C            # noqa: E402

ОБРАЗЦЫ = {
    'фото':     'prompts/кардиган-шоколад-горошек/E04_waist_count.txt',
    'интерьер': 'prompts/локации/INT01.txt',
    'пэкшот':   'prompts/предметка/PACK_SKIRT.txt',
    'видео':    'prompts/видео/V_TEMPLATE_образец.txt',
}
# Общее правило A1 живёт не в списке, а в самом run(): оно одно на все четыре класса.
# Чтобы его нельзя было забыть, оно подмешивается в набор каждого класса как обычное правило.
A1 = ('A1', lambda t: not C.чужие_слова(t),
      'в строках «Image N:» слова предмета, которого в наборе нет',
      'закон A1 · картинка сильнее текста')

НАБОРЫ = {'фото': C.CHECKS_PHOTO + [A1], 'интерьер': C.CHECKS_INTERIOR + [A1],
          'пэкшот': C.CHECKS_PACKSHOT + [A1], 'видео': C.CHECKS_VIDEO + [A1]}


def выкинуть(*шаблоны):
    """Поломка вычитанием: убрать из текста всё, что подходит под шаблон."""
    def f(t):
        for ш in шаблоны:
            t = re.sub(ш, '', t, flags=re.I)
        return t
    return f


def в_хвост_scene(фраза):
    """Поломка добавлением: дописать фразу последней строкой блока SCENE."""
    def f(t):
        i = t.upper().index('\nLIGHT')
        return t[:i] + ' ' + фраза + t[i:]
    return f


def подменить_слот7(чужое):
    """Поломка правила A1: описать слот словами предмета, которого в наборе нет.

    Если строки «Image 7:» в образце нет (видео, крупные планы), она дописывается — сам факт
    описания несуществующего предмета от этого не меняется.
    """
    def f(t):
        строки = t.splitlines()
        for i, l in enumerate(строки):
            if l.startswith('Image 7:'):
                строки[i] = f'Image 7: the {чужое} on a white background.'
                return '\n'.join(строки)
        return f'Image 7: the {чужое} on a white background.\n' + t
    return f


def дописать(фраза):
    return lambda t: t + '\n' + фраза


# (класс, код) → поломка. Ровно по одной на каждое правило каждого класса.
ПОЛОМКИ = {
    # ── ФОТО ────────────────────────────────────────────────────────────────
    ('фото', 'A1'): подменить_слот7('oxblood loafers'),
    ('фото', 'B1'): выкинуть(r'\nGEOGRAPHY'),
    ('фото', 'B2'): выкинуть(r'HIGHEST PRIORITY'),
    ('фото', 'R1'): выкинуть(r'\bImage\s+\d'),
    ('фото', 'R2'): выкинуть(r'style reference'),
    ('фото', 'R3'): выкинуть(r'pixel-identical'),
    ('фото', 'C1'): выкинуть(r'\bexactly (one|two|three|four|five|six|\d+)\b'),
    ('фото', 'C2'): выкинуть(r'no (fourth|fifth|second|third|extra) button', r'no additional'),
    ('фото', 'C3'): выкинуть(r'never a (round|crew|v-)\w*', r'no changed neckline'),
    ('фото', 'E1'): выкинуть(r'no (band|rib|ribbed|elastic)\w*'),
    ('фото', 'E2'): выкинуть(r'single photograph only', r'no collage', r'no multiple panels'),
    ('фото', 'E4'): lambda t: re.sub(r'\bno ', 'without ', t, flags=re.I),
    ('фото', 'S1'): выкинуть(r'mid-action', r'still settling', r'has just', r'halfway', r'not yet'),
    ('фото', 'S2'): выкинуть(r'\b(wind|gust|momentum|inertia|step\w*|pushed off|swing\w*)\b'),
    ('фото', 'S3'): выкинуть(r'one (shoulder|hip|knee|hand)'),
    ('фото', 'L1'): выкинуть(r'\b(light|lighting|weather)\b'),
    ('фото', 'P1'): в_хвост_scene('The whole picture feels calm and quiet.'),
    ('фото', 'P2'): в_хвост_scene('No black border along the file edge.'),
    ('фото', 'P3'): в_хвост_scene('Her hair stays in the low knot.'),
    ('фото', 'G1'): выкинуть(r'film grain', r'35mm colour film', r'no HDR'),
    ('фото', 'W1'): в_хвост_scene('The knit lies smooth across her back.'),
    ('фото', 'W2'): в_хвост_scene('A dynamic editorial mood.'),
    # ── ИНТЕРЬЕР ────────────────────────────────────────────────────────────
    ('интерьер', 'A1'): подменить_слот7('oxblood loafers'),
    ('интерьер', 'B1'): выкинуть(r'\nGEOGRAPHY'),
    ('интерьер', 'B2'): выкинуть(r'HIGHEST PRIORITY'),
    ('интерьер', 'R1'): выкинуть(r'\bImage\s+\d'),
    ('интерьер', 'R2'): выкинуть(r'style reference'),
    ('интерьер', 'I1'): выкинуть(r'\bno (people|person|model|figure)\w*'),
    ('интерьер', 'I2'): выкинуть(r'no (furniture|chair|table)\w*'),
    ('интерьер', 'I3'): выкинуть(r'walnut', r'oak', r'wood panel\w*', r'panelling'),
    ('интерьер', 'I4'): выкинуть(r'no (white wall|painted wall|plaster|wallpaper)'),
    ('интерьер', 'L1'): выкинуть(r'\b(light|lighting|flash)\b', r'on-camera flash'),
    ('интерьер', 'G1'): выкинуть(r'film grain', r'35mm colour film', r'no HDR',
                                 r'no digital sharpening'),
    ('интерьер', 'E4'): выкинуть(r'no collage', r'single photograph only'),
    ('интерьер', 'E5'): выкинуть(r'no text', r'no logos'),
    # ── ПЭКШОТ ──────────────────────────────────────────────────────────────
    ('пэкшот', 'A1'): подменить_слот7('oxblood loafers'),
    ('пэкшот', 'B1'): выкинуть(r'\nGEOGRAPHY'),
    ('пэкшот', 'B2'): выкинуть(r'HIGHEST PRIORITY'),
    ('пэкшот', 'R1'): выкинуть(r'\bImage\s+\d'),
    ('пэкшот', 'R2'): выкинуть(r'style reference'),
    ('пэкшот', 'K1'): выкинуть(r'white background', r'plain white', r'seamless white'),
    ('пэкшот', 'K2'): выкинуть(r'no (people|person|model|figure)\w*'),
    ('пэкшот', 'K3'): выкинуть(r'matches? Image \d exactly', r'identical to Image \d',
                               r'exactly as in Image \d', r'PROPOSAL: no existing sample'),
    ('пэкшот', 'K4'): выкинуть(r'no shadow\w*', r'soft even', r'even studio', r'no hard shadow'),
    ('пэкшот', 'W1'): дописать('The wool lies smooth across the front.'),
    ('пэкшот', 'G1'): выкинуть(r'film grain', r'35mm colour film', r'no HDR',
                               r'no digital sharpening'),
    ('пэкшот', 'E4'): выкинуть(r'no collage', r'single photograph only'),
    ('пэкшот', 'E5'): выкинуть(r'no text', r'no logos'),
    # ── ВИДЕО ───────────────────────────────────────────────────────────────
    ('видео', 'A1'): подменить_слот7('oxblood loafers'),
    ('видео', 'V1'): дописать('\n'.join(f'Extra line {i}.' for i in range(1, 4))),
    ('видео', 'V2'): выкинуть(r'keep (face )?identity', r'same person', r'no face warp'),
    ('видео', 'V3'): выкинуть(r'keep (the )?outfit', r'same outfit', r'garment unchanged'),
    ('видео', 'V4'): выкинуть(r'(?m)^lighting:'),
    ('видео', 'V5'): дописать('Camera also orbits the model.'),
    ('видео', 'V6'): дописать('A fast dramatic swing.'),
    ('видео', 'V7'): выкинуть(r'\bslow\w*', r'\bsubtle\b', r'\bgently\b', r'\bsettles\b'),
    ('видео', 'V8'): выкинуть(r'no text', r'no watermark', r'no subtitles'),
}


def main():
    беды = []
    всего = 0
    for класс, набор in НАБОРЫ.items():
        путь = os.path.join(ROOT, ОБРАЗЦЫ[класс])
        if not os.path.exists(путь):
            беды.append(f'{класс}: нет образца {ОБРАЗЦЫ[класс]}')
            continue
        целый = open(путь, encoding='utf-8').read()
        for код, тест, _, _ in набор:
            всего += 1
            ключ = (класс, код)
            if ключ not in ПОЛОМКИ:
                беды.append(f'{класс}/{код}: поломки нет — правило не проверено ни разу')
                continue
            try:
                если_цел = bool(тест(целый))
            except Exception as e:                                # noqa: BLE001
                беды.append(f'{класс}/{код}: падает на целом образце ({e})')
                continue
            if not если_цел:
                беды.append(f'{класс}/{код}: красное на целом образце {ОБРАЗЦЫ[класс]}')
                continue
            сломанный = ПОЛОМКИ[ключ](целый)
            if сломанный == целый:
                беды.append(f'{класс}/{код}: поломка ничего не изменила в тексте')
                continue
            try:
                если_сломан = bool(тест(сломанный))
            except Exception:                                     # noqa: BLE001
                если_сломан = False        # упало с исключением — run() считает это красным
            if если_сломан:
                беды.append(f'{класс}/{код}: НЕ ПАДАЕТ на поломке — правило не умеет краснеть')

    print(f'Правил проверено: {всего} в четырёх классах')
    for b in беды:
        print('  СБОЙ  ' + b)
    if беды:
        print(f'УПАЛО: {len(беды)}')
        return 1
    print('ПРОШЛО — каждое правило зелёное на целом образце и красное на своей поломке')
    return 0


if __name__ == '__main__':
    sys.exit(main())
