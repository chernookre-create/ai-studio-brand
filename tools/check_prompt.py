#!/usr/bin/env python3
"""Самопроверка промпта ДО отправки. Ни одна генерация не запускается без зелёного отчёта.

Зачем. За 13.08.2026 из шестнадцати проходов заказчик принял три. Каждый брак был предсказуем
по тексту промпта: не был описан вырез — вырез стал круглым; не было счётного запрета — появилась
четвёртая пуговица; не было команды удалить резинку с исходника — резинка осталась; поза была
описана статикой — вышел манекен. Проверять надо не картинку, а промпт.

    python3 tools/check_prompt.py prompt.txt
    python3 tools/check_prompt.py prompt.txt --видео
    cat prompt.txt | python3 tools/check_prompt.py -

Код возврата 1, если есть хоть одно нарушение.

Коды правил здесь **свои** (B, R, C, E, S, L, G, W, P) и с кодами законов не совпадают: `E1` в
этом файле — про резинку по краям, а `E1` в «ЗАКОНАХ» — про комнату, крутящуюся словами. Не
путать. В колонке «правило» указан источник, откуда взято требование.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─────────────────────────────────────────────────────────────────────────────
# ФОТО
BLOCKS = ['REFERENCES', 'PRESERVE', 'HAIR', 'OUTFIT', 'LOCATION', 'GEOGRAPHY',
          'CAMERA', 'SCENE', 'LIGHT', 'GRADE', 'EXCLUDE']

# Заголовки, которых в нынешних одиннадцати блоках нет, но которые стоят в текстах 13.08:
# тогда блок назывался `STREET GEOGRAPHY`. Резать хвост SCENE по ним всё равно нужно, иначе
# в разборе старого текста «последней фразой SCENE» окажется строка из следующего блока.
БЫВШИЕ_БЛОКИ = ['STREET GEOGRAPHY']


def scene_tails(text, сколько=1):
    """Последние фразы блока SCENE — приоритетная позиция промпта (законы B1 и B3).

    **Единственная реализация в комплекте.** До 18.08 их было две: своя в `check_prompt`
    (по ней судит правило `P1`) и своя в `registry.py` (по ней пишется колонка реестра
    «последняя фраза SCENE»). На двух текстах из 77 они давали разные ответы: реестр не
    дорезал блок и показывал строку из следующего. Про главный закон проекта два разных
    ответа — это два разных закона (Ф153).
    """
    up = text.upper()
    if 'SCENE' not in up:
        return [''] * сколько
    body = text[up.index('SCENE') + 5:]
    for b in BLOCKS + БЫВШИЕ_БЛОКИ:
        i = body.upper().find('\n' + b)
        if i > 0:
            body = body[:i]
    sents = [x.strip() for x in re.split(r'(?<=[.!?])\s+', body) if x.strip()]
    вышло = list(reversed(sents[-сколько:])) if sents else []
    return вышло + [''] * (сколько - len(вышло))


def scene_tail(text):
    """Последняя фраза блока SCENE."""
    return scene_tails(text, 1)[0]


# Признаки, ради которых приоритетная позиция вообще существует: то, что ломается на кадре.
# Границы слова обязательны: без них `flat` ловился внутри `flattering`, и фраза настроения
# проходила как приоритетная строка (Ф131). Причёски здесь нет намеренно — по B1 она стоит
# ПРЕДпоследней, а последняя строка отдаётся признаку изделия или кадра (правило P3).
ЛОМКОЕ = (r'\b(buttons?|placket|hems?|cuffs?|edges?|shoes?|flats?|wall|planks?|panelling|'
          r'knit|dots?|neckline|crop|waistband|sleeves?|fastening|length)\b')
# Приоритетная строка — это ограничение признака, а не упоминание о нём: «no fourth button»,
# «never a round crew», «the dots run right to the edge». Фраза настроения признак называет,
# но ничего не запрещает и ничего не удерживает.
ОГРАНИЧЕНИЕ = r'\b(no|never|only|exactly|not|nothing|none)\b'
# Причёска в хвосте — частая ошибка: по B1 её место предпоследнее.
ПРИЧЁСКА = r'\b(hair|hairs|knot|bun|parting|fringe|ponytail)\b'
# Дефекты постобработки: лечатся скриптом после кадра, в хвосте им не место (закон B3).
ПОСТОБРАБОТКА = r'border|watermark|subtitle|resolution|aspect ratio|letterbox|whole file|file edge'

def _плоское_полотно(text):
    """«Полотно лежит гладко» без требования фактуры рядом — обрушивает резкость вязки (A6).

    Оговорка `keeping the knit texture …` действует только внутри СВОЕГО предложения.
    Прежняя редакция искала её по всему тексту: строка из блока GRADE разрешала любое
    «the knit lies smooth» в любом другом блоке, и правило не могло покраснеть (Ф150).
    """
    ПЛОХО = (r'(smooth|flat)[^.]{0,40}\b(knit|fabric|cloth|wool|jersey|weave)\b(?!\s+(line|edge))'
             r'|\b(knit|fabric|cloth|wool|jersey|weave)\b[^.]{0,40}(lies|lie|sits|sit) (smooth|flat)')
    ЛЕКАРСТВО = r'keep(ing|s)? the (knit|fabric|wool|weave) texture'
    for пред in re.split(r'(?<=[.!?])\s+', text):
        if re.search(ПЛОХО, пред, re.I) and not re.search(ЛЕКАРСТВО, пред, re.I):
            return True
    return False


CHECKS_PHOTO = [
    # (код, тест, что не так, правило)
    ('B1', lambda t: all(b in t.upper() for b in BLOCKS),
     'пропущен один из обязательных блоков: ' + ', '.join(BLOCKS), 'скил reference-shoot · одиннадцать блоков'),
    ('B2', lambda t: 'HIGHEST PRIORITY' in t.upper(),
     'в блоке PRESERVE нет пометки HIGHEST PRIORITY — модель не отличит его от остального текста',
     'документ «Метод референсного промпта» · PRESERVE'),
    ('R1', lambda t: len(re.findall(r'\bImage\s+\d', t)) >= 3,
     'меньше трёх пронумерованных референсов: лицо, изделие, низ — минимум',
     'закон A1 · картинка сильнее текста'),
    ('R2', lambda t: 'style reference' in t.lower(),
     'нет референса стиля — свет и грейд будут выбраны моделью заново', 'скил reference-shoot · набор'),
    ('R3', lambda t: bool(re.search(r'pixel-identical', t, re.I)),
     'нет строки «pixel-identical to Image 1» — лицо уедет', 'закон A1 · картинка сильнее текста'),
    ('C1', lambda t: bool(re.search(r'\bexactly (one|two|three|four|five|six|\d+)\b', t, re.I)),
     'счётный признак не задан числом («exactly three buttons»)', 'закон A3 · картинка + число + запрет'),
    ('C2', lambda t: bool(re.search(r'no (fourth|fifth|second|third|extra) button|and no \w+th button', t, re.I))
     or 'no additional' in t.lower(),
     'нет запрета «и ни одной больше» — число поплывёт вверх', 'закон A3 · картинка + число + запрет'),
    ('C3', lambda t: bool(re.search(r'never a (round|crew|v-)|no changed neckline|never a round crew', t, re.I)),
     'не запрещён дефолт горловины («never a round crew neckline»)', 'закон A3 · картинка + число + запрет'),
    ('E1', lambda t: bool(re.search(r'no (band|rib|ribbed|elastic)', t, re.I)),
     'не запрещены резинка и полоса по краям — они приезжают с исходника', 'закон A2 · признак, заданный отсутствием'),
    ('E2', lambda t: bool(re.search(r'single photograph only|no collage|no multiple panels', t, re.I)),
     'нет защиты от коллажа — модель может отдать сетку кадров', 'скил reference-shoot · EXCLUDE'),
    # E3 снято 18.08 (Ф119). Оно требовало `no static pose | no posed stance |
    # no robotic stiffness` — то есть запрет СВОЙСТВА, а по закону A6 и по разделу «чего не
    # делать» в скиле такие запреты не исполняются: ни одна из трёх формулировок не удержала
    # позу ни разу за пять наборов. Красная проверка заставляла вписывать мёртвый текст в
    # каждый промпт. Живая поза держится правилами S1, S2, S3 ниже — незавершённое действие,
    # внешняя сила, асимметрия, — и они остаются обязательными.
    ('E4', lambda t: t.upper().count('NO ') >= 15,
     'в EXCLUDE меньше пятнадцати запретов: дефолты категории не закрыты', 'скил reference-shoot · EXCLUDE'),
    ('S1', lambda t: bool(re.search(r'mid-action|still settling|has just|halfway|not yet', t, re.I)),
     'поза описана статикой: нет незавершённого действия', 'закон A7 · поза требованием, а не запретом'),
    # `wind` без границ слова находился внутри `no window light` — строки, которая стоит в
    # блоке LIGHT каждого нашего промпта. Правило было зелёным всегда и упасть не могло (Ф149).
    ('S2', lambda t: bool(re.search(
        r'\b(wind|winds|gust\w*|momentum|inertia|steps?|stepping|pushed off|swing\w*)\b', t, re.I)),
     'в сцене нет внешней силы — ткань и волосы будут мёртвыми', 'закон A7 · поза требованием, а не запретом'),
    ('S3', lambda t: bool(re.search(r'one (shoulder|hip|knee|hand).{0,60}(other|than the other)', t, re.I | re.S)),
     'нет асимметрии — тело выйдет симметричным и деревянным', 'закон A7 · поза требованием, а не запретом'),
    # Второе плечо прежней альтернации было одно слово `identical`, а правило R3 обязывает
    # писать `pixel-identical` про лицо — совпадение находилось всегда, и правило не могло
    # упасть ни на одном промпте (Ф120). Теперь ищем именно постоянство света.
    ('L1', lambda t: bool(re.search(
        r'\b(light|lighting|weather)\b[^.]{0,120}\b(identical|unchanged|does not change|'
        r'stays? the same|remains? the same|constant)\b'
        r'|\b(identical|unchanged|constant|the same)\b[^.]{0,120}\b(light|lighting|weather)\b', t, re.I)),
     'не сказано, что свет и погода одинаковы при смене ракурса — серия развалится по свету',
     'скил reference-shoot · серия'),
    ('P1', lambda t: bool(re.search(ЛОМКОЕ, scene_tail(t), re.I))
     and bool(re.search(ОГРАНИЧЕНИЕ, scene_tail(t), re.I)),
     'последняя фраза SCENE не удерживает ломкий признак: нужен и сам признак, и ограничение '
     '(«no fourth button», «never a round crew», «the dots run to the very edge»)',
     'закон B1 · приоритетная строка'),
    ('P2', lambda t: not re.search(ПОСТОБРАБОТКА, scene_tail(t), re.I),
     'в последней фразе SCENE стоит дефект постобработки (кайма, водяной знак, разрешение) — '
     'движок его не исполняет, это работа trim_border.py',
     'закон B3 · в хвост только исполнимое'),
    ('P3', lambda t: not re.search(ПРИЧЁСКА, scene_tail(t), re.I),
     'причёска стоит последней строкой SCENE — по B1 её место предпоследнее, последняя отдаётся '
     'признаку изделия или кадра',
     'закон B1 · порядок хвоста'),
    ('G1', lambda t: bool(re.search(r'film grain|35mm colour film|no HDR', t, re.I)),
     'нет грейда плёнкой — получится цифровая пластмасса', 'скил reference-shoot · GRADE'),
    # smooth про ПОЛОТНО — запрещено; smooth про пуговицу или веко — нормально,
    # поэтому ищем только рядом со словами ткани
    ('W1', lambda t: not _плоское_полотно(t),
     'слово smooth/flat про полотно без требования фактуры рядом — резкость падает в 2–3 раза',
     'закон A6 · запрет дефекта плюс требование'),
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
     'пропущен один из обязательных блоков: ' + ', '.join(BLOCKS), 'скил reference-shoot · одиннадцать блоков'),
    ('B2', lambda t: 'HIGHEST PRIORITY' in t.upper(),
     'в блоке PRESERVE нет пометки HIGHEST PRIORITY (шапка слабее хвоста SCENE, но пометка нужна)', 'скил reference-shoot · приоритетная строка'),
    ('R1', lambda t: len(re.findall(r'\bImage\s+\d', t)) >= 1,
     'ни одного пронумерованного референса — комната будет выдумана', 'закон A1 · картинка сильнее текста'),
    ('R2', lambda t: 'style reference' in t.lower(),
     'нет референса стиля — свет и грейд будут выбраны моделью заново', 'скил reference-shoot · набор'),
    ('I1', lambda t: bool(re.search(r'no (people|person|model|figure)', t, re.I)),
     'нет запрета людей — в пустую комнату приедет человек, это дефолт категории',
     'закон A2 · дефолт категории'),
    ('I2', lambda t: bool(re.search(r'no (furniture|chair|table)', t, re.I)),
     'нет запрета мебели — модель обставит комнату', 'закон A2 · дефолт категории'),
    ('I3', lambda t: bool(re.search(r'walnut|oak|wood panel|panelling', t, re.I)),
     'материал стены не назван — выйдет крашеная стена', 'закон E2 · деталь интерьера достраивается дефолтом'),
    ('I4', lambda t: bool(re.search(r'no (white wall|painted wall|plaster|wallpaper)', t, re.I)),
     'не запрещён дефолт категории «крашеная стена»', 'закон A2 · дефолт категории'),
    # Тот же дефект, что в фото-L1 (Ф120), только в интерьерном списке — и он там дожил
    # на сутки дольше: одинокое слово `identical` находится в любом промпте, где есть
    # `pixel-identical` про лицо. Ищем постоянство именно СВЕТА.
    ('L1', lambda t: bool(re.search(
        r'\b(light|lighting|flash)\b[^.]{0,120}\b(identical|unchanged|constant|'
        r'stays? the same|remains? the same)\b'
        r'|\b(identical|unchanged|constant|the same)\b[^.]{0,120}\b(light|lighting|flash)\b'
        r'|on-camera flash', t, re.I)),
     'свет не зафиксирован — интерьер не встанет рядом с кадрами серии', 'без закона · практика: свет серии фиксируется'),
    ('G1', lambda t: bool(re.search(r'film grain|35mm colour film|no HDR', t, re.I)),
     'нет грейда плёнкой — получится цифровая пластмасса', 'скил reference-shoot · GRADE'),
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
     'пропущен один из обязательных блоков: ' + ', '.join(BLOCKS), 'скил reference-shoot · одиннадцать блоков'),
    ('B2', lambda t: 'HIGHEST PRIORITY' in t.upper(),
     'в блоке PRESERVE нет пометки HIGHEST PRIORITY (шапка слабее хвоста SCENE, но пометка нужна)', 'скил reference-shoot · приоритетная строка'),
    ('R1', lambda t: len(re.findall(r'\bImage\s+\d', t)) >= 1,
     'нет пронумерованного референса вещи — модель нарисует свою', 'закон A1 · картинка сильнее текста'),
    ('R2', lambda t: 'style reference' in t.lower(),
     'нет референса стиля', 'скил reference-shoot · набор'),
    ('K1', lambda t: bool(re.search(r'white background|plain white|seamless white', t, re.I)),
     'не задан белый фон — пэкшот приедет в интерьере', 'без закона · практика пэкшота'),
    ('K2', lambda t: bool(re.search(r'no (people|person|model|figure)', t, re.I)),
     'нет запрета человека — в пэкшот приедет модель', 'закон A2 · дефолт категории'),
    # Пэкшот бывает двух видов. Съёмка существующей вещи обязана быть привязана к её картинке.
    # Предложение новой вещи привязывать не к чему — там роль якоря играет числовая
    # спецификация: высота каблука в сантиметрах, число ремешков, форма мыска словом-запретом.
    # Введено 16.08.2026, когда понадобилось предложить заказчику три варианта обуви.
    ('K3', lambda t: bool(re.search(r'matches? Image \d exactly|identical to Image \d|exactly as in Image \d', t, re.I))
     or (bool(re.search(r'PROPOSAL: no existing sample', t))
         and bool(re.search(r'\d+(\.\d+)?\s?(cm|centimetre|centimeter)', t, re.I))),
     'вещь ни к чему не привязана: нужна либо строка «matches Image N exactly», либо пометка '
     '«PROPOSAL: no existing sample» вместе с числовой спецификацией в сантиметрах', 'закон A1 · картинка сильнее текста'),
    ('K4', lambda t: bool(re.search(r'no shadow|soft even|even studio|no hard shadow', t, re.I)),
     'не задан ровный студийный свет — пэкшот получит сцену вместо света', 'без закона · практика пэкшота'),
    ('W1', lambda t: not _плоское_полотно(t),
     'smooth/flat про полотно без требования фактуры рядом', 'закон A6 · запрет дефекта плюс требование'),
    ('G1', lambda t: bool(re.search(r'film grain|35mm colour film|no HDR|no digital sharpening', t, re.I)),
     'нет грейда — получится цифровая пластмасса', 'скил reference-shoot · GRADE'),
    ('E4', lambda t: bool(re.search(r'no collage|single photograph only', t, re.I)),
     'нет запрета коллажа', 'скил reference-shoot · EXCLUDE'),
    ('E5', lambda t: bool(re.search(r'no text|no logos', t, re.I)),
     'нет запрета текста и логотипов', 'скил reference-shoot · EXCLUDE'),
]


# ─────────────────────────────────────────────────────────────────────────────
# ВИДЕО
CHECKS_VIDEO = [
    ('V1', lambda t: len([l for l in t.strip().splitlines() if l.strip()]) <= 8,
     'больше восьми строк: для i2v «2–6 коротких строк бьют длинный абзац»', 'документ «Видео в Higgsfield» §3'),
    ('V2', lambda t: bool(re.search(r'keep (face )?identity|same person|no face warp', t, re.I)),
     'нет строки-якоря идентичности — лицо поплывёт в движении', 'документ «Видео в Higgsfield» §3'),
    ('V3', lambda t: bool(re.search(r'keep (the )?outfit|same outfit|garment unchanged', t, re.I)),
     'нет якоря одежды — изделие морфнёт', 'документ «Видео в Higgsfield» §4'),
    ('V4', lambda t: bool(re.search(r'^lighting:', t, re.I | re.M)),
     'нет фиксированной строки света «Lighting: …» — будет мерцание между кадрами',
     'документ «Видео в Higgsfield» §3'),
    ('V5', lambda t: len(re.findall(
        r'\b(dolly|dollies|orbits?|pans?|tilts?|push(?:es|ing)?|zooms?|cranes?|trucks?)\b',
        t, re.I)) <= 1,
     'больше одного движения камеры в клипе', 'ai-video-shots'),
    # в негативе эти слова законны: «no fast motion». Ловим только требование, а не запрет.
    ('V6', lambda t: not re.search(r'(?<!no )(?<!not )\b(fast|dramatic|dynamic|energetic)\b', t, re.I),
     'быстрые слова: fast / dramatic / dynamic — дают дёрганое движение', 'документ «Видео в Higgsfield» §3.4'),
    ('V7', lambda t: bool(re.search(r'\bslow|subtle|gently|settles\b', t, re.I)),
     'нет медленных слов: slow / subtle / gently / settles', 'документ «Видео в Higgsfield» §3.4'),
    ('V8', lambda t: bool(re.search(r'no text|no watermark|no subtitles', t, re.I)),
     'нет запрета текста и водяных знаков', 'скил ai-video-shots'),
]


def чужие_слова(text):
    """Слова прежнего предмета в строках «Image N:» — расхождение картинки и текста (A1).

    Механизм заведён 18.08 после двух случаев подряд. Пуговицу описывали как гладкий купол в
    широком кольце, когда в слоте 3 лежал гранёный купол в узком витом ободке, — и из этого
    вырос ложный закон C6 «рисунок пуговицы не лечится» (Ф144). Обувь в слоте 7 сменилась с
    бордовых лоферов на кремовые балетки, промпты кардигана поправили, а девять интерьерных и
    предметных так и звали слот 7 «the oxblood loafers» (Ф156).

    Список слов лежит в `refs/CURRENT.json`, поле `не_путать`, — то есть в данных съёмки, а не
    в коде: новая съёмка меняет его вместе со слотами. Смотрим только строки `Image N:`: они
    описывают набор. В PRESERVE слово может быть законным — предложение новой обуви в бордовой
    коже описывает не слот, а то, чего ещё нет.
    """
    import json as _j
    путь = os.path.join(ROOT, 'refs', 'CURRENT.json')
    if not os.path.exists(путь):
        return []
    try:
        карта = (_j.load(open(путь, encoding='utf-8')).get('не_путать') or {})
    except Exception:                                            # noqa: BLE001
        return []
    ссылки = [l for l in text.splitlines() if re.match(r'\s*Image\s+\d', l)]
    беды = []
    for слот, слова in карта.items():
        for w in слова:
            for l in ссылки:
                if re.search(r'\b' + re.escape(w) + r'\b', l, re.I):
                    беды.append(f'слот {слот}: «{w}»')
                    break
    return беды


def run(text, video=False, interior=False, packshot=False):
    checks = (CHECKS_VIDEO if video else CHECKS_INTERIOR if interior
              else CHECKS_PACKSHOT if packshot else CHECKS_PHOTO)
    bad = []
    # Правило A1 общее для всех четырёх классов: описание слота словами прежнего предмета —
    # брак источников, и никакая другая проверка его не ловит.
    чужое = чужие_слова(text)
    if чужое:
        bad.append(('A1', 'в строках «Image N:» стоят слова предмета, которого в наборе нет: '
                    + '; '.join(чужое), 'закон A1 · картинка сильнее текста'))
    for code, test, msg, rule in checks:
        try:
            ok = bool(test(text))
        except Exception as e:                                   # noqa: BLE001
            ok, msg = False, f'{msg} (проверка упала: {e})'
        if not ok:
            bad.append((code, msg, rule))
    return bad


VERSION = 'check_prompt 2026-08-18 · четыре класса кадра плюс общее правило A1, коды правил свои'


def main():
    if '--версия' in sys.argv:
        print(f'\n{VERSION}')
        print('общее правило всех классов: A1 — в строках «Image N:» нет слов предмета, '
              'которого в наборе нет (список в refs/CURRENT.json, поле не_путать)')
        print(f'правил фото: {len(CHECKS_PHOTO)} + A1, правил видео: {len(CHECKS_VIDEO)} + A1')
        print('коды фото: ' + ', '.join(c[0] for c in CHECKS_PHOTO))
        print('коды видео: ' + ', '.join(c[0] for c in CHECKS_VIDEO))
        print(f'правил интерьера: {len(CHECKS_INTERIOR)}')
        print('коды интерьера: ' + ', '.join(c[0] for c in CHECKS_INTERIOR))
        print(f'правил пэкшота: {len(CHECKS_PACKSHOT)}')
        print('коды пэкшота: ' + ', '.join(c[0] for c in CHECKS_PACKSHOT) + '\n')
        return 0
    args = [a for a in sys.argv[1:] if a not in ('--видео', '--интерьер', '--пэкшот')]
    video = '--видео' in sys.argv
    interior = '--интерьер' in sys.argv
    packshot = '--пэкшот' in sys.argv
    text = sys.stdin.read() if (not args or args[0] == '-') else open(args[0], encoding='utf-8').read()

    bad = run(text, video, interior, packshot)
    kind = 'ВИДЕО' if video else ('ИНТЕРЬЕР' if interior else ('ПЭКШОТ' if packshot else 'ФОТО'))
    # +1 — общее правило A1 (чужие слова в строках «Image N:»), оно не лежит ни в одном
    # из четырёх списков, но считается наравне: иначе отчёт печатал «12 из 12» при 13 правилах.
    total = 1 + len(CHECKS_VIDEO if video else (CHECKS_INTERIOR if interior else (CHECKS_PACKSHOT if packshot else CHECKS_PHOTO)))
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
