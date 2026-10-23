# Контракт ML ↔ backend: три канала вместо одного

Дата: 2026-10-22
Ветка: `feature/ml-contract`
Зона изменений: только `ml/` и блок `ml` в `docker-compose.yml`. Код backend не трогаем.

## Цель

Backend и ML общаются через три отдельные пары Redis Streams вместо одной пары
`ml-tasks` / `ml-results` с дискриминатором `type` внутри payload. Тип задачи
определяется именем стрима, поле `type` не передаётся ни в одну сторону.

Дополнительно: ML пишет в БД только `material_chunks`. Все остальные таблицы
пишет backend, получая данные из результата ML.

## Стримы

| Направление | Стрим |
|---|---|
| BE → ML | `ml:tasks:ingest`, `ml:tasks:create-test`, `ml:tasks:grade-attempt` |
| ML → BE | `ml:results:ingest`, `ml:results:create-test`, `ml:results:grade-attempt` |

Consumer group `ml-workers` создаётся на каждом входящем стриме с `mkstream=True`
и стартовым id `0`, `BUSYGROUP` проглатывается. Результатные стримы воркер не читает.

Имена стримов задаются переменными окружения, дефолты — как в таблице выше.

## Контракты

### ingest

BE → ML:

```json
{
  "task_id": "uuid-task",
  "material_id": "uuid-material",
  "storage_key": "uuid-material/file.pdf"
}
```

ML → BE, успех:

```json
{ "task_id": "uuid-task", "status": "ok" }
```

ML → BE, ошибка:

```json
{ "task_id": "uuid-task", "status": "error", "error": "unsupported format: .xyz" }
```

### create_test

BE → ML:

```json
{
  "task_id": "36557924-95eb-49f7-8ca1-ed8317d7cb7f",
  "test_id": "57800578-3084-4553-ad11-0b79490daaa7",
  "material_ids": ["78f214ee-e482-4404-a942-d9c269fa65c0"],
  "title": "Test on models",
  "num_questions": 5,
  "difficulty": "medium",
  "course_id": "b7faa854-c3e9-4483-8422-029632692260"
}
```

ML → BE, успех:

```json
{
  "task_id": "36557924-95eb-49f7-8ca1-ed8317d7cb7f",
  "status": "ok",
  "test_id": "57800578-3084-4553-ad11-0b79490daaa7",
  "test": {
    "title": "Test on models",
    "questions": [
      {
        "id": 1,
        "text": "...",
        "options": ["...", "...", "...", "..."],
        "correct_index": 0,
        "source_chunk_id": "05a801d9-15ea-48f2-86cb-bd47f3e15610"
      }
    ]
  }
}
```

ML → BE, ошибка: `task_id`, `test_id`, `status`, `error`.

### grade_attempt

BE → ML:

```json
{
  "task_id": "3b170e9a-faf0-494b-99d5-c98f73f8dbdc",
  "attempt_id": "dc128404-b7c6-4134-8c45-1b22bb9c8cc6",
  "test_id": "57800578-3084-4553-ad11-0b79490daaa7",
  "answers": [
    { "question_id": "05a801d9-15ea-48f2-86cb-bd47f3e15610", "student_answer_index": 0 }
  ]
}
```

ML → BE, успех:

```json
{
  "task_id": "3b170e9a-faf0-494b-99d5-c98f73f8dbdc",
  "status": "ok",
  "attempt_id": "dc128404-b7c6-4134-8c45-1b22bb9c8cc6",
  "test_id": "57800578-3084-4553-ad11-0b79490daaa7",
  "score_pct": 60.0,
  "grade": 3,
  "overall_feedback": "...",
  "items": [
    { "question_id": "05a801d9-15ea-48f2-86cb-bd47f3e15610", "score": 1.0 }
  ]
}
```

ML → BE, ошибка: `task_id`, `attempt_id`, `test_id`, `status`, `error`.

## Что убрано из ответа ML

| Канал | Поле | Почему |
|---|---|---|
| все | `type` | Тип задаёт имя стрима |
| все | `input_msg_id` | Backend сопоставляет результат по `task_id` |
| create_test | `explanation` | В `test_questions` нет такой колонки |
| create_test | `points` | В `test_questions` нет такой колонки |
| grade_attempt | `is_correct` | Выводится из `score` |
| grade_attempt | `correct_index` | Лежит в `test_questions.answer_key`, backend его уже знает |
| grade_attempt | `student_answer_index` | Лежит в `attempt_answers.student_answer`, backend его уже знает |
| grade_attempt | `correct_text` | Выводится из `options[correct_index]` |
| grade_attempt | `items[].feedback` | Фидбэк один на попытку — `overall_feedback` |

