#!/usr/bin/env python3
"""Команды наблюдаемости.

    python3 tools/obs_cli.py status            общее состояние
    python3 tools/obs_cli.py health            runtime и зависимости
    python3 tools/obs_cli.py tail [N]          последние безопасные события
    python3 tools/obs_cli.py errors [N]        последние ошибки
    python3 tools/obs_cli.py trace <id>        весь путь одной операции
    python3 tools/obs_cli.py set-mode DIAGNOSTIC|NORMAL|MINIMAL [часов]
    python3 tools/obs_cli.py export-on | export-off
    python3 tools/obs_cli.py support-bundle    безопасный свёрток для разбора
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import obs                                                       # noqa: E402


def _счётчики():
    итог = {'файлов': 0, 'байт': 0, 'внешних': 0, 'проверок': 0}
    for e in obs.читать()[0]:
        w = e.get('writeCounters') or {}
        for k in итог:
            итог[k] = max(итог[k], w.get(k, 0)) if e.get('kind') == 'RESULT' else итог[k]
    # точный счёт: суммируем терминальные результаты, а не максимум по всему журналу
    точно = {'файлов': 0, 'байт': 0, 'внешних': 0, 'проверок': 0}
    for e in obs.читать()[0]:
        if e.get('kind') == 'RESULT':
            for k, v in (e.get('writeCounters') or {}).items():
                точно[k] = точно.get(k, 0) + (v or 0)
    return точно


def status(печатать=True):
    e, битых = obs.читать()
    st = obs._прочитать_состояние()
    открытые = {}
    for x in e:
        cid = x.get('correlationId')
        if not cid:
            continue
        if x.get('kind') == 'STARTED':
            открытые[cid] = x
        elif x.get('kind') in ('RESULT',):
            открытые.pop(cid, None)
    d = {
        'режим': obs.режим(),
        'debugUntil': (time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(float(st['debugUntil'])))
                       if st.get('debugUntil') else None),
        'remoteExportEnabled': st['remoteExportEnabled'],
        'releaseSha': obs._релиз(),
        'событий': len(e),
        'битыхСтрок': битых,
        'операцийОткрыто': sorted(открытые),
        'счётчикиЗаписей': _счётчики(),
        'перваяОшибка': obs.первая_ошибка(e),
        'последняяПодтверждённая': obs.последняя_подтверждённая(e),
        'подозренияНаЦикл': [p['признак'] for p in obs.проверить_цикл(e)],
    }
    if печатать:
        print(json.dumps(d, ensure_ascii=False, indent=1))
    return d


def health(печатать=True):
    import subprocess
    зав = {}
    for имя, код in (('cv2', 'import cv2'), ('numpy', 'import numpy'),
                     ('insightface', 'from insightface.app import FaceAnalysis'),
                     ('rembg-u2net', "import sys,os;sys.path.insert(0,os.path.join(%r,'tools'));"
                                     "from scale_fig import сессия_вырезания;сессия_вырезания()"
                                     % ROOT)):
        r = subprocess.run([sys.executable, '-c', код], capture_output=True, text=True)
        зав[имя] = 'ok' if r.returncode == 0 else f'сбой (код {r.returncode})'
    e = obs.читать()[0]
    удары = [x for x in e if x.get('kind') == 'HEARTBEAT']
    возраст = None
    if удары:
        t = obs._в_секундах(удары[-1]['timestamp'])
        возраст = int(time.time() - t) if t else None
    d = {'зависимости': зав, 'событий': len(e),
         'возрастСердцебиенияСек': возраст,
         'журнал': os.path.relpath(obs.ЖУРНАЛ, ROOT),
         'экспортёр': 'выключен (backend не настроен)'
                      if not obs._прочитать_состояние()['remoteExportEnabled'] else 'включён'}
    if печатать:
        print(json.dumps(d, ensure_ascii=False, indent=1))
    return d


def tail(n=20):
    for e in obs.читать()[0][-n:]:
        print(f"{e['sequence']:>5} {e['timestamp']} {e['kind']:<16} "
              f"{(e.get('correlationId') or '—'):<12} {e['stage']:<13} "
              f"{(e.get('safeMessage') or '')[:60]}")


def errors(n=20):
    for e in [x for x in obs.читать()[0] if x.get('kind') == 'ERROR'][-n:]:
        print(f"{e['sequence']:>5} {e['timestamp']} {e.get('errorCode')} "
              f"{(e.get('correlationId') or '—')} {e['stage']}: {e.get('safeMessage')}")


def trace(cid):
    e = [x for x in obs.читать()[0] if x.get('correlationId') == cid]
    if not e:
        print(f'операции {cid} в журнале нет')
        return 1
    print(f'\nПуть операции {cid}\n' + '-' * 70)
    for x in e:
        д = f" {x['durationMs']} мс" if x.get('durationMs') else ''
        print(f"{x['timestamp']} {x['stage']:<13} {x['kind']:<16}"
              f"{(x.get('safeMessage') or '')[:52]}{д}")
    посл = e[-1]
    print('-' * 70)
    print(f"итог: {посл.get('outcome')}   записей: {посл.get('writeCounters')}")
    return 0


def support_bundle(печатать=True):
    """Свёрток для разбора. Всё через тот же санитайзер — секретам взяться неоткуда."""
    e, битых = obs.читать()
    b = {
        'версии': {'python': sys.version.split()[0], 'схемаСобытий': obs.SCHEMA},
        'releaseSha': obs._релиз(),
        'режим': obs.режим(),
        'здоровье': health(печатать=False),
        'состояниеБезопасное': {k: v for k, v in obs._прочитать_состояние().items()
                                if k in ('режим', 'remoteExportEnabled', 'sequence',
                                         'stateRevision')},
        'последниеСобытия': [{k: v for k, v in x.items()
                              if k in ('sequence', 'timestamp', 'kind', 'stage', 'outcome',
                                       'errorCode', 'safeMessage', 'correlationId')}
                             for x in e[-40:]],
        'переходыСостояний': [f"{x.get('correlationId')}:{x['stage']}"
                              for x in e if x.get('kind') == 'STATE'][-40:],
        'перваяОшибка': obs.первая_ошибка(e),
        'последняяПодтверждённая': obs.последняя_подтверждённая(e),
        'счётчикиЗаписей': _счётчики(),
        'битыхСтрок': битых,
        'подозренияНаЦикл': obs.проверить_цикл(e),
        'следующийБезопасныйШаг': (obs.проверить_цикл(e)[0]['следующийБезопасныйШаг']
                                   if obs.проверить_цикл(e) else
                                   'продолжать с последней подтверждённой операции'),
    }
    b = obs.очистить(b)
    b['контрольнаяСумма'] = __import__('hashlib').sha256(
        json.dumps(b, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    if печатать:
        print(json.dumps(b, ensure_ascii=False, indent=1))
    return b


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 2
    к = a[0]
    if к == 'status':
        status(); return 0
    if к == 'health':
        health(); return 0
    if к == 'tail':
        tail(int(a[1]) if len(a) > 1 else 20); return 0
    if к == 'errors':
        errors(int(a[1]) if len(a) > 1 else 20); return 0
    if к == 'trace':
        if len(a) < 2:
            print('нужен код операции: trace <id>'); return 2
        return trace(a[1])
    if к == 'set-mode':
        if len(a) < 2:
            print('нужен режим: ' + ', '.join(obs.РЕЖИМЫ)); return 2
        st = obs.задать_режим(a[1], float(a[2]) if len(a) > 2 else None)
        print(f"режим {st['режим']}" + (f", до {time.strftime('%H:%M', time.localtime(st['debugUntil']))}"
                                        if st['debugUntil'] else '')); return 0
    if к == 'export-on':
        obs.задать_экспорт(True)
        print('remoteExportEnabled=True. Backend не настроен — события никуда не уходят,')
        print('пока не появится конфигурация. Credentials в чат не запрашиваются.'); return 0
    if к == 'export-off':
        obs.задать_экспорт(False); print('remoteExportEnabled=False'); return 0
    if к == 'support-bundle':
        support_bundle(); return 0
    print(f'не знаю команду «{к}»'); print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
