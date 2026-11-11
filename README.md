# AI Firewall v2 — итерация 3, защищённый Svelte чат

Текущий запуск — `/home/user/ai-fire2/compose.yaml`, UI обслуживает Protected
Open WebUI на `http://127.0.0.1:8088/`, временный Gateway UI удалён.
Это ограниченная защищённая редакция upstream интерфейса, не минимально изменённый
полный штатный Chat.svelte. Подробности и честные границы результата:
`/home/user/ai-fire2/docs/iteration-3-verification.md`.

```sh
cd /home/user/ai-fire2
# Для нового .env, только один раз:
sh /home/user/ai-fire2/scripts/setup.sh
# Если .env уже существует со второй итерации, добавьте USER_B_KEY:
# printf '\nUSER_B_KEY=%s\n' "$(openssl rand -hex 32)" >> /home/user/ai-fire2/.env
python3 /home/user/ai-fire2/scripts/prepare-webui.py
python3 /home/user/ai-fire2/scripts/prepare-iteration3.py
docker compose build webui gateway vault mock tests browser-tests
docker compose up -d
sh /home/user/ai-fire2/scripts/verify-iteration3.sh
```

Войти с USER_KEY или USER_B_KEY из `.env`. Пример сообщения:
`Hello SYNTHETIC_PII_ALICE_001`. Кнопка «Показать оригинал» раскрывает только
выбранное сообщение. Следующие сообщения используют server-owned masked history.
BLOCK: `SYNTHETIC_BLOCK_TEST`. 20 turns/chat; новый чат создаётся в БД после
первого успешного turn. Только синтетические ПДн — не реальные данные.

Для остановки: `docker compose stop`. Не удаляйте volumes для обычного перезапуска.
Патч `/home/user/ai-fire2/patches/open-webui-v0.13.3-iteration3.patch` включает
backend entrypoint, Svelte UI и удаление неподдержанных routes; generator проверяет
git apply на чистом pinned checkout. Vendor working tree не изменяется.

## Архив описания итерации 2 (не текущая инструкция запуска)

2026-11-11. Только синтетические данные, НЕ production.

## Запуск

```sh
cd /home/user/ai-fire2
# Только первый раз: существующий .env не перезаписывается
sh /home/user/ai-fire2/scripts/setup.sh
python3 /home/user/ai-fire2/scripts/prepare-webui.py
 docker compose build
 docker compose up -d
 docker compose run --rm tests
```

UI: http://127.0.0.1:8088/ — введите USER_KEY из локального .env.
Текст: `Hello SYNTHETIC_PII_ALICE_001`. Send показывает маску, Reveal last response
восстанавливает копию ответа только для отображения. BLOCK: `SYNTHETIC_BLOCK_TEST`.
Остановка: `docker compose stop`, без удаления volumes. Первый pull большой.
Тесты ждут сервисы до 180 секунд; при долгой миграции повторите после старта.

## Реализованный срез

Это альтернативный минимальный UI Gateway, НЕ штатный Svelte-чат Open WebUI.
Каждый Send создаёт отдельный чат. Штатные API, history/edit/resend/import/files
и WebSocket закрыты. Исходный барьер в
`/home/user/ai-fire2/src/ai_firewall/ingress.py` не изменён.

Gateway → обязательный SyntheticDetector → Vault → LiteLLM → Mock → обязательная
проверка ответа → admission → защищённый adapter → реальная модель Chats и БД
Open WebUI v0.13.3. До успешной проверки ответа не сохраняется даже вход.
Admission связан с точными input/output, identity, operation, policy, TTL 30s.
Одноразовое потребление атомарно хранится в отдельной SQLite БД.
/view имеет no-store, не вызывает writer. Vault недоступен сети WebUI/LiteLLM.
Порты Mock/LiteLLM/WebUI/Vault не опубликованы; тестовый контейнер привилегирован.

Код: `/home/user/ai-fire2/src/ai_firewall/services.py`,
`/home/user/ai-fire2/src/ai_firewall/webui_poc.py`.
Compose: `/home/user/ai-fire2/compose.yaml`; Dockerfiles и LiteLLM YAML:
`/home/user/ai-fire2/docker/`.
Патч `/home/user/ai-fire2/patches/open-webui-v0.13.3-poc.patch` применяется к ЧИСТОЙ
базе b0e6098e940942281d9c83f3529ea117287a3a22, не поверх locked.patch.
prepare-webui.py воспроизводит entrypoint из git без изменения vendor checkout.

Mock: GET /health, GET /v1/models, POST /v1/chat/completions, только текст,
stream=false. normal/echo/template/leak/injection/error/timeout выбираются
MOCK_SCENARIO либо POST /test/scenario с отдельным TEST_KEY во внутренней сети.
GET /test/last — защищённый RAM-only probe. Промпты не меняют сценарий.
Gateway: /check (ALLOW/MASK либо 403 BLOCK), /chat, /view.
VAULT_TTL — секунды, по умолчанию 3600. Секреты генерируются в .env (0600).
Будущая локальная LLM подключается заменой provider/api_base/key в LiteLLM YAML.

## Ограничения — реальные ПДн запрещены

Детектор распознаёт ТОЛЬКО `SYNTHETIC_PII_[A-Za-z0-9_]+`, BLOCK — маркер
`SYNTHETIC_BLOCK_`. Реальные email/телефоны/имена не защищает. Presidio/Natasha
не подключены; точка расширения — обязательный inspect-адаптер.
Vault — отдельная plaintext SQLite: нет промышленного шифрования, KMS,
защищённого удаления страниц/WAL/backups. TTL запрещает reveal после истечения,
очистка ленивая при store. Identity одна, привязана к USER_KEY; нет полноценного
IAM, TLS, rate limiting и многоходового чата. Не публикуйте стенд наружу.
Компрометация admission key вне модели POC. Нет полного CVE/SBOM-аудита upstream.
Это узкий работающий POC, не полное выполнение интеграции штатного Open WebUI UI.
Отчёт: `/home/user/ai-fire2/docs/poc-verification.md`.
