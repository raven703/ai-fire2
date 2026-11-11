# Проверки 2026-11-11

Среда Windows, Python 3.14.6. Интернет доступен: upstream получен по git.
Docker CLI отсутствует. LLM API и ключи не предоставлены.

Первый запуск: 16 passed, 1 warning, 1.26s.
compileall src/tests завершился без ошибок.
Повторный запуск после патча upstream: 16 passed, 1 warning, 4.46s.
compileall также проверил изменённый main.py upstream; git diff --check без ошибок.
Локальные metadata: FastAPI MIT, HTTPX BSD-3-Clause.
Предупреждение: Starlette TestClient объявил интеграцию httpx устаревающей;
тесты проходят, переход на иной клиент требует отдельной проверки зависимостей.

Покрыто: закрытый default, семь обходных URL, canary и порядок scan-before-write,
отказ детектора без утечки exception payload, malformed/oversize/extra fields,
scope/hash/signature/expiry/policy admission, отказ WebSocket.

НЕ проверено: запуск полной сборки Open WebUI, настоящая БД/история/экспорт,
Postgres/Redis/RAG/файлы/backup sweeps, браузерный e2e, Docker Compose,
Vault/KMS, русскоязычные NER precision/recall, LiteLLM и LLM, файлы/OCR/AV,
UI-only deanonymization. Первый срез — барьер и unit/ASGI tests, не полный
минимальный текстовый POC из задания и не выполнение всех девяти этапов.