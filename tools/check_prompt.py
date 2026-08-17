#!/usr/bin/env python3
"""Самопроверка промпта ДО отправки. Ни одна генерация не запускается без зелёного отчёта.

Зачем. За 13.08.2026 из шестнадцати проходов заказчик принял три. Каждый брак был предсказуем
по тексту промпта: не был описан вырез — вырез стал круглым; не было счётного запрета — появилась
четвёртая пуговица; не было команды удалить резинку с исходника — резинка осталась; поза была
описана статикой — вышел манекен. Проверять надо не картинку, а промпт.

    python3 tools/check_prompt.py prompt.txt
    python3 tools/check_prompt.py prompt.txt --видео
    cat prompt.txt | python3 tools/check_prompt.py -

Код возврата 1, если есть хоть одно нарушение. Правила пронумерованы так же, как в RULES.md.
"""
import re
import sys

# ─────────────────────────────────────────────────────────────────────────────
# ФОТО
BLOCKS = ['REFERENCES', 'PRESERVE', 'HAIR', 'OUTFIT', 'LOCATION', 'GEOGRAPHY',
          'CAMERA', 'SCENE', 'LIGHT', 'GRADE', 'EXCLUDE']

CHECKS_PHOTO = [
    # (код, тест, что не так, правило)
    ('B1', lambda t: all(b in t.upper() for b in BLOCKS),
     'пропущен один из обязательных блоков: ' + ', '.join(BLOCKS), 'TEMPLATE_PHOTO §скелет'),
    ('B2', lambda t: 'HIGHEST PRIORITY' in t.upper(),
     'в блоке PRESERVE нет пометки HIGHEST PRIORITY — модель не отличит его от остального текста',
     'METHOD_REFERENCE_PROMPT §PRESERVE'),
    ('R1', lambda t: len(re.findall(r'\bImage\s+\d', t)) >= 3,
     'меньше трёх пронумерованных референсов: лицо, изделие, низ — минимум',
     'ЗАКОНЫ · картинка сильнее текста'),
    ('R2', lambda t: 'style reference' in t.lower(),
     'нет референса стиля — свет и грейд будут выбраны моделью заново', 'скил reference-shoot · набор'),
    ('R3', lambda t: bool(re.search(r'pixel-identical', t, re.I)),
     'нет строки «pixel-identical to Image 1» — лицо уедет', 'ЗАКОНЫ · картинка сильнее текста'),
    ('C1', lambda t: bool(re.search(r'\bexactly (one|two|three|four|five|six|\d+)\b', t, re.I)),
     'счётный признак не задан числом («exactly three buttons»)', 'ЗАКОНЫ · счётный признак'),
    ('C2', lambda t: bool(re.search(r'no (fourth|fifth|second|third|extra) button|and no \w+th button', t, re.I))
     or 'no additional' in t.lower(),
     'нет запрета «и ни одной больше» — число поплывёт вверх', 'ЗАКОНЫ · счётный признак'),
    ('C3', lambda t: bool(re.search(r'never a (round|crew|v-)|no changed neckline|never a round crew', t, re.I)),
     'не запрещён дефолт горловины («never a round crew neckline»)', 'ЗАКОНЫ · счётный признак'),
    ('E1', lambda t: bool(re.search(r'no (band|rib|ribbed|elastic)', t, re.I)),
     'не запрещены резинка и полоса по краям — они приезжают с исходника', 'ЗАКОНЫ · признак, заданный отсутствием'),
    ('E2', lambda t: bool(re.search(r'single photograph only|no collage|no multiple panels', t, re.I)),
     'нет защиты от коллажа — модель может отдать сетку кадров', 'скил reference-shoot · EXCLUDE'),
    ('E3', lambda t: bool(re.search(r'no static pose|no posed stance|no robotic stiffness', t, re.I)),
     'не запрещены позные дефолты — выйдет манекен', 'ЗАКОНЫ · поза и действие'),
    ('E4', lambda t: t.upper().count('NO ') >= 15,
     'в EXCLUDE меньше пятнадцати запретов: дефолты категории не закрыты', 'скил reference-shoot · EXCLUDE'),
    ('S1', lambda t: bool(re.search(r'mid-action|still settling|has just|halfway|not yet', t, re.I)),
     'поза описана статикой: нет незавершённого действия', 'ЗАКОНЫ · поза и действие'),
    ('S2', lambda t: bool(re.search(r'wind|gust|momentum|inertia|step|pushed off|swing', t, re.I)),
     'в сцене нет внешней силы — ткань и волосы будут мёртвыми', 'ЗАКОНЫ · поза и действие'),
    ('S3', lambda t: bool(re.search(r'one (shoulder|hip|knee|hand).{0,60}(other|than the other)', t, re.I | re.S)),
     'нет асимметрии — тело выйдет симметричным и деревянным', 'ЗАКОНЫ · поза и действие'),
    ('L1', lambda t: bool(re.search(r'light .{0,80}(stay|stays) identical|identical', t, re.I)),
     'не сказано, что свет одинаков при смене ракурса — серия развалится по свету',
     'скил reference-shoot · серия'),
    ('G1', lambda t: bool(re.search(r'film grain|35mm colour film|no HDR', t, re.I)),
     'нет грейда плёнкой — получится цифровая пластмасса', 'hyperreal-photo'),
    # smooth про ПОЛОТНО — запрещено; smooth про пуговицу или веко — нормально,
    # поэтому ищем только рядом со словами ткани
    ('W1', lambda t: not re.search(
        r'(smooth|flat)[^.]{0,40}\b(knit|fabric|cloth|wool|jersey|weave)\b(?!\s+(line|edge))'
        r'|\b(knit|fabric|cloth|wool)\b[^.]{0,40}(lies|lie|sits) (smooth|flat)', t, re.I)
     or bool(re.search(r'keeping the (knit|fabric) texture', t, re.I)),
     'слово smooth/flat про полотно без требования фактуры рядом — резкость падает в 2–3 раза',
     'ЗАКОНЫ · запрет дефекта, не свойства'),
    ('W2', lambda t: not re.search(r'\b(dynamic|energetic|dramatic|beautiful lighting|cinematic light)\b', t, re.I),
     'мусорные слова: dynamic / energetic / beautiful lighting — модель их не исполняет',
     'скил reference-shoot · чего не делать'),
]

