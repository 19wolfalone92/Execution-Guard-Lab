# Execution Guard Lab 0.5.0 — квалификация кандидата

Дата: 27 ноября 2026 г. (локальная дата; CI 26 ноября UTC). Статус PARTIAL / HOLD.

## Итог и ограничения

Восстановлен неизменённый исходный код 0.4.0. Существующее ядро 23 инструментов практически прошло квалификацию официального локального Python Workers / workerd; отдельно проверен OAuth Provider в workerd с синтетическим владельцем. Архитектура-кандидат: Python Workers для вычислений + JavaScript/TypeScript Worker с официальным OAuth Provider для транспорта и авторизации, приватная связь между ними ещё не реализована и не испытана. Публичный MCP отсутствует, production OAuth не настроен, ChatGPT 0/23. Версия 0.5.0 относится к пакету квалификации, не к развёрнутому серверу.

## GitHub и изоляция

Ветка qualification/cloud-runtime-oauth-20261127, квалифицированный SHA f914bc6d496e8cb661f9209a4d93d6b26830a434 (5 коммитов, 16 новых файлов относительно 0.4.0). Последующий коммит доказательств и запрета повторного запуска не меняет вычислительное ядро. Main 94bba84b303d273f418a1ef7c9cda7abca2ac92b, не изменён. Main содержит 4 отдельных коммита обновления lab-connection-check.yml; на квалификационной ветке сохранён старый файл и исторический манифест 0.4.0. При будущей интеграции сохранять актуальный main workflow, исторический манифест отдельно. Репозиторий Public.

## Реальное испытание Cloudflare

По подтверждению владельца и run 45905792987: токен активен, один доступный целевой аккаунт, срок 2026-12-27T20:59:59Z; Workers и KV чтение HTTP200. D1 401/10000, R2 403/10000, чтение политики 403/9109; дополнительные полномочия не запрашивались. Полная сохранённая политика не подтверждена независимым API. На этом основании принято решение о строго ограниченном тесте одного Worker без привязок и секретов.

Run 45906590372, job 140204684223: реальное создание Worker eglab-probe-45906590372-1, запись кода HTTP200, чтение конфигурации и версии HTTP200, включение workers.dev HTTP200. Version ID 95c5ab22-b590-46dd-bda4-f02ea41bfae4, deployment ID c5af4e54-096c-4df3-be9d-1d46d65eb8e7. SHA-256 исходника тестового Worker 3015133f8361baf910f2f6833bf41beef8d2134ca8da0404948827087702a0cd.

HTTPS GET был отклонён (ветка обработки 401/403; точный код не записан). Причина неизвестна; это не подтверждает блокировку OpenAI. Никаких повторов, альтернативных URL или последующих облачных изменений не выполнялось. Обновление, откат, отключение тестового subdomain не проверены; последний подтверждённый API статус — enabled. Тестовый Worker не является MCP и не содержит данных пользователя. Активный workflow записи переведён в HOLD без доступа к Secrets; оригинал сохранён в evidence_0.5.0. Не запускать повторно предыдущий run.

## Runtime

Workers-py 1.17.9, workers-runtime-sdk 1.9.7, Wrangler 4.168.0, Pyodide CPython 3.14.2. Первоначальные ошибки: uv 0.12.19 ниже минимальной версии; rpds-py 2026.5.1 не имеет необходимого WASM wheel. Исправлены uv 0.13.4 и отдельным pin rpds-py 0.30.0 для WASM. Нативный requirements.lock неизменён.

Run 45907197036: 69/69 эквивалентных результатов (23 baseline, 23 stress, 23 negative), 230/230 повторных стресс-вызовов, 4 параллельных вызова. Медиана wall 3.26108 ms, максимум 62.022497 ms; первый health 1273 ms. CPU процесса 1–45 ms в среднем на повтор; time_series_analyze 11 ms, code_structure_analyze 45 ms. RSS всего процесса workerd до 401596 KiB; RSS CPython harness 40460 KiB. Это не CPU/RAM отдельного облачного isolate и не доказательство превышения облачных лимитов. Free plan ориентиры официальной документации: 10 ms CPU, 128 MB isolate, 100000 запросов/сутки, KV read 100000/day, write 1000/day. Требуется измерение на фактическом тарифе. Cloudflare Containers требуют платных ресурсов; не подключены.

