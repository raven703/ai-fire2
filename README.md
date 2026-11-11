# AI Firewall v2 — первая архитектурная итерация

Дата: 2026-11-11. **Не готово к эксплуатации. Только синтетические данные.**
Исходные требования: AI_Firewall_v2_Architecture.docx и AI_Firewall_v2_Cline_Prompt.md в корне.
Новый проект; код прошлых AI-Fire не использован.

## Что реализовано

Чистый ASGI ingress с ограниченным чтением тела, fail-closed и закрытием WebSocket;
локальный upstream Open WebUI v0.13.3, обёрнутый этим ingress без разрешающего inspector.
По умолчанию доступны только статусы `/health`, **не чат и не UI**.
Это намеренно закрытая сборка, а не работающий пользовательский POC.
Контракт admission: HMAC-SHA256, hash содержимого, пользователь, операция,
версия политики, случайный nonce, срок 30 секунд. Не интегрирован в upstream;
одноразовость и аутентификация ещё не реализованы.

## Проверки в PowerShell

```powershell
Set-Location 'C:\Personal\AI-Fire-2'
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\python.exe' -m compileall -q src tests
```

Для воспроизведения окружения: Python >=3.12, `python -m venv .venv`, затем
`.\.venv\Scripts\python.exe -m pip install -e '.[test]'`.
Тесты используют FastAPI-макет записи, **не реальную БД Open WebUI**.

Архитектура и угрозы: `C:\Personal\AI-Fire-2\docs\architecture.md`.
Отчёт: `C:\Personal\AI-Fire-2\docs\verification.md`.
Upstream исключён из git; воспроизводимый патч хранится отдельно.

## Следующая итерация

Аутентифицированный Privacy Gateway + обязательные Presidio/Natasha;
санитизация всех полей chat/history/title; реальная БД upstream и canary sweep;
Vault Postgres/AES-GCM/OpenBao и TTL; LiteLLM и buffered output scanning;
доверенное UI-only восстановление. Затем документы, RAG, политики и fault injection.
До этого никакие детекторы или интеграции не объявляются готовыми.