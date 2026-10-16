# Оркестратор для генерации сцен визуальной новеллы

Минималистичное асинхронное Python-приложение, отслеживающее изменения задач в MongoDB и генерирующее JSON-сцены.

## Структура
- `main.py` — точка входа.
- `core/` — логика (генерация сцен, менеджер задач, логирование, работа с MongoDB).
- `config/env.py` — загрузка переменных окружения (`python-dotenv`).
- `logs/` — ротационные логи (создаются при запуске).
- `Novel/game/scenes/` — целевые JSON-файлы сцен (создаётся автоматически).

## Переменные окружения
Приложению нужны:
- `MONGO_URI` — строка подключения к MongoDB (например: `mongodb://user:pass@host:27017/?authSource=admin`).
- `MONGO_DB_NAME` — имя базы данных (опционально, по умолчанию `default_db`).

Перед запуском контейнера задайте как минимум `MONGO_URI`.

## Локальный запуск (без контейнера)
```cmd
pip install -r requirements.txt
set MONGO_URI=mongodb://localhost:27017
set MONGO_DB_NAME=mydb
python main.py
```
(На PowerShell используйте `$env:MONGO_URI=...`.)

## Dockerfile
`Dockerfile` создан на базе `python:3.12-slim`:
- Кеширование зависимостей через отдельную копию `requirements.txt`.
- Непривилегированный пользователь `appuser`.
- Автоматическое создание директорий `logs` и `Novel/game/scenes`.
- Стартовая команда: `python main.py`.

## .dockerignore
Исключает: логи, кеши, VCS, IDE-файлы, виртуальные окружения.

## Сборка образа
Из корня проекта (`orchestrator`):
```cmd
docker build -t orchestrator:latest .
```

## Запуск контейнера
Минимально (только обязательная переменная):
```cmd
docker run --rm -e MONGO_URI=mongodb://host:27017 orchestrator:latest
```
С указанием имени базы:
```cmd
docker run --rm ^
  -e MONGO_URI=mongodb://host:27017 ^
  -e MONGO_DB_NAME=mydb ^
  orchestrator:latest
```
(В Windows `cmd` символ `^` переносит команды на новую строку.)

Запуск с маунтом локальной директории для логов и сцен:
```cmd
mkdir data_logs
mkdir data_scenes
docker run --rm ^
  -e MONGO_URI=mongodb://host:27017 ^
  -v %cd%\data_logs:/app/logs ^
  -v %cd%\data_scenes:/app/Novel/game/scenes ^
  orchestrator:latest
```

## Тест генератора сцен отдельно
Можно выполнить генерацию без подключения к MongoDB:
```cmd
docker run --rm orchestrator:latest python -m core.scene_generator > scene_sample.json
```
Это вызовет модуль напрямую, не стартуя основной цикл.

## Завершение работы
Контейнер завершается при остановке процесса. Для длительной работы используйте перезапуск:
```cmd
docker run -d --restart=unless-stopped -e MONGO_URI=mongodb://host:27017 orchestrator:latest
```

## Типичные проблемы
1. Ошибка подключения: проверьте корректность `MONGO_URI` и сетевую доступность БД.
2. Пустые логи: убедитесь, что директория смонтирована корректно (права записи для непривилегированного пользователя внутри контейнера).
3. Зависание: приложение ожидает события в change stream. Убедитесь, что в MongoDB включён реплика сет (для `watch()` требуется replica set). В одиночном `mongod` без replica set change streams не работают.

## Обновление образа
После изменения зависимостей:
```cmd
docker build --no-cache -t orchestrator:latest .
```