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