# ─────────────────────────────────────────────────────────────────────────────
# ИНТЕРЬЕР — кадр локации без человека и без изделия.
#
# Добавлено 16.08.2026. Правило проекта запрещает игнорировать красную проверку и требует
# менять её в коде, если она неверна. Здесь она была неверна: на пустую комнату check_prompt
# требовал «pixel-identical to Image 1» (лицо), запрет четвёртой пуговицы, запрет резинки на
# манжете и асимметрию плеч — четырёх сущностей, которых в кадре нет по постановке. Правила
# про человека и изделие для этого класса сняты, а вместо них поставлены свои: запрет людей и
# мебели, названный материал стены, сквозной свет и грейд.
CHECKS_INTERIOR = [
    ('B1', lambda t: all(b in t.upper() for b in BLOCKS),
     'пропущен один из обязательных блоков: ' + ', '.join(BLOCKS), 'TEMPLATE_PHOTO §скелет'),
    ('B2', lambda t: 'HIGHEST PRIORITY' in t.upper(),
     'в блоке PRESERVE нет пометки HIGHEST PRIORITY (шапка слабее хвоста SCENE, но пометка нужна)', 'скил reference-shoot · приоритетная строка'),
    ('R1', lambda t: len(re.findall(r'\bImage\s+\d', t)) >= 1,
     'ни одного пронумерованного референса — комната будет выдумана', 'ЗАКОНЫ · картинка сильнее текста'),
    ('R2', lambda t: 'style reference' in t.lower(),
     'нет референса стиля — свет и грейд будут выбраны моделью заново', 'скил reference-shoot · набор'),
    ('I1', lambda t: bool(re.search(r'no (people|person|model|figure)', t, re.I)),
     'нет запрета людей — в пустую комнату приедет человек, это дефолт категории',
     'Закон 2: запрет объектом работает'),
    ('I2', lambda t: bool(re.search(r'no (furniture|chair|table)', t, re.I)),
     'нет запрета мебели — модель обставит комнату', 'Закон 2'),
    ('I3', lambda t: bool(re.search(r'walnut|oak|wood panel|panelling', t, re.I)),
     'материал стены не назван — выйдет крашеная стена', 'ЗАКОНЫ · локация'),
    ('I4', lambda t: bool(re.search(r'no (white wall|painted wall|plaster|wallpaper)', t, re.I)),
     'не запрещён дефолт категории «крашеная стена»', 'Закон 3'),
    ('L1', lambda t: bool(re.search(r'identical', t, re.I)) or bool(re.search(r'on-camera flash', t, re.I)),
     'свет не зафиксирован — интерьер не встанет рядом с кадрами серии', 'ЗАКОНЫ · свет — сквозная константа'),
    ('G1', lambda t: bool(re.search(r'film grain|35mm colour film|no HDR', t, re.I)),
     'нет грейда плёнкой — получится цифровая пластмасса', 'hyperreal-photo'),
    ('E4', lambda t: bool(re.search(r'no collage|single photograph only', t, re.I)),
     'нет запрета коллажа', 'скил reference-shoot · EXCLUDE'),
    ('E5', lambda t: bool(re.search(r'no text|no logos', t, re.I)),
     'нет запрета текста и логотипов', 'скил reference-shoot · EXCLUDE'),
]