## Разделение записи в БД

ML пишет ровно одну таблицу — `material_chunks`: `chunk_id`, `material_id`,
`text_chunk`, `embedding`. Больше ничего.

Backend пишет `test_questions`, `student_attempts`, `attempt_answers` и все
статусы: `materials.status_material`, `tests.status_test`.

### Обязанности backend, следующие из контракта

1. `ingest` не возвращает `material_id`. Чтобы поставить
   `status_material='ready'`, backend обязан хранить соответствие
   `task_id → material_id` с момента отправки задачи.
2. `type_question` в ответе ML нет. Backend проставляет `"single_choice"` сам —
   ML генерирует только этот тип.
3. `overall_feedback` backend кладёт в `student_attempts.overall_feedback`.
4. `items[].score` backend кладёт в `attempt_answers.score`.
   Колонка `attempt_answers.feedback` остаётся NULL.
5. `source_chunk_id` — внешний ключ на `material_chunks.chunk_id`, поэтому
   ML обязан вставлять чанки с настоящими UUID и возвращать в вопросе именно
   тот `chunk_id`, из которого вопрос выведен.

## Поведение LLM

### Генерация теста

LLM получает подборку релевантных чанков в `<context>...</context>` и
возвращает строгий JSON:

```json
{
  "title": "<до 80 символов>",
  "questions": [
    {
      "id": 1,
      "text": "<текст вопроса>",
      "options": ["<A>", "<B>", "<C>", "<D>"],
      "correct_index": 0,
      "explanation": "<короткое объяснение>"
    }
  ]
}
```

`explanation` обязателен, но в BE не уходит: требование объяснить ответ
заставляет модель перепроверить `correct_index`. `points` в схеме нет.

Требования промпта: ровно `num_questions` вопросов, заданная сложность, ровно
4 варианта, ровно один верный, `correct_index` с нуля, без повторов между
вопросами, факты только из контекста.

### Общий фидбэк

LLM отдаёт обычный текст без JSON. На вход — название теста и список промахов
(текст вопроса, ответ студента, правильный ответ). Промпт требует обращение
на «ты», 3–5 предложений, без похвалы за правильные ответы и без перечисления
вопросов подряд. Если промахов нет — короткое «что закрепить», без выдуманных
ошибок.

## Структура модулей

```
ml/app/
  contracts.py               3 задачи + 3 результата, без type
  db/pool.py                 asyncpg-пул, ленивый, один на процесс
  db/chunks.py               запись и векторный поиск по material_chunks (pgvector)
  db/questions.py            чтение test_questions для grader'а
  handlers/ingest.py         чистые функции, без Redis
  handlers/create_test.py
  handlers/grade_attempt.py
  parsers/registry.py        dispatch по расширению
  services/storage.py        скачивание из S3
  services/test_generator.py
  services/grader.py         детерминированная проверка индексов
  services/feedback.py       LLM → overall_feedback
  workers/worker.py          три XREADGROUP-цикла
```

Хендлеры — чистые функции без Redis, вызываются и воркером, и тестами.
`rag_question` из контракта удалён.

## Ошибки

- Любое исключение в хендлере → результат со `status: "error"`, `task_id` и
  тем идентификатором, который известен (`material_id` / `test_id` / `attempt_id`).
- Битый JSON в payload логируется и ack'ается, иначе poison-message зациклится.
- Упал XADD результата — сообщение намеренно не ack'ается, остаётся в pending.
- На старте воркер делает `XAUTOCLAIM`, забирая хвосты от упавшего инстанса.
- Парсинг файлов CPU-bound — уходит в `asyncio.to_thread`, чтобы не блокировать
  остальные два цикла воркера.

## Шкала оценок

`score_pct` ≥ 90 → 5, ≥ 70 → 4, ≥ 50 → 3, иначе 2.

## Docker

`ml/Dockerfile`: `python:3.12-slim`, `libpq-dev` и `build-essential` под asyncpg,
непривилегированный пользователь, точка входа `python -m app.workers.worker`.
Healthcheck — `import app.workers.worker`. Входящих портов нет.

В compose сервис `ml` с `depends_on` по healthcheck у postgres, redis,
seaweedfs. Переменные: `DATABASE_URL`, `REDIS_URL`, шесть имён стримов,
`CONSUMER_GROUP`, `CONSUMER_NAME`, параметры S3, `OPENROUTER_API_KEY`,
`LLM_MODEL`, `EMBED_MODEL`, `LOG_LEVEL`.

Отладка стримов — через `SCAN`, а не `KEYS`: при трёх парах стримов `KEYS`
блокирует Redis на больших объёмах.