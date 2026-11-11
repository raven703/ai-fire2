# Итерация 3 — выполненные проверки и границы результата

Дата: 2026-11-11. Каталог: `/home/user/ai-fire2`. Только синтетические ПДн.
Настоящих, внешних или облачных LLM нет: LiteLLM → FastAPI Mock LLM.

## Статус относительно запроса

Работает многоходовый диалог через собранный SvelteKit frontend, обслуживаемый
Protected Open WebUI v0.13.3. Временный HTML-интерфейс Gateway удалён, наружу
опубликован только Open WebUI: `http://127.0.0.1:8088/`.

**Существенное отклонение:** это ограниченная защищённая редакция интерфейса,
а не сохранённый почти без изменений штатный Chat.svelte. Заменены большие
Chat/MessageInput/Messages/Navbar/Sidebar и boot-layout компоненты. Используются
upstream SvelteKit, маршруты `/`, `/c/[id]`, стили, branding, Textarea, Spinner
и иконки. Неподдерживаемые routes удалены из frontend-сборки. Таким образом,
функциональный/security критерий поддержанного многоходового чата выполнен,
но требование «исходный интерфейс с минимальными изменениями» выполнено лишь
частично. Не объявлять эту работу полной интеграцией всех штатных UI-компонентов.

## Что реализовано

- Два синтетических пользователя: USER_KEY → synthetic-user, USER_B_KEY → synthetic-bob.
- Ключ вводится в password-поле, затем очищается. Непрогнозируемая HttpOnly,
  SameSite=Strict session cookie; серверные сессии в RAM, TTL 1 час. Нет persistent
  cookie Max-Age. Origin обязателен на всех браузерных POST, logout отзывает сессию.
- Браузер отправляет только новый text и необязательный chat_id. История, user,
  tools, stream, files в клиентском payload запрещены строгой схемой.
- История для inference берётся сервером из БД после проверки владельца;
  обязательный детектор проверяет новое сообщение, stored context и ответ модели.
- Admission HMAC/TTL/content/user/operation/policy сохранён; дополнительно подпись
  охватывает chat ID, create/append и hash базовой истории. Replay — SQLite UNIQUE.
  CAS и одиночный writer lock не позволяют устаревшему ответу затереть другой turn.
- Запись только после проверки обоих сообщений через настоящие `Chats` методы;
  обновляются chat JSON/history и chat_message. Неудачный inference/BLOCK не
  сохраняет даже входное сообщение. На чат максимум 20 пар сообщений.
- Vault стабилизирует token по user/chat/value до истечения TTL, при повторном
  store обновляет TTL. Другой user/chat получает иной token; copied token в чужом
  контексте не раскрывается. Vault не подключён к сети WebUI.
- View принимает только chat/message ID, читает каноническое сообщение после
  проверки владельца. Нет произвольного reveal-text API в браузере. Ответ no-store.
- TrustedText держит оригинал только в локальном состоянии листового компонента;
  не экспортирует его в историю/composer. Используется текстовая Svelte-интерполяция,
  без HTML/Markdown. При переходе/reload представление снова замаскировано.
- Существующий ProtectedIngress не изменён, неизвестные REST и все WebSocket
  по-прежнему закрыты. Разрешены лишь явные защищённые операции и bounded assets.
- Нет message/draft persistence, service worker, telemetry/socket bootstrap.
  Upstream branded app.html сохранён с заменой theme persistence на RAM.

## Реально выполнено

Сборка `docker compose build webui`: SvelteKit sync, Vite production build,
adapter-static, результат скопирован в `/app/build` реального образа Open WebUI.
Исходники берутся Git archive из commit b0e6098e940942281d9c83f3529ea117287a3a22,
не из изменённого vendor working tree. Проверяется применимость итогового патча
через git apply --check/apply на чистой базе и соответствие build input.

Полный workflow `/home/user/ai-fire2/scripts/verify-iteration3.sh` завершился:

| Фаза | Реальный результат |
|---|---|
| API/security/unit на Docker Compose | **54 passed**, 1 warning, 7.00s |
| Chromium, обычный сценарий | **1 passed, 1 skipped**, 6.51s |
| Обязательный detector failure | **503**, без admission/сохранения |
| Chromium, Gateway действительно остановлен | **1 passed, 1 skipped**, 11.55s |
| Canary sweep docker compose logs | **PASS**, SYNTHETIC_PII_ отсутствует |
| Финальный стенд | Пять сервисов Up, WebUI healthy |

Skipped означает вторую фазу в одном файле: normal не выполняется в outage-фазе
и наоборот. Это не пропуск обязательного outage-теста.

### Браузерный сценарий

Chromium запускается Playwright в отдельном Compose контейнере. Реально проверены:

1. Login, «Новый чат», ввод случайного synthetic canary через textarea.
2. Два маскированных сообщения и URL `/c/{id}`; mask в настоящей БД, original отсутствует.
3. «Показать оригинал» возвращает canary, не меняя БД.
4. Продолжение при видимом оригинале: intercepted HTTP содержит только новый
   text/chat_id; Mock получает 3 маскированных context messages, без canary.