# ─────────────────────────────────────────────────────────────────────────────
# ПЭКШОТ — вещь одна на белом фоне, без человека.
#
# Добавлено 16.08.2026 по той же причине, что и класс ИНТЕРЬЕР: правила про лицо, позу и
# асимметрию плеч к предметной съёмке неприменимы, а свои требования у неё есть.
CHECKS_PACKSHOT = [
    ('B1', lambda t: all(b in t.upper() for b in BLOCKS),
     'пропущен один из обязательных блоков: ' + ', '.join(BLOCKS), 'TEMPLATE_PHOTO §скелет'),
    ('B2', lambda t: 'HIGHEST PRIORITY' in t.upper(),
     'в блоке PRESERVE нет пометки HIGHEST PRIORITY (шапка слабее хвоста SCENE, но пометка нужна)', 'скил reference-shoot · приоритетная строка'),
    ('R1', lambda t: len(re.findall(r'\bImage\s+\d', t)) >= 1,
     'нет пронумерованного референса вещи — модель нарисует свою', 'ЗАКОНЫ · картинка сильнее текста'),
    ('R2', lambda t: 'style reference' in t.lower(),
     'нет референса стиля', 'скил reference-shoot · набор'),
    ('P1', lambda t: bool(re.search(r'white background|plain white|seamless white', t, re.I)),
     'не задан белый фон — пэкшот приедет в интерьере', 'ЗАКОНЫ · пэкшот'),
    ('P2', lambda t: bool(re.search(r'no (people|person|model|figure)', t, re.I)),
     'нет запрета человека — в пэкшот приедет модель', 'Закон 2'),
    # Пэкшот бывает двух видов. Съёмка существующей вещи обязана быть привязана к её картинке.
    # Предложение новой вещи привязывать не к чему — там роль якоря играет числовая
    # спецификация: высота каблука в сантиметрах, число ремешков, форма мыска словом-запретом.
    # Введено 16.08.2026, когда понадобилось предложить заказчику три варианта обуви.
    ('P3', lambda t: bool(re.search(r'matches? Image \d exactly|identical to Image \d|exactly as in Image \d', t, re.I))
     or (bool(re.search(r'PROPOSAL: no existing sample', t))
         and bool(re.search(r'\d+(\.\d+)?\s?(cm|centimetre|centimeter)', t, re.I))),
     'вещь ни к чему не привязана: нужна либо строка «matches Image N exactly», либо пометка '
     '«PROPOSAL: no existing sample» вместе с числовой спецификацией в сантиметрах', 'Закон 0'),
    ('P4', lambda t: bool(re.search(r'no shadow|soft even|even studio|no hard shadow', t, re.I)),
     'не задан ровный студийный свет — пэкшот получит сцену вместо света', 'ЗАКОНЫ · пэкшот'),
    ('W1', lambda t: not re.search(
        r'(smooth|flat)[^.]{0,40}\b(knit|fabric|cloth|wool|jersey|weave)\b(?!\s+(line|edge))', t, re.I)
     or bool(re.search(r'keeping the (knit|fabric) texture', t, re.I)),
     'smooth/flat про полотно без требования фактуры рядом', 'ЗАКОНЫ · запрет дефекта, не свойства'),
    ('G1', lambda t: bool(re.search(r'film grain|35mm colour film|no HDR|no digital sharpening', t, re.I)),
     'нет грейда — получится цифровая пластмасса', 'hyperreal-photo'),
    ('E4', lambda t: bool(re.search(r'no collage|single photograph only', t, re.I)),
     'нет запрета коллажа', 'скил reference-shoot · EXCLUDE'),
    ('E5', lambda t: bool(re.search(r'no text|no logos', t, re.I)),
     'нет запрета текста и логотипов', 'скил reference-shoot · EXCLUDE'),
]


