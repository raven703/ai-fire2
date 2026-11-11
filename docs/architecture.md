# ADR-001: закрытый архитектурный срез

## Выбор upstream

Open WebUI v0.13.3, commit b0e6098e940942281d9c83f3529ea117287a3a22.
Это фиксированная база исследования, не утверждение о последней или безопасной версии.
Сначала требуется аудит зависимостей и CVE; фиксирование версии не заменяет аудит.
Сохранить LICENSE, LICENSE_HISTORY и брендинг. LICENSE содержит дополнительное
ограничение на брендинг; не считать этот компонент безусловно свободным ПО.
FastAPI: MIT; HTTPX: BSD-3-Clause, проверено по локальным метаданным установленных пакетов.
Полный SBOM и лицензии транзитивных зависимостей нужны перед релизом.
Остальные целевые компоненты пока не выбраны/не установлены; лицензионная приёмка
Presidio, Natasha, LiteLLM, OpenBao, ClamAV, YARA-X, OCR и их моделей — открытая задача.

## Реальные точки сохранения

Пути ниже относительно `C:\Personal\AI-Fire-2\vendor\open-webui`.

| Исходник / символ | Риск BEFORE проверки | Решение текущего среза |
|---|---|---|
| backend/open_webui/routers/chats.py:850 create_new_chat, :865 insert_new_chat | JSON чата и title в БД, затем событие с title | закрыто |
| тот же файл :884 import_chats, :896 Chats.import_chats | пакетный импорт истории | закрыто |
| тот же файл update_chat, share, tags, folder | редактирование и метаданные вне completion | закрыто |
| backend/open_webui/utils/middleware.py:2456 upsert_message_to_chat_by_id_and_message_id | отдельные записи в обработке сообщений | completion закрыт |
| backend/open_webui/utils/middleware.py save_response_stream и ENABLE_REALTIME_CHAT_SAVE | streaming/cache до финального контроля | закрыто |
| backend/open_webui/routers/files.py upload_file / insert_new_file | файловый том и метаданные | закрыто |
| backend/open_webui/routers/retrieval.py save_docs_to_vector_db / process/files/batch | embedding API и векторная БД | закрыто |
| socket.io / WebSocket | обход HTTP middleware | все WebSocket закрыты |

Это начальная карта, **не полный аудит всех writers**. Нет заявления о доказанной
безопасности фоновых задач, startup, внутренних вызовов или логов всего upstream.
Filter Function не используется как граница безопасности. Патч ставит outer ASGI
barrier после регистрации маршрутов; запуск альтернативного ASGI entrypoint запрещён.
Отсутствие пакета ai_firewall приводит к ошибке старта, не обходу.

## Целевой поток и границы

```text
Браузер -> trusted ingress (raw только RAM) -> Privacy Gateway / детекторы / политика
   -> Vault API -> отдельный Postgres (AEAD, scope, TTL; ключи OpenBao)
   -> sanitized JSON + admission -> Protected Open WebUI -> sanitized DB
   -> Security Gateway -> LiteLLM -> существующая LLM
   -> buffered output scan -> sanitized DB -> UI
Авторизованный trusted view -> Vault API -> восстановленная копия только для просмотра
```

Vault DB/ключи не доступны Open WebUI/LiteLLM. Нужны отдельные сети ingress,
inspection, inference, vault-data, kms; только Vault API соединяет vault-data и kms.
Compose не создаётся с фиктивно работающими сервисами: Docker отсутствует, сервисы
и лицензии ещё не прошли выбор/проверку. До реальных данных нужны HTTPS и auth.

## Угрозы и тесты

Direct API/import/upload/edit: default deny; неизвестный endpoint также deny.
Скрытые поля и большой JSON: строгая ограниченная тестовая схема и лимит тела.
Detector timeout/error: отказ без payload в логах; реальный timeout ещё нужен.
Token tamper/scope/TTL/policy drift: unit tests. Replay остаётся риском: nonce
сам по себе не обеспечивает одноразовость; потребуется атомарное consume-хранилище.
Сырые ответы, streaming, files, tools, RAG: заблокированы, не реализованы.
DoS slow body, Unicode/NER обходы, malicious JSON и разрешённый произвольный текст:
требуют дополнительных контролей. Тестовый inspector нельзя использовать в production.

## Структура

src/ai_firewall — ingress и admission; tests — изолированное доказательство порядка;
docs — ADR/threat model/проверки; patches — патч контролируемого upstream;
vendor/open-webui — локальный checkout, не код прошлой системы.