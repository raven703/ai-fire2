# Layout autosave correction — November 11, 2026

User screenshot exposed an unsupported POST /chats/{id}/view autosave after
successful turns. Original panel API now keeps auxiliary layout in a module
memory Map only; it sends no layout HTTP requests and uses no browser storage.
Layout intentionally resets after reload; committed conversation history does
not. Server POST /view remains denied. Removed the unused network helper to
avoid accidentally reintroducing layout persistence with unchecked labels or
prompts. Original panel components are unchanged.

Rebuilt source image with BuildKit/watchdog: exit 0, no watchdog stop. Recreated
native webui from that image. Chromium: 4 passed, 1 skipped (explicit outage
test); includes two turns, reload and assertions that no POST /view occurs and
the layout warning is absent. Regression: 84 passed, 1 skipped, existing warning.
Evidence: native-layout-build.log, native-layout-browser.log,
native-layout-regression.log. Both native and POC services restarted after build.

# Native HTTP/UI integration verification — November 11, 2026

The original source-built UI is running on 127.0.0.1:8089. Deploy with
`docker compose -f compose.native.yaml -f compose.native-core.yaml up -d`.
The explicit overlay enables only the protected text contract. The base
configuration still defaults to closed content. POC remains at port 8088;
its services were temporarily stopped for build memory and restarted. No
volumes removed or history rewritten; all inputs were synthetic.

Implemented authenticated native text completion/read/list/model-discovery
routes using upstream get_verified_user and chat-creation permission checks.
Routes are ordered ahead of the upstream SPA mount. Chat.svelte sends only
one new message, IDs and revision; history is reconstructed server-side.
The original composer, messages, navbar and sidebar remain in place.
Chat.svelte adopts canonical committed state, never inserts raw optimistic
messages, and restores protected history on reload. Existing RAM-only draft
handling remains. Unsupported REST writes, Socket.IO and WebSocket are denied.
Unsupported capability discovery returns empty lists without invoking upstream
writers. Auxiliary chat view returns null, never reads/writes saved view data.

SQLite triggers now enforce the protected write callback for INSERT/UPDATE/
DELETE on chat and chat_message. Connection callbacks are initialized before
upstream reconciliation tasks start. Exact-row permitted ORM flush enables
the connection gate only for its flush and closes it afterwards. Disposable
tests verified raw sqlite3 and direct AsyncEngine SQL UPDATE denial, as well
as successful protected writes. This is an application boundary, not protection
against an administrator modifying the database schema or application code.

Source build completed with the 6144 MiB heap and watchdog. One intermediate
build was cancelled by the watchdog at 877 MiB available; retry succeeded.
Starting threshold adjusted from 7168 to 7040 MiB after stopping services;
runtime cancellation thresholds were not relaxed. Final backend-only rebuild
reused the successful frontend BuildKit layer. The running container was
recreated from the final image (no remaining docker-cp-only deployment).

Chromium final run: 4 passed, 1 skipped, exercising original login, PII MASK,
two turns, displayed history after reload, BLOCK, denied alternative APIs,
Mock request capture (masked three-message model history), browser local/
session storage and database dump canary checks, model failure retaining
one clean input, output BLOCK retaining one clean input, and output MASK.
Gateway outage was separately injected by stopping its container: 1 passed.
The skipped browser test is that same explicit-outage test in the normal run.
Browser foreign-user check rejects a pending identity (401); verified-user
ownership isolation is separately covered by real-model append tests, not
claimed as a two-verified-user Chromium test.

Final full regression: 84 passed, 1 skipped (SQLAlchemy absent in that image),
one existing warning. The actual-model source-image script separately passed
with live Gateway/Vault/LiteLLM/Mock and trigger enforcement. Existing permit
tests cover durable replay and transactional rollback; a full native-create
HTTP receipt replay is not exposed because clients never receive writer tokens.
Native log sweep found no SYNTHETIC_PII_TEST_, SYNTHETIC_PII_OUTPUT_CANARY or
SYNTHETIC_BLOCK_BROWSER in collected webui/gateway/litellm/mock logs. WebSocket
publication is disabled; synchronous canonical HTTP is the only output path.

Evidence (ignored): native-final-browser.log, native-gateway-outage-e2e.log,
native-final-models.log, native-final-regression.log, native-final-services.log,
native-chat-history.png, native-build-6144-controlled.log and memory CSV.

Limits: text-only, mock-only, nonstream, SQLite-only, no attachments/tools,
edits/deletes/regeneration/background tasks. Fault coverage includes output
BLOCK, not an output-phase-only Gateway transport outage. Browser storage
checks cover localStorage/sessionStorage; IndexedDB/CacheStorage were not
independently enumerated. These remaining acceptance gaps must not be described
as tested. Earlier entries below are historical checkpoints, not current state.

# Native append/completion verification — November 11, 2026

Added non-public `ai_firewall.native_lifecycle` server operations. Append takes
SQLite BEGIN IMMEDIATE before ownership and revision reads, validates the
parent/current tip, checks its ChatMessage mirror, rejects reused message IDs,
inspects content, then commits Chat JSON, ChatMessage and the exact-row permit
nonce together. Assistant content uses output inspection. Canonical results
are returned only after commit. No HTTP endpoint or events added.

Nonce table initialization now occurs inside the real write transaction before
consumption. The disposable verification no longer provisions that table.
Existing standalone replay/rollback tests remain in the regression suite;
replay against the actual native ORM create path is still not covered.

Added a nonstream completion helper that reconstructs the committed parent
chain (bounded, cycle checked), inspects all model-bound content, calls native
LiteLLM -> Mock LLM, and routes the full assistant output through output DLP
and locked append. Model/provider failures return generic errors; they do not
remove previously committed clean input. Completion is NOT wired into the
upstream HTTP lifecycle or Chat.svelte yet.

Executed the extended disposable real-model script with live Gateway/Vault
and newly started separate native LiteLLM/Mock services: create MASK,
assistant MASK, user continuation MASK, stale revision denial, foreign-user
denial, actual LiteLLM completion persisted, BLOCK append denial, create
BLOCK/outage rollback, and SQLite dump checks for the three raw canaries all
passed. The complete sequence persisted four ChatMessage rows and four nonces.
This is a server-helper integration test, NOT original-UI E2E. No claim that
the Mock request capture was inspected or output detector failure injected.

Final regression run with fork mounted: 84 passed, 1 skipped, one existing
deprecation warning. Python compilation and diff checks passed. Earlier run
without the fork mount had seven additional skips and was not the final run.

Still unresolved: direct SQL bypass protection, lifecycle HTTP wiring,
Chat.svelte canonical synchronization, Chromium chat/history/failure tests,
event/log/browser-storage sweeps. Native content API and WebSocket remain
closed. Changes are not deployed into the running native webui. POC untouched.

# Atomic native creation verification — November 11, 2026

Implemented initial Chat + ChatMessage staging and one commit in upstream
`Chats.insert_new_chat`. Message staging errors now roll back and propagate,
rather than leaving a committed Chat. Protected creation acquires SQLite
BEGIN IMMEDIATE before checking that the UUID is absent. Existing UUIDs are
rejected without revealing the owner. Caller transactions without a real
SQLite transaction fail closed. Only SQLite is supported.

The complete incoming chat document is inspected by the live Gateway before
constructing either ORM representation; the canonical sanitized document is
returned to the caller. Scalar ORM defaults are resolved before the exact-row
admission snapshot. Callable defaults fail closed. Pending rows must match
both the operation's user and chat scope. The final ALLOW receipt covers both
tables; its nonce is consumed inside the same transaction as their flush.

Executed `scripts/verify-native-atomic-create.py` in a disposable source-image
container with actual upstream models and AsyncSession/aiosqlite, mounting
the changed source. The production inspector factory was injected without
importing unrelated application modules; chat creation permission lookup was
bypassed for the synthetic user. Gateway HTTP and Vault were real, not mocked.
Verified MASK of raw input through the actual create method, canonical return,
one Chat + one ChatMessage + one nonce committed, BLOCK and connection-outage
rollback, rejection of duplicate UUID from another user, and absence of raw
canary in the disposable database dump. No production-volume writes performed.

Live authenticated batch verification also passed. Regression suite:
84 passed, 1 skipped (SQLAlchemy unavailable in that test image); the separate
source-image model test above did exercise SQLAlchemy. No new Chromium chat
acceptance run. Results: `artifacts/native-atomic-create.log` and
`artifacts/native-atomic-regression.log` (ignored).

NOT accepted: direct-engine SQL bypass protection, alternative writer coverage,
update revision locking, completion wiring, multi-turn Chromium, browser/log
canary sweeps. The nonce table is provisioned explicitly by the disposable
test, not yet by native startup. Native content routes remain CLOSED; this
change must not be deployed as completed protected chat. No compensating
write mechanism is used: unsupported writes remain denied at the ORM boundary,
and the outer route barrier remains required because it does not yet protect
direct engine SQL.

# Native Integration Core — промежуточная реализация, НЕ принят

## Реальная модель и AsyncSession после b1c13cd

scripts/verify-native-model-writer.py выполнен внутри source image с настоящей
моделью open_webui.models.chats.Chat, AsyncSession и aiosqlite на отдельной
disposable SQLite. Исправлен DBAPI adapter: execute через cursor адаптированного
соединения; прежний синхронный-only вызов не считался подтверждённым для async.
Проверены отказ raw flush и commit реальной Chat row вместе с nonce.

Добавлен inspected_flush: точный snapshot ожидающих ORM rows проходит через
NativeInspector с проверенным Gateway receipt; writer требует ALLOW и неизменный
snapshot, residual MASK отклоняется. Реальный AsyncSession flush этим путём
проверен с HTTP MockTransport (НЕ живой Gateway), затем commit и два nonce/две
строки проверены реальным SQL. Native client/permit suite: 14 passed.

Это всё ещё НЕ рабочий native chat. inspected_flush не вставлен в штатные
insert_new_chat/_chat_transaction: в insert_new_chat обнаружен отдельный commit
Chat до dual-write ChatMessage, а writers также имеют собственные commit paths.
Для безопасного включения нужно объединить initial dual-write в одну транзакцию,
обработать defaults до snapshot, вычислять revision под блокировкой, закрыть
direct engine SQL и только затем разрешить lifecycle. Socket.IO/UI completion
ещё не включены, нового Chromium chat результата нет. Staging не изменялся.

## Writer boundary: следующий частичный шаг после 58bdad1

Добавлен native_writer.py и регистрация SQLAlchemy Session events в native
runtime. before_flush охватывает ORM writes таблиц chat/chat_message независимо
от вызывающего REST/socket/internal handler. do_orm_execute отклоняет bulk DML
этих таблиц. Без backend-only exact-column permit flush запрещён. Permit связывает
полный JSON snapshot строк с signed payload; nonce потребляется через DBAPI
соединение текущей транзакции, а не отдельную SQLite connection.

Проверено в контейнере с SQLAlchemy 2.0.38 и реальной SQLite: missing permit,
вторая мутация после consume, rollback nonce+content, запрет bulk insert,
успешный flush+commit с durable nonce. Writer test: 1 passed; совместный запуск
writer+permit: 5 passed (до добавления positive commit assertion, после него
writer повторно passed). py_compile и diff --check прошли.

Ограничения: это ещё не завершённая интеграция. Native lifecycle пока не выдаёт
writer permits; AsyncSession/aiosqlite adapter и реальные Open WebUI model rows
требуют отдельных тестов. Direct engine SQL не охвачен ORM events. Revision
передаётся writer-адаптером и должна вычисляться из заблокированной строки, а не
браться из request. Все content endpoints по-прежнему закрыты. Изменение runtime
в исходниках ещё не развёрнуто в работающем image, staging не перезапускался.
Нового native chat Chromium или полного 84-test прогона в этом шаге нет.

## Успешная source build с heap 6144 MiB

- По запросу владельца NODE_OPTIONS=--max-old-space-size=6144 установлен только
  в frontend stage. Runtime stage не наследует NODE_OPTIONS.
