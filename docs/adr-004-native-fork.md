# ADR-004: отдельный защищённый fork, без замены upstream UI

Статус: принято для подготовки; Native Integration Core ещё не разрешён к эксплуатации.
Дата: 2026-11-11.

## Сохранение контрольной реализации

Контрольный POC находится в commit eab205a основного репозитория. Его compose.yaml,
frontend overlay, Python services и security tests остаются без изменений.
Работающий ai-fire2-poc не заменяется native-контуром. Отчёт iteration-3-verification.md
относится только к этому POC, не к native fork.

## Происхождение и структура

Основной проект: ветка development/protected-openwebui.
Полноценный вложенный независимый Git checkout: /home/user/ai-fire2/forks/open-webui.
Ветка fork: firewall/native-core. База: b0e6098e940942281d9c83f3529ea117287a3a22.
Git objects скопированы из локального официального vendor repository, без его dirty
working tree. Сохранены история, LICENSE, LICENSE_HISTORY и branding.
upstream remote указывает на https://github.com/open-webui/open-webui.git;
push URL отключён. Ничего не опубликовано. forks/ исключён из основного Git;
воспроизводимость задаётся manifest и проверками, будущие изменения — отдельными
коммитами fork и экспортируемой patch series, не незаписанным ignored checkout.

## Границы первой реализации

Identity fields штатной auth разрешены. Пароли и auth tokens не идут в DLP/Vault.
Очищенный вход может сохраняться при отказе LLM. BLOCK/REVIEW не сохраняются.
Оригинальные Chat, MessageInput, Messages, Sidebar, Navbar, Auth, Settings остаются.
Непроверенные функции блокируются сервером, не удаляются из исходников.

## План Native Integration Core по конкретным точкам

1. backend/open_webui/main.py: chat_completion до metadata processing, создания
   chat/turn, publish_event и background tasks. Identity из get_verified_user;
   ownership до Vault; строгая схема, canonical sanitized copies user_message,
   messages, params и metadata. Не доверять model_item.direct.
2. backend/open_webui/routers/chats.py: create_new_chat, update_chat, rename и
   отдельные message mutations. Сначала DLP/permit, затем штатные Chats methods.
   Import/share/export/fork/compact и неподдержанные mutations временно deny.
3. backend/open_webui/models/chats.py и chat_messages.py: перечислить все callers
   insert/update/upsert/edit_message_output. Content writes требуют scope-bound
   permit; consume и запись должны быть атомарны либо иметь recovery/idempotency.
   Один ContextVar-флаг без привязки к конкретному содержимому недостаточен.
4. backend/open_webui/utils/middleware.py: buffered non-stream output scan до
   non_streaming_chat_response_handler и любых output events/writes. Запретить
   streaming, tools, background title/tag/follow-up generation до их приёмки.
5. backend/open_webui/socket/main.py: разделить транспортные события и content
   events; внутренний event_emitter также writer. Не открывать Socket.IO целиком.
6. src/lib/components/chat/Chat.svelte: отключить saveDraft persistence и restore,
   сохранить RAM composer; non-stream requests; заменить локальный raw message
   canonical server message до autosave/continuation. Проверить queued messages.
7. src/lib/components/chat/Messages/*: изолированный leaf-only text reveal по
   chat/message/revision, без mutation history/edit buffer/Markdown interpolation.
8. backend/open_webui/routers/users.py: whitelist структурированных UI settings;
   свободный текст/system/variables — DLP или deny. Сохранять штатную auth.
9. routers/files.py и retrieval.py: deny до multipart parsing/tempfile/storage и
   embedding. Позже отдельный trusted ingestion, не DLP после Storage.upload_file.
10. routers/chats.py search + frontend API: поиск по masked history; raw query не
    должен попадать в URL/access logs. Rename проходит DLP; delete scope-checked.

Общий Python security adapter живёт отдельно от upstream business logic. Gateway
получает authenticated context от backend, а не USER_KEY fixed identities или
user_id из браузера. Существующий POC protocol нельзя без изменений использовать:
он допускает только два фиксированных пользователя.

## Privacy Gateway contract (следующий независимый шаг)

Отдельный authenticated batch inspect endpoint: user/chat/operation/schema/version,
перечень типизированных text fields. Полный анализ всех полей и итоговый verdict
предшествуют любому Vault store. BLOCK/REVIEW — zero Vault writes. Затем MASK и
admission exact canonical payload; nonce, TTL, policy version, operation, identity,
chat revision. Gateway не получает auth passwords. Ошибка обязательного детектора,
policy engine или Vault — fail-closed. Сначала synthetic-only.

## Решение по включению

Чистый upstream НЕ является защищённым стендом: его не запускать с доступными
content endpoints до реализации core. Подготовка/сборка не означает приёмку B.
До завершения A и проверок B остаётся рабочим только контрольный POC.

## Обновления

fetch upstream без merge в рабочую ветку; новая upgrade branch; review diff writers,
events, browser storage и egress; merge/rebase только после review. Полный security
suite и native Chromium acceptance обязательны. Конфликт нельзя решать удалением
security hooks. Сохранять upstream лицензии/branding и проверять их изменения.