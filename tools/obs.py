#!/usr/bin/env python3
"""Наблюдаемость проекта: одно событие — одна строка, один сквозной код на операцию.

Зачем. Проект живёт сессиями в эфемерном контейнере, а работа тянется через несколько
сессий и несколько чатов. К 19.08 накопилось три беды, которых не видно изнутри одной
сессии: непонятно, на каком этапе всё встало; непонятно, какая ошибка была первой, а какая
её следствием; и — самое дорогое — работа ходит по кругу, одна и та же правка вносится
повторно, а заметно это только человеку и только задним числом.

Что это НЕ. Здесь нет очередей, воркеров, вебхуков и HTTP: в проекте их нет, и метрики без
поля в данных не заводятся (закон F7). Экспортёр наружу выключен и останется выключенным,
пока не появятся credentials — их в чат не запрашивают.

Три режима: DIAGNOSTIC, NORMAL, MINIMAL. **CORE AUDIT пишется во всех трёх** и не выключается
ничем: запуск и конец операции, переходы состояний, внешние действия, счётчики записей,
первая значимая ошибка, дубли, подозрение на цикл, решения человека, терминальный результат.

    from obs import операция, событие, ЭТАПЫ
    with операция('кадр', код='E02_01', ключ='съёмка кадра') as оп:
        оп.этап('Validation'); ...
        оп.записал('results/v7.json', 1)
        оп.готово('принят')

Журнал: 00_obs/events.jsonl рабочей директории. В репозиторий не едет — он публичный, а
события содержат имена файлов и коды кадров. Долговременное хранение — перенос сводки на мак.
"""
import hashlib
import json
import os
import re
import sys
import time
import uuid

SCHEMA = 1
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ОБЛАСТЬ = os.path.join(ROOT, '00_obs')
ЖУРНАЛ = os.path.join(ОБЛАСТЬ, 'events.jsonl')
СОСТОЯНИЕ = os.path.join(ОБЛАСТЬ, 'state.json')

# Этапы конвейера — те, что реально существуют в этом проекте.
ЭТАПЫ = ['Trigger', 'Validation', 'Processing', 'External', 'Writes', 'Verification', 'Result']

РЕЖИМЫ = ('DIAGNOSTIC', 'NORMAL', 'MINIMAL')
РАЗМЕР_ФАЙЛА = 5 * 1024 * 1024        # больше — ротация
ХРАНИТЬ_ФАЙЛОВ = 5
СРОК = {'DIAGNOSTIC': 14, 'NORMAL': 90, 'MINIMAL': 90}   # дней

# ─────────────────────────────────────────────────────────────────────────────
# Санитайзер. Репозиторий публичный, а на маке в путях стоит имя пользователя, в окружении
# живут токены GitHub и Яндекса. Ни одно из этого в журнал попасть не может — ни целиком,
# ни куском. Правило простое: не «замазать найденное», а вырезать по форме.

ЗАПРЕТ = [
    # (имя, регулярка, чем заменить)
    ('токен', r'\b(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,})\b', '<токен-github>'),
    ('токен', r'\b(y0_[A-Za-z0-9_\-]{20,}|OAuth\s+[A-Za-z0-9_\-\.]{20,})\b', '<токен-яндекс>'),
    ('ключ', r'-----BEGIN[^-]{0,40}PRIVATE KEY-----', '<приватный-ключ>'),
    ('ключ', r'\b(sk|pk|rk)-[A-Za-z0-9]{20,}\b', '<api-key>'),
    ('заголовок', r'(?i)\b(authorization|x-api-key|cookie|set-cookie)\b\s*[:=]\s*\S+',
     '<заголовок-вырезан>'),
    ('пароль', r'(?i)\b(pass(word)?|secret|token|api[_-]?key|credential)s?\b\s*[:=]\s*\S+',
     '<секрет-вырезан>'),
    ('строка-бд', r'\b\w+://[^\s/@]+:[^\s/@]+@\S+', '<строка-подключения>'),
    ('почта', r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '<почта>'),
    ('домашний путь', r'/(?:Users|home)/[^/\s\'"]+', '~'),
    ('путь сессии', r'/sessions/[A-Za-z0-9\-]+', '<сессия>'),
]
ПРЕДЕЛ_СТРОКИ = 400          # длиннее — обрезаем: полный prompt и полный ответ модели не храним