5. Reload восстанавливает историю из БД только с масками. Повторный ввод того же
   canary в том же чате получает тот же token.
6. BLOCK объясняется пользователю; SQL dump до/после совпадает.
7. HTML-подобный текст после reveal остаётся текстом: нет img DOM и XSS execution.
8. Прямые REST writers, import, completion, files, retrieval, tools и query-bypass
   отвергаются даже при авторизованной браузерной сессии.
9. Второй browser context/Bob не читает, не продолжает и не раскрывает Alice chat;
   прямое открытие его URL показывает отказ.
10. Переход к новому чату и повторное открытие существующего восстанавливают 8
    маскированных сообщений, без display-only original.
11. При остановленном Gateway UI сообщает «не сохранено», сообщений нет, DB dump
    не меняется; после workflow Gateway восстановлен.
12. localStorage пуст; IndexedDB databases отсутствуют; CacheStorage/ServiceWorker
    не используются. В sessionStorage только sveltekit:scroll (координаты) и
    пустой sveltekit:snapshot. Canary нет в этих значениях и browser console.

SQL dump покрывает все таблицы реальной SQLite Open WebUI. Дополнительно читаются
все файлы webui-data, включая DB/WAL: raw canary отсутствует. Vault volume исключён
из запрета намеренно — там хранятся синтетические оригиналы по назначению.
Тестовые исходники содержат маркеры/генераторы canary, это не пользовательское хранилище.
Скриншот: `/home/user/ai-fire2/artifacts/iteration3-masked-chat.png` (только маски).
Логи контейнеров: `/home/user/ai-fire2/artifacts/iteration3-container.log`.

### Дополнительные API/security тесты

Все прежние 31 проверки сохранены/адаптированы к новому admission payload.
Добавлены multi-turn/token stability, user/chat isolation, copied token,
message ID ownership, history injection, stale admission CAS, synthetic Vault TTL
(изолированный in-memory Vault test), session/CSRF/logout, body limit, generic
exception без payload/log, прямые альтернативные endpoints, filesystem sweep.

### Промежуточные ошибки (исправлены, не скрыты)

- API: двойной Cache-Control; исправлен единственный no-store header.
- Browser: CacheStorage API отсутствовал на HTTP контейнерном origin; probe теперь
  явно учитывает отсутствие API, не объявляя его содержимое проверенным, когда API нет.
- Browser: ожидалось полностью пустое sessionStorage, но SvelteKit сохраняет scroll
  и пустой snapshot; тест проверяет разрешённые ключи и отсутствие canary.
- Patch generation: отсутствие final newline и stale overlay files делали patch
  неприменимым; подготовка теперь очищает собственный generated src и проверяет patch.
- После финальной пересборки session/CSRF тест стартовал до готовности WebUI
  (Connection refused); подключён тот же readiness fixture, что в integration suite.

## Известные ограничения

**Реальные ПДн запрещены.** SyntheticDetector понимает только SYNTHETIC_PII_ и
SYNTHETIC_BLOCK_ markers, не email/телефоны/NER. Vault plaintext SQLite, нет KMS,
промышленного шифрования/защищённого удаления. TTL не стирает старый original из
browser RAM, если пользователь уже авторизованно его увидел; кнопка hide/reload
удаляет это представление. Оригинал нельзя отозвать у уже увидевшего его человека.

Один uvicorn worker и lock; горизонтальный масштаб не поддержан. Два фиксированных
synthetic identities, нет полноценного IAM/password management/login rate limiting.
HTTP только loopback, cookie не Secure: для удалённого использования необходим TLS.
Процессы Gateway и WebUI доверенные; WebUI обладает admission key для verify, его
компрометация вне доказанного контракта. Нет защиты от root/Docker administrator,
malicious extensions/DevTools/user screenshots, swap/crash dumps, packet capture.
Проверка browser storage — live API в автоматизированном контексте, не forensic
проверка дискового профиля браузера. Проверка files ограничена webui-data, не всей ОС.

Неподдерживаемые функции отсутствуют в UI и закрыты сервером: документы, изображения,
RAG/search, streaming, MCP/tools, функции/плагины, n8n, внешние LLM, edit/delete/resend,
ветвление, import/export/share, workspace/admin/settings, realtime/WebSocket.
История ограничена 50 последними чатами и 20 turns/chat; persistence-чаты появляются
после первого успешного проверенного turn, пустой New chat — только RAM-состояние.
Нет полноценной mobile/accessibility/browser-matrix приёмки.

Предупреждения сборки upstream dependencies (deprecated npm packages и Svelte export
condition), Starlette HTTPX deprecation остаются; CVE/SBOM audit не выполнен.
Никакие данные проверок не доказывают пригодность для реальной конфиденциальной информации.