## OAuth

Официальный @cloudflare/workers-oauth-provider 1.4.0. Run 45907196967: 22/22 локальных проверок (metadata, DCR, S256, неверный redirect, consent, отказ/неизвестный владелец, неверный verifier и resource, replay+revocation, refresh, forged/revoked token). Первый тест ошибочно проверял доступ после replay; provider по RFC 6749 отзывает grant, поэтому исправлен порядок и явно проверен отзыв. Реальный GitHub identity adapter не испытан с живыми credentials; отдельное приложение GitHub OAuth не зарегистрировано. Кандидат scope lab:read, access TTL 900 s, refresh TTL 7 days. Production URL, client ID, redirect URI и owner ID не определены. Не передавать токены через чат.

## Регрессия и аудит

Run 45907197010: 366/366 PASS (364 baseline + 2 mock tests), 96/96 SDK, 23/23, 2 сессии, MCP 2025-11-25. 35 Python зависимостей без известных уязвимостей по pip-audit, 6 Pyodide зависимостей без известных уязвимостей, npm audit 0. Указанные результаты относятся к разрешённым графам, не являются полноценным production security audit. Production preflight не пройден.

## Восстановление и следующая безопасная точка

1. Сохранить original 0.4.0, все evidence ZIP и контрольные суммы. Не использовать тестовые local fixtures как production endpoints.
2. Владелец в Cloudflare dashboard лабораторного аккаунта проверяет Worker eglab-probe-45906590372-1, причину отклонения HTTPS и состояние workers.dev; при необходимости выключает только этот статический Worker. Не менять права токена или тариф без основания. Не повторять отклонённую операцию до разрешения.
3. Независимые оставшиеся работы: production service binding, защищённый Streamable HTTP, ограничения, проверки real identity/PKCE/expiry/scope/session isolation и фактического тарифа, preflight. После подтверждения полномочий — отдельно разрешённая квалификация развёртывания, затем remote SDK и ChatGPT. Никакой регистрации до действительного защищённого MCP URL.
4. Не затрагивать Pro и Bridge; Pro main a61f1061b91dbabce2bb3ccf66ba710589b21808, PR5 open/unmerged, head 097466cd33842f6dafabc5e3411c84fb6f1e5d52, checkpoint rev43.

## Доказательства
- Run [45906590372](https://github.com/19wolfalone92/Execution-Guard-Lab/actions/runs/45906590372): `Lab-write-45906590372.zip` SHA-256 `ac33a521bbaf754f666c26d385c933cf82d74db8e278269ba8e817e779da7311`.
- Run [45907197010](https://github.com/19wolfalone92/Execution-Guard-Lab/actions/runs/45907197010): `Lab-regression-45907197010.zip` SHA-256 `0577186d8da04a35d7b964975450645fcf86e8e222025e830f225d10f4f4e294`.
- Run [45907197036](https://github.com/19wolfalone92/Execution-Guard-Lab/actions/runs/45907197036): `Lab-runtime-45907197036.zip` SHA-256 `2936cc996e2b0214f282e1bea4f30483a9c30da3f96405727f5b789d3e0701cf`.
- Run [45907196967](https://github.com/19wolfalone92/Execution-Guard-Lab/actions/runs/45907196967): `Lab-oauth-45907196967.zip` SHA-256 `2d07d9384e0f3ec2396dd644781d16dd16c20b80f3926d6a37d9af9d2f41c067`.

Матрица 36 Gate: BLOCKED=11, PARTIAL=9, PASS=15, UNVERIFIED=1. См. ACCEPTANCE_0.5.0.json. Для всех 23 максимальный подтверждённый уровень L3-local, см. evidence_0.5.0/tool_qualification.csv.
