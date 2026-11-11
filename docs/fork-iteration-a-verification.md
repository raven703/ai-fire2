# Fork A: подготовка, не завершённый Native Integration Core

Дата: 2026-11-11. Только synthetic POC; production readiness отсутствует.

## Реализовано

- Основной проект переключён на development/protected-openwebui.
- Контрольный POC сохранён в commit eab205a; compose, services, UI и tests не заменены.
- Создан независимый полноценный Git checkout /home/user/ai-fire2/forks/open-webui
  с историей upstream, чистой базой b0e6098e940942281d9c83f3529ea117287a3a22,
  веткой firewall/native-core, LICENSE/историей лицензии и исходным branding.
- Dirty vendor working tree не изменялся. Git clone использовал Git objects,
  не локальные незакоммиченные изменения. Push отключён; публикаций не было.
- fork-manifest.json, setup-fork.py/check-fork.py задают происхождение и восстановление.
- ADR-004 документирует решения и точки интеграции до изменения upstream.
- docker/Dockerfile.native подготовлен для оригинальных исходников; runtime
  намеренно отключён, чтобы незавершённая интеграция не открыла незащищённый сервер.

## Реально проверено

- Проверка ancestry, branch, remote и наличия лицензий — PASS.
- git diff upstream -- src backend пуст, checkout чистый: frontend не заменён.
- Контрольный Compose suite: 54 passed, 1 warning, 12.04s.
- Контрольный Chromium: 1 passed, 1 skipped, 10.95s (outage phase отдельно не запускалась).
- Проверки БД/canary входят в выполненный POC suite; это не тесты native fork.
- Пять контрольных сервисов работают, WebUI healthy.
- git diff --check — PASS.

## Не выполнено / следующий шаг

Итерация A частичная: полная оригинальная frontend-сборка Dockerfile.native не
запускалась. Native Integration Core B НЕ реализован: нет native auth/chat E2E,
native admission writers, output gate, Socket.IO security и native reveal.
Нельзя заявлять выполнение конечной задачи или открывать штатные content APIs.
Контрольный POC по-прежнему использует упрощённый UI и временную auth, только
в контрольном контуре. Подготовленный чистый fork пока не запускается как сервис.

Следующий независимый шаг: собрать оригинальный frontend, реализовать отдельный
authenticated batch inspection contract Gateway (полный verdict до Vault), покрыть
BLOCK/REVIEW zero-write и outage; затем native pre-side-effect hooks и writer
permits согласно ADR. Не переносить fixed synthetic users в native auth.

## Воспроизведение и обновления

Из /home/user/ai-fire2 выполнить python3 scripts/setup-fork.py, затем
python3 scripts/check-fork.py. Скрипт не reset/clean существующий checkout.
Исходники fork исключены из основного Git, но имеют собственную историю;
изменения fork следует коммитить в этом репозитории и экспортировать patch series
до объявления этапа завершённым. Пока изменений upstream нет.

Для обновления: git -C /home/user/ai-fire2/forks/open-webui fetch upstream;
затем отдельная upgrade branch и review diff. Не делать автоматический merge.
GitHub fork и remote origin владельца добавляются только после его разрешения.
Перед remote publication отдельно проверить license/branding, secrets и security tests.