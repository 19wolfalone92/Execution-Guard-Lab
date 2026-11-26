# Execution Guard Lab 0.3.0 — PARTIAL / deployment HOLD

Независимая лаборатория вычислений, анализа и проверки доказательств. В составе **23 инструмента** (без новых инструментов). Сохраняет ядро 0.2.0; исправлена ошибочная граница выходной схемы `workflow_validate`. Исходные ZIP 0.1.0 и 0.2.0 включены в неизменном виде. Не связана с Production Execution Guard Pro, D1, KV, GitHub writes или торговыми системами.

## Что проверено

- Исходный архив: 85 824 байта, SHA-256 `244aa5b93c99b5b195f9421cdc043b9cad670930f35b9110e2f87a13d49b6578`, 26 файлов, 25 хешей манифеста и CRC подтверждены.
- 269 исходных тестов повторены, 96 stdio и 98 HTTP записей воспроизведены.
- Финальные 364/364 pytest (269 прежних и 95 новых), без пропусков. 121 фактический запрос к отдельному локальному TLS-процессу; 47 положительных вызовов tools/call, 23 различных инструмента. 23 полных результата совпадают с зафиксированными ответами 0.2.0 и проверены по исходным эталонным полям. 23 отрицательных инструментальных случая. Проверки лимитов и отключения клиента дополнительно на ASGI-уровне.
- Новый `secure_http.py`: stateless Streamable HTTP на `/mcp`, TLS, OAuth resource metadata, pinned RS256 public key, ограничение owner/client/issuer/audience/scope/TTL, строгий JSON, размер 128 KiB, 4 одновременно, 180 запросов/60 секунд, 5 секунд на приём тела. Протоколы 2025-03-26, 2025-06-18, 2025-11-25; более новая версия согласуется назад. Полноценный MCP SDK и современный 2026 handshake не проверены.

## Критические ограничения

**Не публиковать текущую локально испытанную среду в интернет.** В установленном Python есть известные advisory для PyJWT 2.13.0 и cryptography 46.0.4. Тесты выполнены только с синтетическими ключами на loopback. `requirements-runtime.txt` содержит целевые обновлённые версии; их установка заблокирована доступом к пакетам. `production_preflight.py` отказывается запускать сервис на несовпадающей среде. Это не заменяет актуальный аудит зависимостей.

Официальный Python SDK 1.30.0 недоступен: pip не нашёл пакет, DNS PyPI недоступен, прямая загрузка опубликованного wheel не удалась. `sdk_probe.py` подготовлен по документации v1; его реальный SDK-run не выполнен. Нет выделенного удалённого хоста, действующего issuer, публичного TLS URL, зарегистрированного подключения Lab. **L3-local = 23; L3-remote/L4/L5/L6 = 0.**

## Состав и воспроизведение

- `lab.py`, `extensions.py` — исходная функциональность; `lab.py` и `http_lab.py` также сохраняют старый локальный 0.2 regression transport, не предназначенный для сети.
- `secure_http.py`, `production_preflight.py`, `Dockerfile`, `compose.yaml` — кандидат 0.3.0 для выделенного хоста. Compose по умолчанию публикует только loopback. Сборка Docker не выполнена: Docker отсутствует в текущей среде.
- `test_secure_http.py`, `run_local_tls_fixture.py` — исключительно синтетическая loopback TLS-квалификация. Тестовый launcher не попадает в Docker image. Не использовать для публичного развёртывания.
- `BASELINE_RERUN.txt`, `BASELINE_RERUN_RPC.json`, `TEST_RESULTS_030.txt`, `TESTS_030.xml`, `SECURE_HTTP_EVIDENCE.json` — фактические журналы, не содержат JWT/заголовков Authorization.
- `MCP_SCHEMAS.json`, `TOOL_REGISTRY.json`, `QUALIFICATION_MATRIX.csv`, `PERMISSION_MATRIX.csv`, `ACCEPTANCE.json` — текущие схемы, матрицы и реестр. `historical_0_2/` — исторические документы, не текущие результаты.
- `SDK_INSTALL_ATTEMPT.txt`, `SDK_IMPORT_CHECK.txt`, `PATCHED_DEPENDENCIES_ATTEMPT.txt`, `PRODUCTION_PREFLIGHT.txt` — реальные причины блокировки.
- `DEPLOYMENT.md`, `CONNECTION.md`, `SECURITY.md`, `REPORT.md` — инструкции, ограничения и отчёт.

В изолированной тестовой среде с установленными квалифицированными зависимостями:

```sh
python -m pip install -r requirements-test.txt
python -m pytest -q
python qualify.py > rerun-local.json
python scripts/verify.py ACCEPTANCE.json
```

Для воспроизведения исторической 0.2.0 распаковать отдельно `BASELINE-0.2.0.zip` и проверить его `MANIFEST.sha256`. Для проверки официальным SDK после установки: `python -m pip install -r requirements-sdk.txt`, `python sdk_probe.py --check-install`; далее следовать `DEPLOYMENT.md`. Не публиковать сервис при FAIL/BLOCKED обязательных проверок.
