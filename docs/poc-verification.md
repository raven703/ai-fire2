# Реальные проверки 2026-11-11

Ubuntu/WSL2, Docker 29.6.1, Compose v5.3.0. Без sudo и удаления volumes.

Полный повторный прогон Docker Compose: **31 passed, 1 warning in 5.18s**.
Команда: docker compose run --rm --no-deps tests pytest -q -p no:cacheprovider /app/tests
Первый успешный полный прогон: 31 passed за 46.21s, включая startup.
Ранняя попытка до скачивания WebUI: 13 setup errors services not ready;
после завершения сборки прогон повторён. Warning — Starlette HTTPX deprecation.

Проверены реальные Chats.insert_new_chat, мигрированная webui.db и dual-write
chat_message. SQL dump всех таблиц читается через read-only mount, не ASGI-макет.

- MASK canary отсутствует в SQL dump, маска присутствует.
- Mock получает только маску, не исходный canary.
- Reveal восстанавливает ответ, после него canary по-прежнему отсутствует в БД.
- Неверный user scope Vault не восстанавливает данные.
- BLOCK не меняет SQL dump.
- Выход leak маскируется; injection BLOCK, error, timeout не сохраняются.
- LiteLLM models и completions работают, normal/echo/template проверены.
- stream=true отклоняется; промпт не меняет сценарий; без ключа Mock отказывает.
- Admission tamper, content substitution, expiry, replay отвергаются.
- Прямые create/import/completion/edit/messages/files/socket/query-bypass закрыты.
- Все 16 исходных unit tests барьера сохранены и проходят.

Дополнительно выполненные fault-команды:
DETECTOR_FAILURE=1 → POST /chat: 503;
остановленный Gateway → прямой POST /api/v1/chats/new в WebUI: 403.
Gateway восстановлен, полный прогон повторён успешно.
Браузерный GET 127.0.0.1:8088: 200.
В docker compose logs --no-color не найден SYNTHETIC_PII_.
Это проверка текущих логов, не полный аудит всех возможных логгеров.

Не завершено: штатный Svelte UI (заменён минимальным Gateway UI), многоходовый
чат, поддержка edit/history/resend (они блокируются), multi-user IAM, реальный
NER/DLP, промышленное шифрование. Нет browser automation, forensic sweep
свободных страниц/WAL и автоматического Vault TTL expiry теста. Fault-команды
пока не оформлены единым pytest workflow. Ограничения описаны в README.
Главный canary-критерий подтверждён для поддержанного узкого synthetic-среза,
но не для произвольных реальных ПДн или всех функций штатного Open WebUI.

Финальный прогон после исправления healthcheck: 31 passed, 1 warning in 34.99s.
Все пять сервисов Up, Protected WebUI healthy.
