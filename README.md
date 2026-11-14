# Модуль контроля соблюдения SLA по доставке с агрегацией метрик, алертами и дашбордами (Тема №11)

Курсовой проект по МДК 02.02 «Инструментальные средства разработки программного обеспечения» (специальность 09.07.02 «Информационные системы и программирование», группа ИСП 41).

Система принимает поток событий доставки заказов, проверяет корректность и согласованность данных (диапазоны времени, нормативов, дистанции, средней скорости и временных меток), рассчитывает соблюдение нормативов SLA по зонам доставки, формирует алерты (`WARNING` / `CRITICAL`) при превышении допустимого времени, сохраняет данные в Microsoft SQL Server, обменивается справочниками и сводками с «1С:Предприятие 8.3» через CSV и HTTP, а также предоставляет REST API и веб-дашборд на FastAPI.

## 1. Слои системы и архитектура

| Слой | Назначение в теме №11 | Где находится в проекте |
| :--- | :--- | :--- |
| **Вход** | Генератор потока доставок с контролируемым `--seed`, CSV-файлы обмена из 1С и HTTP POST запросы `/shipments` | `simulate()` в `app/main.py`, `integration/api.py`, `integration/http_client.py` |
| **Проверка** | Чистые функции контроля границ времени `[1; 1440]` мин, норматива `[10; 720]` мин, дистанции `[0.1; 500]` км, скорости `<= 150` км/ч и времени не из будущего | `app/validate.py`, `integration/rules.py` |
| **Расчёт и правила** | Расчёт опоздания `delay_min`, статуса `sla_met`, классификация алертов (`WARNING` / `CRITICAL`) и расчёт `% соблюдения SLA` по зонам | `evaluate_sla()` в `app/validate.py`, `evaluate_alert()` в `integration/rules.py`, `REPORT_SQL` |
| **Хранение** | Таблицы `dbo.delivery_zone`, `dbo.shipment_event`, `dbo.sla_alert`, `dbo.rejected_event` в Microsoft SQL Server 2022 + `InMemoryRepository` | `db/init.sql`, `app/db.py`, `integration/repository.py` |
| **Отчёт, алерты и дашборд** | Консольная таблица SLA, выгрузка сводки `exchange/svodka_sla_dlya_1c.csv` для 1С, JSON API `/shipments/summary`, `/alerts` и HTML-дашборд `/dashboard` | `cmd_report()`, `cmd_export1c()` в `app/main.py`, `integration/api.py` |
| **Автотесты и CI/CD** | Модульные, параметризованные, адаптерные и интеграционные тесты (`pytest`), проверка стиля (`flake8`), конвейер GitLab CI | `tests/`, `.gitlab-ci.yml` |

### Схема архитектуры (Mermaid)

```mermaid
flowchart LR
  subgraph Host["Хост / 1С:Предприятие 8.3"]
    ONEC["1С: Справочник ЗоныДоставки и отчёт SLA"]
    VOL[("Том exchange/ (CSV)")]
    ONEC <-->|"spravochnik_zon.csv / svodka_sla_dlya_1c.csv"| VOL
  end

  subgraph Docker["Сеть Docker Compose"]
    SIM["Генератор доставок simulate()"] --> APP["Контейнер app: проверка SLA и расчёт алертов"]
    VOL <-->|"import1c / export1c"| APP
    APP -->|"pymssql (порт 1433)"| DB[("Контейнер db: MS SQL Server 2022")]
    API["Контейнер api: FastAPI + Веб-дашборд :8000"] -->|"MssqlRepository"| DB
  end
```

## 2. Что нужно установить

- **Docker Desktop** (с включённым WSL 2 на Windows; выделить не менее 3–4 ГБ ОЗУ для контейнера SQL Server)
- **Visual Studio Code** (рекомендуемые расширения описаны в `.vscode/extensions.json`)
- **Git** (для клонирования и работы с GitLab)
- **Python 3.10+** (при локальном запуске вне контейнера)

## 3. Как запустить проект с нуля (проверка чистого клона)

```bash
git clone <адрес_репозитория> check
cd check
cp .env.example .env
docker compose up --build --abort-on-container-exit
```

При запуске `docker compose up --build --abort-on-container-exit` автоматически поднимается контейнер `db` (Microsoft SQL Server 2022), дожидается статуса `healthy`, после чего контейнер `app` выполняет полный сквозной сценарий (`run-all`):
1. `init` — применяет идемпотентную схему `db/init.sql` (создаёт базу `sla_delivery` и 4 таблицы).
2. `import1c` — загружает справочник зон доставки из `exchange/spravochnik_zon.csv`.
3. `ingest` — генерирует поток из 200 доставок, отсеивает некорректные записи в `dbo.rejected_event`, сохраняет валидные в `dbo.shipment_event` и создаёт алерты в `dbo.sla_alert`.
4. `report` — выводит сводную таблицу соблюдения SLA по зонам в консоль.
5. `export1c` — формирует итоговую выгрузку `exchange/svodka_sla_dlya_1c.csv` для 1С.