- Одна guarded build: exit=0, watchdog_stop=False. Min MemAvailable=1712 MiB,
  max swap used=1 MiB. Параллельных тяжёлых задач/Chromium не было. npm cache
  mount и Docker BuildKit cache сохранены. Лог native-build-6144-controlled.log.
- Собран ai-fire2-native:source, manifest digest
  sha256:54ed89b04857de97970984e975140342e1582f678a23a6f796dc9647dfbdb813.
- Запущен именно source image с оригинальными компонентами; fallback staging
  image больше не используется работающим native WebUI.
- Все 64 language static assets присутствуют в image и byte-identical source.
  Все 64 HTTP paths возвращают JSON 200. Chromium проверил locale en-US -> ru-RU
  -> en-US через штатную browser locale preference с reload, включая html lang
  и текст оригинальной login-кнопки; pageerrors отсутствуют. Live Settings dropdown
  пока не проверен (content/settings mutations остаются закрытыми).
- Original source UI/auth Chromium + locale test: **2 passed**, 8.66s.
  Проверка штатного signin, запрета content API, DB/browser canary также прошла.
- Полный контейнерный регрессионный suite: **84 passed**, 1 warning, 11.67s.
- Сохранённый POC восстановлен через start, WebUI healthy. Volumes не удалялись.

Оптимизация словарей сохранена: указанные static paths и browser reload locale
работают. Её вклад в устранение OOM отдельно не измерен — heap одновременно
увеличен. Это не основание заявлять, что она одна исправила OOM.

Главная граница неизменна: source build/UI/auth теперь реально работают, но
Native Integration Core ещё НЕ готов. Native content endpoints закрыты;
transaction permit к штатным writers, Socket.IO и canonical frontend echo,
native LiteLLM/Mock multi-turn chat и полный security E2E предстоит реализовать.

## Возобновление с 10 GiB WSL

Проверено: MemTotal=9948 MiB, swap=2048 MiB; оба checkout были чистыми на
b01fd8f / 46c76a3b1. Контейнеры после перезапуска WSL не работали.
Выполнена одна guarded source build с NODE_OPTIONS=4096 и прежним watchdog.
Подтверждены Docker CACHED npm/source layers; SSR build прошёл (1837 modules),
затем запущен client build. На ~167s client/build process сообщил V8 heap
exhaustion (live heap около 4007 MiB). Watchdog отменил собственный build.
Минимум MemAvailable за попытку 3235 MiB, swap used=0: это V8 heap limit,
а не нехватка общей RAM. Увеличение WSL до 10 GiB устранило предыдущий
host-pressure blocker, но source build по-прежнему НЕ готова.

Исследование graph: динамический import включает 64 translation dictionaries,
суммарно 23174950 bytes JSON. Подготовлена экспериментальная оптимизация:
копирование неизменённых словарей как static assets и загрузка через same-origin
fetch с whitelist language codes. Все 64 словаря существуют. Компоненты UI и
переводы не заменены/не удалены. Это кандидат оптимизации, НЕ доказанная причина
OOM: размер JSON не равен размеру V8 graph. Повторная тяжёлая сборка не запущена.
Нужны проверка static-copy destination, сборка и browser language switching;
до этого оптимизация не принята. Ограничение Node 4096 не повышалось.

В этом возобновлении выполнены только diff --check и source/dictionary checks;
новых unit/Chromium результатов нет. Native content barrier не открыт.

## Контролируемая попытка 4096 MiB (после ba475bc / 46c76a3b1)

- Обе рабочие ветки были чистыми; история и volumes сохранены.
- Фактический WSL MemTotal: 7944 MiB, swap 2048 MiB; cgroup memory/swap max
  не задают дополнительного ограничения. До остановки проектных сервисов
  MemAvailable ~3348 MiB; после остановки ~5283 MiB.
- NODE_OPTIONS в Docker frontend stage увеличен до 4096 MiB по запросу владельца.
  Windows .wslconfig не изменялся.
- Проверен BuildKit v0.31.1 (docker driver), существующий cache ~16.92 GB сохранён.
  Добавлен persistent locked npm cache mount ai-fire2-native-npm и prefer-offline.
  npm ci успешно завершился за 271.7s; package/source слои разделены; в журнале
  подтверждены CACHED layers. Повторный запуск ради проверки cache не выполнялся.
- Выполнена ровно ОДНА сборка с новым heap; параллельных сборок/Chromium не было.
  Контейнеры двух проектных контуров временно stop, затем start через EXIT trap.
- Watchdog отменил build через ~422s: MemAvailable=1020 MiB, swap used=71 MiB.
  За 212 samples min available=1020 MiB, max swap=71 MiB. Exit watchdog=75,
  docker cancellation=130. V8 OOM в этой попытке НЕ зафиксирован: сработал
  упреждающий RAM threshold. Build/source image НЕ готовы.
- Конкретное препятствие: нет безопасного запаса общей RAM при 4096 MiB heap
  и текущем WSL/IDE окружении. Следующая попытка требует изменения ресурсных
  условий; владельцу предложено увеличить WSL RAM до 10 GiB. Агент настройки
  Windows не менял и сборку повторно не запускал.
- Сохранены метрики artifacts/native-build-memory.csv и журнал
  artifacts/native-build-4096-controlled.log (ignored, не коммитятся).
- Проверки py_compile и git diff --check прошли. Новых результатов native chat
  нет; прежние 84 tests и Chromium результаты ниже не выдаются за новый прогон.
- Native content barrier не ослаблен; permit/writer integration не объявлена
  готовой. Следующий этап после source build — реальная writer/event integration.

## Продолжение после восстановления WSL (2026-11-11)

- Сохранены обе текущие ветки, незавершённые изменения и Docker volumes.
  Остановленные после WSL POC/native staging контейнеры запущены через start,
  без пересоздания volumes или публикации в remote.
- В frontend build stage установлен NODE_OPTIONS=--max-old-space-size=3072;
  CLI override 5632 удалён. Сборки выполнялись последовательно, без Chromium.
- scripts/build-native-safe.py: эксклюзивный lock, проверка стартового запаса
  RAM, мониторинг каждые 2 секунды, отмена собственного build при MemAvailable
  <1024 MiB, swap used >768 MiB или Node FATAL ERROR. Метрики в ignored artifacts.
- Обе попытки 3072 MiB завершились heap exhaustion, не успешной сборкой.
  Вторая (без tree shaking, maxParallelFileOps=8) отменена watchdog; на последних
  отсчётах оставалось 1830 MiB available, swap ~1 MiB. Лимит не повышался.
  Последняя Rollup-настройка экспериментальная, не доказала успешную сборку.
- Добавлен native_permit.py: проверка exact admission + revision и persistent
  nonce в той же SQLite-транзакции, что content write. Тесты на настоящей SQLite
  проверяют replay после reopen, совместный rollback и stale revision zero-write.
  Примитив ещё НЕ подключён к SQLAlchemy writers Open WebUI.
- Контейнерный полный suite: **84 passed**, 1 warning, 11.60s.
- POC Chromium: **1 passed, 1 skipped**, 7.82s.
- Original UI/auth staging Chromium: **1 passed**, 3.28s.
- Live authenticated Gateway batch повторно прошёл auth/BLOCK/REVIEW/nested/MASK.
- Source frontend build и native chat по-прежнему НЕ приняты. LiteLLM/Mock
  работают только в сохранённом POC; native content barrier остаётся закрытым.

Git checkout fork сейчас shallow (upstream commit отмечен grafted). Имеющиеся
объекты/коммиты не удалялись; для полного исторического анализа потребуется
отдельное безопасное fetch --unshallow upstream, не reset/reclone.

Дата: 2026-11-11. Synthetic-only. Не production-ready.

## Реализовано

- Native authenticated batch inspection `/native/inspect`; доверенный service
  credential отделён от native пользовательских паролей и сессий.
- Полный анализ всех batch fields до первой Vault-записи; BLOCK/REVIEW отклоняются.
- Canonical receipt связывает очищенные поля с user UUID, chat UUID, operation,
  revision, TTL, policy и nonce. Backend client проверяет подпись и точный scope.
- Vault поддерживает native UUID identity наряду с неизменённым POC scope.
- В оригинальном backend добавлены staged hooks: completion до bootstrap,
  проверка модельного контекста перед handler и output до response middleware
  logging/events/writes. Произвольные вложенные поля не допускаются.
- Оригинальный Chat.svelte: non-stream; saveDraft больше не записывает composer
  в sessionStorage. Остальные native компоненты не заменены.
- Независимые Compose volumes/network/порт 8089, Gateway и Vault. POC не удалён.
- Внешний staging ASGI разрешает только original UI/assets, native auth и минимум
  read endpoints; все content APIs и WebSocket закрыты. Даже development flag
  completion не отключает этот барьер.
- Исходные frontend builds: sourcemap выключен, минификация выключена для снижения
  памяти WSL. Это не замена компонентов. Docker context исключает secrets и .git.
- Отдельный Dockerfile.native-staging использует оригинальный UI pinned image
  для независимой проверки auth. Он НЕ доказывает сборку изменённого frontend.

## Проверено

- Контейнерный suite с mounted fork hooks: **80 passed**, 1 upstream warning.
  Включает 54 прежних теста и 26 новых. Native hooks тестируются с injected storage,
  их нельзя считать real-native-chat DB acceptance.
- Живой Gateway + настоящий Vault SQLite: service auth, nested JSON denial,
  ALLOW/MASK, BLOCK, REVIEW. Записи denied canaries в Vault отсутствуют.
- Живой обязательный detector failure: HTTP 503; normal Gateway восстановлен.
- Native Chromium staging: **1 passed** — оригинальная форма signin, штатный
  token, запрет content APIs; canary/пароль отсутствуют в native WebUI DB dump и
  проверенных browser local/session storage. Снимок artifacts/native-auth-staging.png.
- POC Chromium повторный прогон: **1 passed, 1 skipped**. Первый прогон под
  memory pressure упал на navigation timeout; повтор без build pressure прошёл.
- Native container log sweep: raw synthetic markers не найдены.
- compileall, Compose config, diff --check и fork provenance check прошли.

## Сборка и фактический runtime

Первая original source frontend build: Node heap exhaustion (4096 MiB).
Попытки без sourcemap и без минификации также достигли heap/memory pressure;
остановлены только собственные build jobs, не POC services.
Следующая попытка с heap 5632 MiB записывается в artifacts/native-build-5632.log.
Статус этой попытки следует проверить перед дальнейшим развёртыванием.

Запущенный staging image: ai-fire2-native:staging. Он использует pinned original
UI image, а не новый frontend build. Основной compose image ai-fire2-native:source
отделён от staging. Для воспроизведения staging использовать оба compose файла:
compose.native.yaml + compose.native-staging.yaml. Содержимое чатов недоступно.

## Не реализовано / не проверено

Native многоходовый chat, reload history, LiteLLM/Mock wiring в native compose,
writer permits/atomic replay consume/CAS, server canonical echo в original frontend,
Socket.IO allowlist и display-only reveal НЕ закончены. Внутренние SQL writers
не объявляются защищёнными — поэтому content runtime остаётся закрытым.
Нет native chat E2E для LLM error/output DLP failure/Gateway outage/user isolation.
Нет полной filesystem/browser IndexedDB sweep native chat, поскольку чат не открыт.
Подпись admission сама по себе не предотвращает replay: nonce consume предстоит.
Original draft restore paths требуют дальнейшего review; staging UI взят из image
и не содержит source draft fix, но сервер не допускает создание чатов.

Пароль staging synthetic test identity находится только в ignored artifacts с
mode 0600; не добавляется в Git. Первый native admin создан штатным upstream
bootstrap; остальные signup имеют pending role. Signup enabled локально для
staging тестирования. Это не production provisioning.

## Следующий кодовый шаг

Довести source build; подключить scoped writer permits на реальных transaction
boundaries; закрыть все остальные REST/events/internal writers; безопасно открыть
native completion и chat reads с original Socket.IO либо synchronous UI lifecycle.
Затем native canonical echo, Litellm/Mock и полный Chromium/DB/outage suite.
Не включать FIREWALL_NATIVE_CORE_ACCEPTED до завершения этих контролей.