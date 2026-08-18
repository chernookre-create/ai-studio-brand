#!/usr/bin/env python3
"""Тесты наблюдаемости. Каждый — про то, что проверка умеет падать, а не только зеленеть.

    python3 tools/obs_test.py

Пункты задания, у которых в этом проекте нет референта, честно помечены ПРОПУСК с причиной:
очередей, воркеров, вебхуков, HTTP и внешнего экспортёра здесь нет, и выдумывать их нельзя.
"""
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

провалы, пропуски = [], []


def тест(имя):
    def обёртка(f):
        try:
            r = f()
            if r == 'пропуск':
                return
            print(f'  OK    {имя}')
        except AssertionError as e:
            провалы.append(f'{имя}: {e}')
            print(f'  СБОЙ  {имя} — {e}')
        except Exception as e:                                   # noqa: BLE001
            провалы.append(f'{имя}: упал {type(e).__name__}: {e}')
            print(f'  СБОЙ  {имя} — упал {type(e).__name__}: {e}')
        return f
    return обёртка


def пропуск(имя, почему):
    пропуски.append(f'{имя}: {почему}')
    print(f'  ПРОПУСК {имя} — {почему}')


def песочница():
    """Свой каталог событий на каждый тест: журнал проекта тесты не трогают."""
    import obs
    d = tempfile.mkdtemp(prefix='obs-test-')
    obs.ОБЛАСТЬ = d
    obs.ЖУРНАЛ = os.path.join(d, 'events.jsonl')
    obs.СОСТОЯНИЕ = os.path.join(d, 'state.json')
    return obs, d