### Запуск веб-сервиса и дашборда FastAPI

```bash
docker compose up -d db api
```

После запуска откройте в браузере:
- Интерактивный дашборд SLA и алертов: `http://localhost:8000/dashboard`
- Документация Swagger UI: `http://localhost:8000/docs`

## 4. Как запустить автотесты и линтер

```bash
# Модульные и адаптерные тесты без запуска СУБД (23 теста)
docker compose run --rm --no-deps app pytest -v

# Интеграционные тесты на живой базе SQL Server (все 25 тестов)
docker compose up -d db
docker compose run --rm -e RUN_DB_TESTS=1 app python -m app.main init
docker compose run --rm -e RUN_DB_TESTS=1 app pytest -v

# Проверка стиля кода линтером flake8
docker compose run --rm --no-deps app flake8 app integration tests --max-line-length=120
```

## 5. Структура проекта

```text
sla_delivery_project/
  app/                          # Консольное приложение (Методички 1-6)
    config.py                   # Чтение настроек из переменных окружения
    validate.py                 # Чистые функции валидации и расчёта SLA/алертов
    db.py                       # Подключение к SQL Server с повторами и запуском init.sql
    main.py                     # Команды: init, ingest, report, import1c, export1c, run-all
  integration/                  # Слоистая архитектура и веб-сервис (Большая методичка)
    settings.py                 # Неизменяемый dataclass Settings.from_env()
    domain.py                   # Предметные объекты ShipmentReading, SlaAlertRecord, ZoneSlaSummary
    rules.py                    # Чистые бизнес-правила проверки и генерации алертов
    repository.py               # Протокол хранилища, InMemoryRepository и MssqlRepository
    service.py                  # Сценарий приёма с внедрением зависимостей (ingest)
    http_client.py              # HTTP-клиент справочника 1С с таймаутами и повторами
    api.py                      # Веб-интерфейс FastAPI (/shipments, /alerts, /dashboard)
    server.py                   # Точка сборки приложения для uvicorn
  db/
    init.sql                    # Идемпотентная схема БД SQL Server и начальные данные
    queries.sql                 # Отчётные SQL-запросы и команды BACKUP / RESTORE
    schema.dbml                 # Описание ER-диаграммы для dbdiagram.io
  exchange/
    spravochnik_zon.csv         # Образец выгрузки справочника зон доставки из 1С
    1c_obrabotka_obmen.bsl      # Код внешней обработки и HTTP-сервиса для 1С:Предприятие 8.3
  tests/                        # Автотесты (ядро, граничные случаи, HTTP-клиент, FastAPI, MSSQL)
  .gitlab/                      # Шаблоны Merge Request и Issue для GitLab
  .vscode/                      # Задачи (tasks.json) и расширения (extensions.json) для VS Code
  Dockerfile                    # Рецепт сборки Docker-образа приложения
  docker-compose.yml            # Оркестрация контейнеров db, app и api
  .gitlab-ci.yml                # Конвейер CI/CD (стадии lint и test)
  requirements.txt              # Закреплённые версии сторонних библиотек
```

## 6. Формат файлов обмена с 1С и схема БД

### Формат входного справочника (`exchange/spravochnik_zon.csv`)
- **Разделитель:** точка с запятой `;`
- **Кодировка:** `UTF-8` (поддерживается BOM через `utf-8-sig`)
- **Естественный ключ:** колонка `Код` (нормализуется через `.strip().upper()`)
- **Колонки:** `Код;Наименование;НормативМин;КритОпозданиеМин`

### Формат выгружаемой сводки (`exchange/svodka_sla_dlya_1c.csv`)
- **Колонки:** `Код;Наименование;ВсегоДоставок;В_Срок;Нарушений_SLA;Процент_SLA;СреднееВремяМин;МаксОпозданиеМин;АктивныхАлертов`

### Таблицы базы данных (`sla_delivery`)
1. `dbo.delivery_zone` — справочник зон доставки и нормативов SLA (`code` UNIQUE, `sla_target_min`, `max_delay_min`).
2. `dbo.shipment_event` — принятые события доставки (`order_no`, `zone_id` FK, `planned_min`, `actual_min`, `delay_min`, `sla_met`, `delivered_at`).
3. `dbo.sla_alert` — сработавшие алерты при нарушении SLA (`shipment_id` FK, `zone_code`, `severity`, `alert_message`, `created_at`).
4. `dbo.rejected_event` — отклонённые записи с указанием причины (`order_no`, `zone_code`, `raw_value`, `delivered_at`, `reason`).

## ���-��������� FastAPI
- `GET /dashboard` � HTML-������� SLA
- `GET /alerts` � ����� �������

