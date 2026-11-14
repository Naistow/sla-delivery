## Что сделано
- Опишите кратко изменения в модуле контроля SLA доставки.

## Как проверить
1. Запустить тесты: `docker compose run --rm --no-deps app pytest -v`
2. Запустить линтер: `docker compose run --rm --no-deps app flake8 app integration tests --max-line-length=120`
3. Проверить сценарий: `docker compose up --build --abort-on-container-exit`

## Чек-лист
- [ ] Код соответствует правилам слоёв (ядро не зависит от БД и сети)
- [ ] Добавлены автотесты (включая граничные значения SLA)
- [ ] В коммите нет `.env`, паролей и временных выгрузок CSV
- [ ] Документация в `README.md` актуализирована

Closes #