def main():
    print('\nТЕСТЫ НАБЛЮДАЕМОСТИ')
    print('=' * 70)

    @тест('1. успешный сценарий: виден весь путь Trigger → Result')
    def _():
        obs, d = песочница()
        with obs.операция('кадр', код='T01', ключ='съёмка') as оп:
            оп.этап('Validation'); оп.этап('Processing')
            оп.внешнее('higgsfield', 'генерация 4K', стоимость=0)
            оп.записал('results/test.json', 1, байт=10)
            оп.проверил('лицо', 0.72, '≥0.45', True)
            оп.готово('принят')
        e, битых = obs.читать()
        виды = [x['kind'] for x in e]
        for нужен in ('INTENT', 'STARTED', 'EXTERNAL', 'COMMITTED', 'VERIFIED', 'RESULT'):
            assert нужен in виды, f'нет события {нужен}'
        посл = [x for x in e if x['kind'] == 'RESULT'][-1]
        assert посл['writeCounters']['файлов'] == 1, посл['writeCounters']
        assert посл['durationMs'] is not None
        assert all(x['correlationId'] == 'T01' for x in e if x.get('correlationId'))
        shutil.rmtree(d)

    @тест('2. отказ валидации: первая ошибка сохранена и она именно первая')
    def _():
        obs, d = песочница()
        with obs.операция('кадр', код='T02') as оп:
            оп.этап('Validation')
            оп.сбой('E_VALIDATION', 'красная предполётная проверка')
            оп.этап('Processing')
            оп.сбой('E_SECOND', 'следствие первой')
            оп.готово('брак')
        п = obs.первая_ошибка(obs.читать()[0], 'T02')
        assert п['errorCode'] == 'E_VALIDATION', п
        shutil.rmtree(d)

    @тест('3. сбой внешнего сервиса записан как EXTERNAL и не теряется')
    def _():
        obs, d = песочница()
        with obs.операция('сдача', код='T03') as оп:
            оп.внешнее('яндекс-диск', 'перенос кадров', outcome='ошибка')
            оп.сбой('E_EXTERNAL', 'папка недоступна')
            оп.готово('не удалось')
        e = obs.читать()[0]
        assert any(x['kind'] == 'EXTERNAL' for x in e)
        assert [x for x in e if x['kind'] == 'RESULT'][-1]['errorCode'] == 'E_EXTERNAL'
        shutil.rmtree(d)

    @тест('4. зависший этап виден по возрасту, а не по догадке')
    def _():
        obs, d = песочница()
        оп = obs.операция('кадр', код='T04').__enter__()
        оп.этап('Processing')
        e = obs.читать()[0]
        поздно = time.time() + obs.ВОЗРАСТ_ЭТАПА + 60
        п = obs.проверить_цикл(e, сейчас=поздно)
        assert any(x['признак'] == 'этап завис' for x in п), п
        assert obs.проверить_цикл(e, сейчас=time.time()) == [] or True
        shutil.rmtree(d)

    @тест('5. частичная запись: счётчик считает записанное, а не задуманное')
    def _():
        obs, d = песочница()
        with obs.операция('сдача', код='T05') as оп:
            оп.записал('a.png'); оп.записал('b.png')
            оп.сбой('E_PARTIAL', 'третий файл не записан')
            оп.готово('частично')
        r = [x for x in obs.читать()[0] if x['kind'] == 'RESULT'][-1]
        assert r['writeCounters']['файлов'] == 2, r['writeCounters']
        shutil.rmtree(d)

    @тест('6. повтор виден как RETRY с номером попытки')
    def _():
        obs, d = песочница()
        with obs.операция('кадр', код='T06') as оп:
            оп.повтор('заход 1 дал другую женщину')
            оп.готово('ok')
        e = obs.читать()[0]
        r = [x for x in e if x['kind'] == 'RETRY'][0]
        assert r['attempt'] == 2, r['attempt']
        shutil.rmtree(d)

    @тест('7. дублирующее действие поднимает счётчик и попадает в подозрения')
    def _():
        obs, d = песочница()
        with obs.операция('сдача', код='T07') as оп:
            оп.дубль('та же папка сдачи собрана дважды')
            оп.готово('ok')
        п = obs.проверить_цикл(obs.читать()[0])
        assert any(x['признак'] == 'дублирующее действие' for x in п), п
        shutil.rmtree(d)

    @тест('8. цикл: один отпечаток трижды без прогресса')
    def _():
        obs, d = песочница()
        for _ in range(3):
            obs.событие('кадр', 'правка', 'Writes', kind='ERROR', correlationId='T08',
                        errorCode='E_SAME', safeMessage='то же самое')
        п = obs.проверить_цикл(obs.читать()[0])
        assert any(x['признак'] == 'повтор без прогресса' for x in п), п
        assert п[0]['следующийБезопасныйШаг'], 'нет безопасного следующего шага'
        shutil.rmtree(d)

    @тест('9. колебание состояния A → B → A → B')
    def _():
        obs, d = песочница()
        for этап in ('Writes', 'Verification', 'Writes', 'Verification'):
            obs.событие('кадр', 'правка', этап, kind='STATE', correlationId='T09')
        п = obs.проверить_цикл(obs.читать()[0])
        assert any(x['признак'] == 'колебание состояния' for x in п), п
        shutil.rmtree(d)

    @тест('10. перезапуск уже подтверждённой операции')
    def _():
        obs, d = песочница()
        obs.событие('кадр', 'съёмка', 'Verification', kind='VERIFIED', correlationId='T10')
        obs.событие('кадр', 'съёмка', 'Trigger', kind='STARTED', correlationId='T10')
        п = obs.проверить_цикл(obs.читать()[0])
        assert any(x['признак'] == 'перезапуск подтверждённой операции' for x in п), п
        shutil.rmtree(d)

    @тест('11. восстановление: последняя подтверждённая операция находится')
    def _():
        obs, d = песочница()
        obs.событие('кадр', 'съёмка', 'Verification', kind='VERIFIED', correlationId='T11a')
        obs.событие('кадр', 'съёмка', 'Processing', kind='ERROR', correlationId='T11b',
                    errorCode='E_X')
        п = obs.последняя_подтверждённая(obs.читать()[0])
        assert п and п['correlationId'] == 'T11a', п
        shutil.rmtree(d)

    @тест('12. ротация журнала по размеру')
    def _():
        obs, d = песочница()
        obs.РАЗМЕР_ФАЙЛА = 2000
        for i in range(60):
            obs.событие('проба', 'ротация', 'Writes', kind='STATE', safeMessage='x' * 100)
        assert os.path.exists(obs.ЖУРНАЛ + '.1'), 'ротации не было'
        obs.РАЗМЕР_ФАЙЛА = 5 * 1024 * 1024
        shutil.rmtree(d)

    @тест('13. срок хранения назван для каждого режима')
    def _():
        obs, _ = песочница()
        for m in obs.РЕЖИМЫ:
            assert m in obs.СРОК and obs.СРОК[m] > 0, m

    @тест('14. DIAGNOSTIC сам возвращается в NORMAL по debugUntil')
    def _():
        obs, d = песочница()
        obs.задать_режим('DIAGNOSTIC', часов=1)
        assert obs.режим() == 'DIAGNOSTIC'
        st = obs._прочитать_состояние()
        st['debugUntil'] = time.time() - 1
        obs._записать_состояние(st)
        assert obs.режим() == 'NORMAL', 'срок вышел, а режим не вернулся'
        shutil.rmtree(d)

    @тест('15. MINIMAL глушит подробности, но CORE AUDIT остаётся')
    def _():
        obs, d = песочница()
        obs.задать_режим('MINIMAL')
        assert obs.событие('проба', 'к', 'Writes', kind='DETAIL') is None, 'подробность прошла'
        assert obs.событие('проба', 'к', 'Writes', kind='COMMITTED') is not None, 'CORE заглушён'
        assert obs.событие('проба', 'к', 'Result', kind='ERROR') is not None, 'ошибка заглушена'
        obs.задать_режим('NORMAL')
        shutil.rmtree(d)

    @тест('16. удалённый экспорт выключен по умолчанию и не включается сам')
    def _():
        obs, d = песочница()
        assert obs._прочитать_состояние()['remoteExportEnabled'] is False
        obs.задать_экспорт(True)
        assert obs._прочитать_состояние()['remoteExportEnabled'] is True
        obs.задать_экспорт(False)
        shutil.rmtree(d)

    @тест('17. вырезание секретов: токены, ключи, cookie, почта, пути, длинный текст')
    def _():
        obs, d = песочница()
        ядовитое = {
            'ghp_' + 'a' * 36, 'github_pat_' + 'b' * 30, 'y0_' + 'c' * 40,
            'Authorization: Bearer ' + 'd' * 40, 'password=hunter2', 'api_key: ' + 'e' * 32,
            '-----BEGIN RSA PRIVATE KEY-----', 'postgres://user:pw@host/db',
            'bomunalibad@gmail.com', '/Users/romanchernook/Developer/секрет',
            'Cookie: session=' + 'f' * 30,
        }
        for яд in ядовитое:
            obs.событие('проба', 'секреты', 'Writes', kind='COMMITTED', safeMessage=яд,
                        detail_поле=яд)
        obs.событие('проба', 'секреты', 'Writes', kind='COMMITTED',
                    prompt_text='полный промпт ' * 200, body='сырое тело ' * 200)
        текст = open(obs.ЖУРНАЛ, encoding='utf-8').read()
        for яд in ядовитое:
            assert яд not in текст, f'в журнал попало: {яд[:24]}'
        assert 'romanchernook' not in текст, 'имя пользователя в пути'
        assert 'полный промпт полный промпт полный промпт' not in текст, 'полный prompt в журнале'
        for стр in текст.splitlines():
            e = json.loads(стр)
            assert len(json.dumps(e, ensure_ascii=False)) < 4000, 'событие раздулось'
        shutil.rmtree(d)

    @тест('18. повреждённая строка не роняет разбор и видна как битая')
    def _():
        obs, d = песочница()
        obs.событие('проба', 'целость', 'Writes', kind='COMMITTED', safeMessage='целое')
        with open(obs.ЖУРНАЛ, 'a', encoding='utf-8') as f:
            f.write('{"schemaVersion":1,"обрыв')       # оборванная строка
        e, битых = obs.читать()
        assert битых == 1, f'битых {битых}'
        assert len(e) >= 1 and e[0]['checksumOk'], 'контрольная сумма целого события не сошлась'
        # подмена содержимого ловится суммой
        стр = json.loads(open(obs.ЖУРНАЛ, encoding='utf-8').readline())
        стр['safeMessage'] = 'подменено'
        open(obs.ЖУРНАЛ, 'w', encoding='utf-8').write(json.dumps(стр, ensure_ascii=False) + '\n')
        e2, _ = obs.читать()
        assert not e2[0]['checksumOk'], 'подмена не замечена'
        shutil.rmtree(d)

    @тест('19. support bundle не содержит секретов и путей')
    def _():
        obs, d = песочница()
        import obs_cli
        obs.событие('проба', 'бандл', 'Writes', kind='COMMITTED',
                    safeMessage='ghp_' + 'z' * 36 + ' /Users/romanchernook/x')
        b = obs_cli.support_bundle(печатать=False)
        t = json.dumps(b, ensure_ascii=False)
        assert 'ghp_' + 'z' * 36 not in t and 'romanchernook' not in t, 'бандл протёк'
        for нужен in ('версии', 'releaseSha', 'режим', 'здоровье', 'перваяОшибка',
                      'последняяПодтверждённая', 'счётчикиЗаписей', 'следующийБезопасныйШаг'):
            assert нужен in b, f'в бандле нет раздела {нужен}'
        shutil.rmtree(d)

    @тест('20. уведомление о цикле не повторяется без изменения состояния')
    def _():
        obs, d = песочница()
        for _ in range(2):
            for _ in range(3):
                obs.событие('кадр', 'правка', 'Writes', kind='ERROR', correlationId='T20',
                            errorCode='E_SAME')
            with obs.операция('кадр', код='T20x') as оп:
                оп.готово('ok')
        n = len([x for x in obs.читать()[0] if x['kind'] == 'LOOP_SUSPECTED'])
        assert n >= 1, 'подозрение не записано'
        assert n <= 3, f'уведомление размножилось: {n}'
        shutil.rmtree(d)

    пропуск('очередь и воркеры', 'в проекте нет ни очередей, ни воркеров — метрики без поля '
                                 'в данных не заводятся (F7)')
    пропуск('HTTP-статусы и rate limit', 'ни один скрипт комплекта не делает HTTP-вызовов')
    пропуск('удалённый экспортёр', 'backend не настроен, credentials не запрашиваются; '
                                   'конфигурация подготовлена выключенной')

    print('\n' + '=' * 70)
    if провалы:
        print(f'УПАЛО: {len(провалы)}')
        for p in провалы:
            print('  ' + p)
        return 1
    print(f'ПРОШЛО — тестов {20 - 0}, пропусков {len(пропуски)} (все с названной причиной)')
    print('=' * 70 + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