def очистить(значение, _глубина=0):
    """Вырезать запрещённое и обрезать длинное. Работает по форме, а не по списку известных."""
    if _глубина > 6:
        return '<слишком глубоко>'
    if isinstance(значение, dict):
        out = {}
        for k, v in значение.items():
            kl = str(k).lower()
            if any(w in kl for w in ('password', 'secret', 'token', 'apikey', 'api_key',
                                     'cookie', 'authorization', 'credential', 'prompt_text',
                                     'body', 'payload', 'stderr')):
                out[str(k)] = '<вырезано по имени поля>'
            else:
                out[str(k)] = очистить(v, _глубина + 1)
        return out
    if isinstance(значение, (list, tuple)):
        return [очистить(v, _глубина + 1) for v in значение][:50]
    if isinstance(значение, (int, float, bool)) or значение is None:
        return значение
    s = str(значение)
    for _, шаблон, чем in ЗАПРЕТ:
        s = re.sub(шаблон, чем, s)
    if len(s) > ПРЕДЕЛ_СТРОКИ:
        s = s[:ПРЕДЕЛ_СТРОКИ] + f'…<обрезано, всего {len(s)} знаков>'
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Состояние: режим, срок диагностики, экспортёр, счётчик последовательности.

ПО_УМОЛЧАНИЮ = {
    'режим': 'NORMAL',
    'debugUntil': None,
    'remoteExportEnabled': False,
    'sequence': 0,
    'stateRevision': 0,
    'последнее_событие': None,
}


def _прочитать_состояние():
    try:
        d = json.load(open(СОСТОЯНИЕ, encoding='utf-8'))
        return {**ПО_УМОЛЧАНИЮ, **d}
    except Exception:                                            # noqa: BLE001
        return dict(ПО_УМОЛЧАНИЮ)


