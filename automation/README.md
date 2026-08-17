# Автоотправка на GitHub

Копия того, что стоит на маке. Нужна, если папку придётся разворачивать заново.

`sync.sh` живёт на уровень выше папки `project/` — то есть в `~/Developer/AI-STUDIO/sync.sh`.
`com.aistudio.autosync.plist` копируется в `~/Library/LaunchAgents/` и загружается:

    cp automation/com.aistudio.autosync.plist ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/com.aistudio.autosync.plist

Агент раз в 5 минут запускает `sync.sh`: тот делает коммит, если что-то изменилось, и отправляет
на GitHub. Лог — `/tmp/aistudio-autosync.log`.

## Два подводных камня, оба проверены на себе

**Папка не должна лежать на Рабочем столе.** macOS не пускает фоновые задачи к `~/Desktop`, агент
падает с `Operation not permitted` — молча, потому что ошибка уходит в лог, а не на экран.
`~/Developer` этой защиты не имеет.

**Забытый `.git/index.lock` блокирует всё насмерть.** Живой git держит этот замок секунды; если
файл остался от прерванной операции, каждый коммит будет падать. `sync.sh` снимает такие замки
сам, если они старше пяти минут.