# ─────────────────────────────────────────────────────────────────────────────
# ВИДЕО
CHECKS_VIDEO = [
    ('V1', lambda t: len([l for l in t.strip().splitlines() if l.strip()]) <= 8,
     'больше восьми строк: для i2v «2–6 коротких строк бьют длинный абзац»', 'VIDEO_REVISION 3.1'),
    ('V2', lambda t: bool(re.search(r'keep (face )?identity|same person|no face warp', t, re.I)),
     'нет строки-якоря идентичности — лицо поплывёт в движении', 'VIDEO_REVISION 3.1'),
    ('V3', lambda t: bool(re.search(r'keep (the )?outfit|same outfit|garment unchanged', t, re.I)),
     'нет якоря одежды — изделие морфнёт', 'VIDEO_REVISION 4'),
    ('V4', lambda t: bool(re.search(r'^lighting:', t, re.I | re.M)),
     'нет фиксированной строки света «Lighting: …» — будет мерцание между кадрами',
     'VIDEO_REVISION 3.1'),
    ('V5', lambda t: len(re.findall(r'\b(dolly|orbit|pan|tilt|push|zoom|crane|truck)\b', t, re.I)) <= 1,
     'больше одного движения камеры в клипе', 'ai-video-shots'),
    # в негативе эти слова законны: «no fast motion». Ловим только требование, а не запрет.
    ('V6', lambda t: not re.search(r'(?<!no )(?<!not )\b(fast|dramatic|dynamic|energetic)\b', t, re.I),
     'быстрые слова: fast / dramatic / dynamic — дают дёрганое движение', 'VIDEO_REVISION 3.4'),
    ('V7', lambda t: bool(re.search(r'\bslow|subtle|gently|settles\b', t, re.I)),
     'нет медленных слов: slow / subtle / gently / settles', 'VIDEO_REVISION 3.4'),
    ('V8', lambda t: bool(re.search(r'no text|no watermark|no subtitles', t, re.I)),
     'нет запрета текста и водяных знаков', 'скил ai-video-shots'),
]


def run(text, video=False, interior=False, packshot=False):
    checks = (CHECKS_VIDEO if video else CHECKS_INTERIOR if interior
              else CHECKS_PACKSHOT if packshot else CHECKS_PHOTO)
    bad = []
    for code, test, msg, rule in checks:
        try:
            ok = bool(test(text))
        except Exception as e:                                   # noqa: BLE001
            ok, msg = False, f'{msg} (проверка упала: {e})'
        if not ok:
            bad.append((code, msg, rule))
    return bad


VERSION = 'check_prompt 2026-08-14 · КОНТРОЛЬНАЯ СТРОКА: ГОРОШЕК-19-ПРАВИЛ'


def main():
    if '--версия' in sys.argv:
        print(f'\n{VERSION}')
        print(f'правил фото: {len(CHECKS_PHOTO)}, правил видео: {len(CHECKS_VIDEO)}')
        print('коды фото: ' + ', '.join(c[0] for c in CHECKS_PHOTO))
        print('коды видео: ' + ', '.join(c[0] for c in CHECKS_VIDEO))
        print(f'правил интерьера: {len(CHECKS_INTERIOR)}')
        print('коды интерьера: ' + ', '.join(c[0] for c in CHECKS_INTERIOR) + '\n')
        return 0
    args = [a for a in sys.argv[1:] if a not in ('--видео', '--интерьер', '--пэкшот')]
    video = '--видео' in sys.argv
    interior = '--интерьер' in sys.argv
    packshot = '--пэкшот' in sys.argv
    text = sys.stdin.read() if (not args or args[0] == '-') else open(args[0], encoding='utf-8').read()

    bad = run(text, video, interior, packshot)
    kind = 'ВИДЕО' if video else ('ИНТЕРЬЕР' if interior else ('ПЭКШОТ' if packshot else 'ФОТО'))
    total = len(CHECKS_VIDEO if video else (CHECKS_INTERIOR if interior else (CHECKS_PACKSHOT if packshot else CHECKS_PHOTO)))
    print(f"\nПроверка промпта ({kind}): {total - len(bad)} из {total} правил соблюдено")
    if not bad:
        print('Нарушений нет. Промпт можно отправлять.\n')
        return 0
    print('\nНАРУШЕНИЯ — генерация запрещена до исправления:\n')
    for code, msg, rule in bad:
        print(f"  [{code}] {msg}")
        print(f"        правило: {rule}")
    print()
    return 1


if __name__ == '__main__':
    sys.exit(main())