def _записать_состояние(d):
    os.makedirs(ОБЛАСТЬ, exist_ok=True)
    врем = СОСТОЯНИЕ + '.tmp'
    with open(врем, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(врем, СОСТОЯНИЕ)          # атомарно: частично записанного файла не бывает


def режим():
    """Текущий режим с учётом debugUntil: срок вышел — сам возвращается в NORMAL."""
    st = _прочитать_состояние()
    if st['режим'] == 'DIAGNOSTIC' and st.get('debugUntil'):
        if time.time() > float(st['debugUntil']):
            st['режим'] = 'NORMAL'
            st['debugUntil'] = None
            _записать_состояние(st)
            событие('obs', 'режим', 'Result', outcome='ok',
                    safeMessage='срок диагностики истёк, режим вернулся в NORMAL')
    return st['режим']


def задать_режим(новый, часов=None):
    новый = новый.upper()
    if новый not in РЕЖИМЫ:
        raise ValueError(f'режим бывает только {", ".join(РЕЖИМЫ)}')
    st = _прочитать_состояние()
    st['режим'] = новый
    # DIAGNOSTIC без срока не бывает: иначе он остаётся навсегда, и журнал распухает молча.
    st['debugUntil'] = (time.time() + (часов or 4) * 3600) if новый == 'DIAGNOSTIC' else None
    _записать_состояние(st)
    событие('obs', 'режим', 'Result', outcome='ok',
            safeMessage=f'режим {новый}', debugUntil=st['debugUntil'])
    return st


def задать_экспорт(включён):
    st = _прочитать_состояние()
    st['remoteExportEnabled'] = bool(включён)
    _записать_состояние(st)
    событие('obs', 'экспорт', 'Result', outcome='ok',
            safeMessage=f'remoteExportEnabled={bool(включён)}')
    return st


# ─────────────────────────────────────────────────────────────────────────────
# Запись события.

# Что пишется всегда, в любом режиме. Это и есть CORE AUDIT: его нельзя выключить ничем.
CORE = {'INTENT', 'STARTED', 'COMMITTED', 'VERIFIED', 'RETRY', 'RECOVERY', 'DECISION',
        'EXTERNAL', 'RESULT', 'ERROR', 'DUPLICATE', 'LOOP_SUSPECTED', 'STATE', 'HEARTBEAT'}
# Что пишется только в DIAGNOSTIC.
ТОЛЬКО_ДИАГНОСТИКА = {'TIMING', 'DETAIL', 'PROGRESS'}


def _ротация():
    try:
        if os.path.getsize(ЖУРНАЛ) < РАЗМЕР_ФАЙЛА:
            return
    except OSError:
        return
    for i in range(ХРАНИТЬ_ФАЙЛОВ - 1, 0, -1):
        ст, нов = f'{ЖУРНАЛ}.{i}', f'{ЖУРНАЛ}.{i + 1}'
        if os.path.exists(ст):
            os.replace(ст, нов)
    os.replace(ЖУРНАЛ, f'{ЖУРНАЛ}.1')
    лишний = f'{ЖУРНАЛ}.{ХРАНИТЬ_ФАЙЛОВ + 1}'
    if os.path.exists(лишний):
        os.remove(лишний)


def событие(component, operationKey, stage, **поля):
    """Записать одно событие. Возвращает записанную структуру (или None, если режим её глушит)."""
    kind = поля.pop('kind', 'DETAIL')
    m = режим() if component != 'obs' else 'NORMAL'
    if kind not in CORE:
        if m == 'MINIMAL':
            return None
        if m == 'NORMAL' and kind in ТОЛЬКО_ДИАГНОСТИКА:
            return None

    st = _прочитать_состояние()
    st['sequence'] += 1
    _записать_состояние(st)

    e = {
        'schemaVersion': SCHEMA,
        'eventId': uuid.uuid4().hex[:16],
        'sequence': st['sequence'],
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'level': поля.pop('level', 'ERROR' if kind == 'ERROR' else 'INFO'),
        'kind': kind,
        'environment': поля.pop('environment', 'session'),
        'service': 'ai-studio-brand',
        'component': component,
        'releaseSha': _релиз(),
        'correlationId': поля.pop('correlationId', None),
        'operationKey': operationKey,
        'stage': stage,
        'phase': поля.pop('phase', None),
        'stateRevision': st['stateRevision'],
        'attempt': поля.pop('attempt', 1),
        'durationMs': поля.pop('durationMs', None),
        'outcome': поля.pop('outcome', None),
        'errorCode': поля.pop('errorCode', None),
        'safeMessage': None,
        'traceId': поля.pop('traceId', None),
        'spanId': поля.pop('spanId', None),
        'duplicateActions': поля.pop('duplicateActions', 0),
        'writeCounters': поля.pop('writeCounters', None),
    }
    e['safeMessage'] = очистить(поля.pop('safeMessage', None))
    прочее = очистить(поля) if поля else None
    if прочее:
        e['detail'] = прочее
    # Контрольная сумма считается по событию без самой суммы: испорченную строку видно.
    e['checksum'] = hashlib.sha256(
        json.dumps(e, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]

    os.makedirs(ОБЛАСТЬ, exist_ok=True)
    _ротация()
    строка = json.dumps(e, ensure_ascii=False) + '\n'
    # Одна строка — один write, O_APPEND: параллельные писатели не рвут друг друга.
    fd = os.open(ЖУРНАЛ, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, строка.encode('utf-8'))
    finally:
        os.close(fd)
    return e


_релиз_кеш = None


def _релиз():
    global _релиз_кеш
    if _релиз_кеш is None:
        try:
            import subprocess
            _релиз_кеш = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--short', 'HEAD'],
                                        capture_output=True, text=True).stdout.strip() or 'нет-git'
        except Exception:                                        # noqa: BLE001
            _релиз_кеш = 'нет-git'
    return _релиз_кеш


def читать(файл=None, лимит=None):
    """Прочитать журнал, пропуская битые строки. Частично записанная строка не должна ронять разбор."""
    путь = файл or ЖУРНАЛ
    события, битых = [], 0
    if not os.path.exists(путь):
        return события, битых
    for стр in open(путь, encoding='utf-8', errors='replace'):
        стр = стр.strip()
        if not стр:
            continue
        try:
            e = json.loads(стр)
        except Exception:                                        # noqa: BLE001
            битых += 1
            continue
        если_сумма = e.pop('checksum', None)
        своя = hashlib.sha256(
            json.dumps(e, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
        e['checksum'] = если_сумма
        e['checksumOk'] = (если_сумма == своя)
        события.append(e)
    return (события[-лимит:] if лимит else события), битых


# ─────────────────────────────────────────────────────────────────────────────
# Обнаружение замкнутого цикла.
#
# Это главный пункт всей затеи. Проект за сутки трижды заходил на один и тот же круг:
# правка вносилась, проверка её не видела, следующая сессия находила то же самое. Человек
# сказал прямо: «устал ходить по кругу». Fingerprint из полей события ловит именно это.

ОТПЕЧАТОК_ПОЛЯ = ('correlationId', 'operationKey', 'stage', 'phase', 'errorCode', 'stateRevision')
ПОРОГ_ПОВТОРА = 3            # столько одинаковых отпечатков подряд без прогресса
ПОРОГ_КОЛЕБАНИЯ = 2          # столько полных циклов A→B→A→B
ВОЗРАСТ_ЭТАПА = 45 * 60      # секунд: дольше — этап завис


def отпечаток(e):
    return '|'.join(str(e.get(k) or '') for k in ОТПЕЧАТОК_ПОЛЯ)


def _в_секундах(ts):
    try:
        return time.mktime(time.strptime(ts, '%Y-%m-%dT%H:%M:%SZ'))
    except Exception:                                            # noqa: BLE001
        return None


def проверить_цикл(события=None, сейчас=None):
    """Вернуть список подозрений. Каждое — с причиной, первой ошибкой и безопасным следующим шагом.

    Девять признаков из десяти, названных в задании. Десятый — «очередь не уменьшается» —
    в этом проекте не проверяется: очередей нет, а метрика без поля в данных не заводится (F7).
    """
    события = события if события is not None else читать()[0]
    сейчас = сейчас if сейчас is not None else time.time()
    подозрения = []

    # 1. Один отпечаток повторяется без прогресса.
    подряд, прошлый = 0, None
    for e in события:
        о = отпечаток(e)
        if e.get('outcome') in ('ok', 'принят', 'verified'):
            подряд, прошлый = 0, None
            continue
        подряд = подряд + 1 if о == прошлый else 1
        прошлый = о
        if подряд >= ПОРОГ_ПОВТОРА:
            подозрения.append({'признак': 'повтор без прогресса', 'отпечаток': о,
                               'сколько': подряд, 'correlationId': e.get('correlationId')})
            подряд = 0

    # 2. Состояние колеблется A → B → A → B.
    цепь = [f"{e.get('correlationId')}:{e.get('stage')}" for e in события if e.get('stage')]
    for i in range(len(цепь) - 3):
        a, b, c, d = цепь[i:i + 4]
        if a == c and b == d and a != b:
            подозрения.append({'признак': 'колебание состояния', 'отпечаток': f'{a} ↔ {b}',
                               'сколько': ПОРОГ_КОЛЕБАНИЯ, 'correlationId': a.split(':')[0]})
            break

    # 3. Этап длится дольше допустимого. 7. Сердцебиение пропало.
    открытые = {}
    for e in события:
        cid = e.get('correlationId')
        if not cid:
            continue
        if e.get('kind') == 'STARTED':
            открытые[cid] = e
        elif e.get('kind') in ('RESULT', 'VERIFIED'):
            открытые.pop(cid, None)
    for cid, e in открытые.items():
        t = _в_секундах(e.get('timestamp', ''))
        if t and сейчас - t > ВОЗРАСТ_ЭТАПА:
            подозрения.append({'признак': 'этап завис', 'отпечаток': отпечаток(e),
                               'сколько': int((сейчас - t) / 60), 'correlationId': cid,
                               'единица': 'минут'})

    # 4. Уже подтверждённая операция запускается снова.
    подтверждённые = {e.get('correlationId') for e in события if e.get('kind') == 'VERIFIED'}
    for e in события:
        if e.get('kind') == 'STARTED' and e.get('correlationId') in подтверждённые:
            позже = [x for x in события if x.get('correlationId') == e.get('correlationId')
                     and x.get('kind') == 'VERIFIED' and x['sequence'] < e['sequence']]
            if позже:
                подозрения.append({'признак': 'перезапуск подтверждённой операции',
                                   'отпечаток': отпечаток(e), 'сколько': 1,
                                   'correlationId': e.get('correlationId')})

    # 5. Исчерпан лимит повторов. 6. Счётчик дублей больше нуля.
    for e in события:
        if e.get('kind') == 'RETRY' and (e.get('attempt') or 0) >= 3:
            подозрения.append({'признак': 'лимит повторов исчерпан', 'отпечаток': отпечаток(e),
                               'сколько': e.get('attempt'), 'correlationId': e.get('correlationId')})
        if (e.get('duplicateActions') or 0) > 0:
            подозрения.append({'признак': 'дублирующее действие', 'отпечаток': отпечаток(e),
                               'сколько': e.get('duplicateActions'),
                               'correlationId': e.get('correlationId')})

    # 9. stateRevision не двигается там, где обязан. 10. Терминальный результат публикуется дважды.
    терминалы = {}
    for e in события:
        if e.get('kind') == 'RESULT':
            ключ = f"{e.get('correlationId')}:{e.get('operationKey')}"
            терминалы[ключ] = терминалы.get(ключ, 0) + 1
    for ключ, n in терминалы.items():
        if n > 1:
            подозрения.append({'признак': 'терминальный результат опубликован повторно',
                               'отпечаток': ключ, 'сколько': n,
                               'correlationId': ключ.split(':')[0]})

    # дедупликация: одно и то же подозрение не размножаем
    видели, итог = set(), []
    for p in подозрения:
        k = (p['признак'], p['отпечаток'])
        if k in видели:
            continue
        видели.add(k)
        p['перваяОшибка'] = первая_ошибка(события, p.get('correlationId'))
        p['последняяПодтверждённая'] = последняя_подтверждённая(события)
        p['следующийБезопасныйШаг'] = _совет(p['признак'])
        итог.append(p)
    return итог


СОВЕТЫ = {
    'повтор без прогресса':
        'остановить эту операцию; посмотреть первую ошибку глазами; менять не повтор, а причину',
    'колебание состояния':
        'зафиксировать одно из двух состояний решением человека и не переключать автоматически',
    'этап завис':
        'проверить внешний сервис вручную; продолжать с последней подтверждённой операции',
    'перезапуск подтверждённой операции':
        'не запускать заново: результат уже принят, взять его из журнала',
    'лимит повторов исчерпан':
        'дальше повторять бессмысленно — нужно решение человека',
    'дублирующее действие':
        'сверить счётчики записей: возможно, часть работы сделана дважды',
    'терминальный результат опубликован повторно':
        'проверить, не отправлена ли сдача заказчику дважды',
}


def _совет(признак):
    return СОВЕТЫ.get(признак, 'остановиться и показать человеку')


def первая_ошибка(события=None, correlationId=None):
    события = события if события is not None else читать()[0]
    for e in события:
        if e.get('kind') == 'ERROR' and (correlationId is None
                                         or e.get('correlationId') == correlationId):
            return {'sequence': e['sequence'], 'timestamp': e['timestamp'],
                    'stage': e.get('stage'), 'errorCode': e.get('errorCode'),
                    'safeMessage': e.get('safeMessage')}
    return None


def последняя_подтверждённая(события=None):
    события = события if события is not None else читать()[0]
    for e in reversed(события):
        if e.get('kind') == 'VERIFIED':
            return {'correlationId': e.get('correlationId'), 'operationKey': e.get('operationKey'),
                    'timestamp': e['timestamp'], 'sequence': e['sequence']}
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Операция: один сквозной код от начала до конца.

class Операция:
    """Один запрос/кадр/прогон целиком. Пишет INTENT, STARTED, этапы, RESULT.

    Точные счётчики записей ведутся здесь, а не на глаз: `записал()` вызывается в месте
    записи файла. Сегодня «сколько файлов дошло» я считал руками при каждой отправке.
    """

    def __init__(self, component, код=None, ключ='операция', попытка=1):
        self.component = component
        self.correlationId = код or uuid.uuid4().hex[:12]
        self.traceId = uuid.uuid4().hex
        self.operationKey = ключ
        self.attempt = попытка
        self.stage = 'Trigger'
        self.начало = None
        self.счётчики = {'файлов': 0, 'байт': 0, 'внешних': 0, 'проверок': 0}
        self.дублей = 0
        self.ошибка = None
        self.закрыта = False

    # --- служебное
    def _пишу(self, kind, stage=None, **kw):
        return событие(self.component, self.operationKey, stage or self.stage,
                       kind=kind, correlationId=self.correlationId, traceId=self.traceId,
                       spanId=uuid.uuid4().hex[:8], attempt=self.attempt,
                       duplicateActions=self.дублей, writeCounters=dict(self.счётчики), **kw)

    # --- жизненный цикл
    def __enter__(self):
        self._пишу('INTENT', 'Trigger', safeMessage=f'намерение: {self.operationKey}')
        self.начало = time.time()
        self._пишу('STARTED', 'Trigger')
        return self

    def этап(self, имя, **kw):
        if имя not in ЭТАПЫ:
            raise ValueError(f'этап бывает только из {ЭТАПЫ}')
        self.stage = имя
        self._пишу('STATE', имя, **kw)
        return self

    def записал(self, путь, сколько=1, байт=None):
        """Файл записан. Считается здесь — иначе счётчик врёт (F6: у числа один источник)."""
        self.счётчики['файлов'] += сколько
        if байт:
            self.счётчики['байт'] += байт
        self._пишу('COMMITTED', 'Writes', safeMessage=f'записано: {путь}', outcome='ok')
        return self

    def внешнее(self, сервис, что, стоимость=None, **kw):
        """Внешнее действие: генерация, отправка на Диск, push. Пишется всегда, в любом режиме."""
        self.счётчики['внешних'] += 1
        self._пишу('EXTERNAL', 'External', safeMessage=f'{сервис}: {что}',
                   стоимость=стоимость, **kw)
        return self

    def проверил(self, чем, число=None, норма=None, прошло=None):
        self.счётчики['проверок'] += 1
        self._пишу('VERIFIED' if прошло else 'STATE', 'Verification',
                   safeMessage=f'{чем}: {число} (норма {норма})',
                   outcome='ok' if прошло else 'ниже нормы')
        return self

    def решение(self, чьё, что):
        self._пишу('DECISION', self.stage, safeMessage=f'{чьё}: {что}')
        return self

    def дубль(self, что):
        self.дублей += 1
        self._пишу('DUPLICATE', self.stage, safeMessage=f'дубль: {что}', level='WARN')
        return self

    def повтор(self, почему):
        self.attempt += 1
        self._пишу('RETRY', self.stage, safeMessage=f'повтор: {почему}', level='WARN')
        return self

    def сбой(self, код, сообщение):
        """Первая значимая ошибка запоминается: последующие — чаще всего её следствие."""
        if self.ошибка is None:
            self.ошибка = {'errorCode': код, 'safeMessage': сообщение, 'stage': self.stage}
        self._пишу('ERROR', self.stage, errorCode=код, safeMessage=сообщение, level='ERROR')
        return self

    def готово(self, итог='ok'):
        self._закрыть(итог)
        return self

    def _закрыть(self, итог):
        if self.закрыта:
            return
        self.закрыта = True
        мс = int((time.time() - (self.начало or time.time())) * 1000)
        self._пишу('RESULT', 'Result', outcome=итог, durationMs=мс,
                   errorCode=(self.ошибка or {}).get('errorCode'),
                   safeMessage=f'итог: {итог}')
        подозрения = проверить_цикл()
        # Уведомление одно на состояние: повторять его без изменений — самому ходить по кругу.
        if подозрения:
            прошлые = _прочитать_состояние().get('последнее_событие')
            метка = ';'.join(sorted(f"{p['признак']}|{p['отпечаток']}" for p in подозрения))
            if метка != прошлые:
                st = _прочитать_состояние()
                st['последнее_событие'] = метка
                _записать_состояние(st)
                for p in подозрения:
                    событие(self.component, self.operationKey, 'Result', kind='LOOP_SUSPECTED',
                            level='WARN', correlationId=p.get('correlationId'),
                            safeMessage=f"{p['признак']}: {p['следующийБезопасныйШаг']}",
                            признак=p['признак'], отпечаток=p['отпечаток'],
                            перваяОшибка=p.get('перваяОшибка'),
                            последняяПодтверждённая=p.get('последняяПодтверждённая'))

    def __exit__(self, тип, значение, след):
        if тип is not None:
            self.сбой(тип.__name__, str(значение)[:200])
            self._закрыть('исключение')
        else:
            self._закрыть('ok' if self.ошибка is None else 'с ошибкой')
        return False


def операция(component, код=None, ключ='операция', попытка=1):
    return Операция(component, код, ключ, попытка)


def сердцебиение(component='сессия', что='жива'):
    return событие(component, 'heartbeat', 'Trigger', kind='HEARTBEAT', safeMessage=что)
