# Контракт ML ↔ backend, v4

Дата: 2026-11-17
Ветка: `ml/redis-jobs`
Зона: `ml/` (ML). Backend-часть контракта — **требования** (`ml/docs/backend-tz-contract-v4.md`), а не код в этой ветке: backend ведёт другой разработчик.

Схема БД — ERD заказчика (`ml/docs/erd.png`). Где контракт от неё отступает —
в §8, с обоснованием.

## 0. Что изменилось с v3

v3 — это контракт тиммейта, приведённый к ERD. v4 — тот же контракт, но
доведённый до состояния, в котором backend и ML **находятся на одной ветке и
договорились о разделении ответственности за БД**.

| # | Изменение | Почему |
|---|---|---|
| 1 | Backend больше не держит «словарь контракта» в двух местах: ML — источник правды по payload'ам, backend — по именам каналов и по структуре ответа | Два независимых описания одного JSON разъезжаются; в v3 backend пересказывал формат ML в `ml/docs/integration.md` |
| 2 | `type_question` и `answer_key` пишутся **as-is** из ответа ML | Backend пересобирал `answer_key` из плоских полей — появился риск потерять `explanation` |
| 3 | `amountQuestions` на backend — всегда конкретное число (5/10/20) | Бакеты backend'а («min/medium/max») не совпадают с режимами ML («min» = выбрать сам). Неоднозначность убрана: backend разворачивает бакет в число |
| 4 | `is_correct` и `correct_answer` в `attempt_answers` **удалены** (миграция 006) | В ERD этих колонок нет. Обе величины выводятся при чтении попытки |
| 5 | Добавлена `test_questions.question_order` (миграция 006) | В ERD нет колонки порядка, а без неё вопросы сортируются по случайным UUID |
| 6 | `student_attempts` / `attempt_answers` пишет **backend**, ML присылает только вердикт | `student_answer` — это то, что студент отправил; ML его не знает |
| 7 | Backend подписан на **три отдельных канала** результатов, у каждого своя consumer-группа | Один канал с роутингом по полю `type` — это и есть «прочитать не тем обработчиком» |
| 8 | Явно зафиксирована семантика доставки: at-least-once с двух сторон + идемпотентность записи | Redis Streams дают «хотя бы один раз», а не «ровно один» |

### 0.1 Переименование каналов (2026-11-17)

Имена каналов изменены по требованию заказчика: было `ml-tasks:<type>` /
`ml-results:<type>` — стало `<тип-задачи>:<направление>`, где направление —
`be-to-ml` или `ml-to-be`:

| Было | Стало |
|---|---|
| `ml-tasks:ingest` / `ml-results:ingest` | `ingest:be-to-ml` / `ingest:ml-to-be` |
| `ml-tasks:create_test` / `ml-results:create_test` | `create-test:be-to-ml` / `create-test:ml-to-be` |
| `ml-tasks:grade_attempt` / `ml-results:grade_attempt` | `grade-test:be-to-ml` / `grade-test:ml-to-be` |

Причина: старое имя прятало направление в префиксе и не читалось как «от кого
к кому». Новое читается сразу: `grade-test:be-to-ml` — задача «проверь тест»,
её ждёт ML. Слаг в имени канала — kebab-case, поэтому он не обязан совпадать
с внутренним типом в коде (`create_test` → `create-test`,
`grade_attempt` → `grade-test`); перевод живёт в `app/contracts.py`.

Заодно убрана конфигурируемость префиксов (`ML_TASKS_STREAM`,
`ML_RESULTS_STREAM`, `ML_STREAMS_*_PREFIX`): имена каналов — часть контракта,
и если у сторон разъедутся значения переменной, стримы перестанут совпадать
тихо, с обнаружением только на проде.

Не изменилось: конверт `XADD <channel> * payload '<JSON>'`,
форматы `answer_key`, микс типов по сложности, шкала оценок, правило
`is_correct = score ≥ 0.5`, `score_pct` по всем вопросам теста.

## 1. Транспорт

### 1.1 Каналы

Один тип задачи — один канал. Тип задаёт **имя канала**, а не поле в payload:
поля `type` в сообщениях нет вообще.

Имя канала: `<слаг-типа-задачи>:<направление>`, где направление — `be-to-ml`
(backend → ML) или `ml-to-be` (ML → backend).

| Направление | Канал | Consumer group | Consumer |
|---|---|---|---|
| BE → ML | `ingest:be-to-ml` | `ml-workers` | `worker-1` |
| BE → ML | `create-test:be-to-ml` | `ml-workers` | `worker-1` |
| BE → ML | `grade-test:be-to-ml` | `ml-workers` | `worker-1` |
| ML → BE | `ingest:ml-to-be` | `ml-backend` | `backend-1` |
| ML → BE | `create-test:ml-to-be` | `ml-backend` | `backend-1` |
| ML → BE | `grade-test:ml-to-be` | `ml-backend` | `backend-1` |

Слаг в имени канала — kebab-case и не обязан совпадать с внутренним типом
задачи в коде: `create_test` → `create-test`, `grade_attempt` → `grade-test`.
Внутри ML типы задач остаются `ingest` / `create_test` / `grade_attempt`
(плюс legacy `rag_question`), а `app/contracts.py` переводит тип в слаг.

**Имена каналов — константы контракта, не конфигурация.** Их задаёт обе
стороны одинаково в коде. Конфигурируемый префикс (`ML_TASKS_STREAM` и
подобные) убран намеренно: если у ML и backend'а разъедутся значения
переменной, стримы перестанут совпадать тихо, и это обнаружится только на
проде, в виде «задачи уходят в никуда». Окружением остаётся только
идентификация воркера:

| Переменная | Сервис | По умолчанию |
|---|---|---|
| `CONSUMER_GROUP` | ml | `ml-workers` |
| `CONSUMER_NAME` | ml | `worker-1` |
| `ML_STREAMS_CONSUMER_GROUP` | backend | `ml-backend` |
| `ML_STREAMS_CONSUMER_NAME` | backend | `backend-1` |

Consumer group привязана к одному стриму, поэтому её создают на **каждом**
канале. Backend создаёт группы с `MKSTREAM` — каналы появляются на лету первым
же сообщением.

### 1.2 Конверт

```
XADD <канал> * payload '<JSON одной строкой>'
```

Ровно одно поле — `payload`. Значение — JSON-объект, сериализованный без
переносов строк. Backend читает `MapRecord.getValue().get("payload")` и
парсит в свой record-тип; ML читает `fields["payload"]` и парсит в
dataclass по типу из имени канала.

Машино-читаемые схемы всех шести контрактов (JSON Schema draft 2020-12) —
в `ml/docs/contracts/`, с каноническими примерами payload'ов в
`ml/docs/contracts/examples/`. Примеры сгенерированы из `app/contracts.py`,
тест `ml/tests/test_contract_schema.py` не даёт им разъехаться с кодом.

### 1.3 Семантика доставки

Redis Streams — **at-least-once**. Обе стороны это учитывают:

| Событие | ML (каналы задач) | Backend (каналы результатов) |
|---|---|---|
| Упал после чтения, до `XACK` | Сообщение висит в pending; следующий круг забирает его `XAUTOCLAIM` по `reclaim_idle_ms` | Сообщение висит в pending; **reclaim не реализован**, забирать придётся вручную |
| Упал после `XADD` результата, до `XACK` | Задача выполнится заново → backend получит результат дважды | — |
| Обработчик бросил исключение | Отправляет `status:"error"` и `XACK`ает | Логирует и **не** `XACK`ает — сообщение остаётся в pending (его можно переиграть вручную) |
| Backend лежал, ML работал | — | Сообщения, опубликованные пока backend лежал, **не теряются**: `last-delivered-id` группы не двигается, при первом чтении после подъёма группа отдаст их |

Идемпотентность записи — обязательное условие, а не опция:

- вопросы теста — `question_id = uuid5(test_id, "q:" + порядковый номер)`;
  повторная обработка результата `create_test` не плодит дубли;
- вердикт по попытке — `UPDATE` по `answer_id`/`attempt_id`, повторный вердикт
  перезаписывает те же строки.

**Асимметрия намеренная.** Reclaim на стороне ML нужен, потому что там
долгая работа (индексация, генерация теста, LLM-судья) и падение воркера
 commonplace. На стороне backend'а обработка — короткая транзакция; reclaim
не реализован, чтобы не тащить непроверенный API в код, который никто не
тестировал. Следствие: если backend упал **в момент** обработки результата,
этот результат останется в pending и потребует ручного `XCLAIM`. Все
остальные сценарии (backend лежал до чтения; ML перезапустился) отрабатывают
без потерь.

### 1.4 Ошибки

ML **всегда отвечает** — в том числе на ошибку:

- неизвестный тип канала → `{"task_id":"","status":"error","error":"unknown task type: …"}`;
- битый JSON в payload → `{"task_id":"","status":"error","error":"payload is not valid JSON: …"}`;
- исключение в handler'е → `{"task_id":…,"status":"error","error":"<Type>: <msg>"}`.

Backend на `status:"error"` не падает: он переводит нужную строку в статус
`error` (материал / тест) или оставляет попытку без изменений.

## 2. `ingest`

### 2.1 BE → ML

```json
{
  "task_id": "8f1b…",
  "material_id": "5a2c…",
  "storage_key": "uploads/lec.pdf"
}
```

`task_id` необязателен (корреляция идёт по `material_id`), но backend его
шлёт всегда.

### 2.2 ML → BE

Успех (`status:"ready"` — тот же смысл, что у `materials.status_material`):

```json
{
  "task_id": "8f1b…",
  "material_id": "5a2c…",
  "status": "ready",
  "chunks_indexed": 29
}
```

Ошибка:

```json
{
  "task_id": "8f1b…",
  "material_id": "5a2c…",
  "status": "error",
  "error": "unsupported format: .xyz"
}
```

`material_id` в error-ветке обязателен, если он известен: без него backend не
знает, какую строку `materials` перевести в `error`.

### 2.3 Что делает backend

`materials.status_material` ← `ready` / `error`. Больше ничего: чанки в БД
пишет сам ML (`material_chunks`).

## 3. `create_test`

### 3.1 BE → ML

```json
{
  "task_id": "36557924-95eb-49f7-8ca1-ed8317d7cb7f",
  "test_id": "57800578-3084-4553-ad11-0b79490daaa7",
  "material_ids": ["78f214ee-e482-4404-a942-d9c269fa65c0"],
  "title": "Test on models",
  "amountQuestions": 10,
  "difficulty": "medium",
  "course_id": "b7faa854-c3e9-4483-8422-029632692260"
}
```

| Поле | Тип | Обяз. | Правило |
|---|---|---|---|
| `task_id` | uuid-строка | да | Корреляция «какая именно задача» внутри канала |
| `test_id` | uuid-строка | да | Запись в `tests`, которую надо обновить |
| `material_ids` | список uuid-строк | да | Непустой список уже проиндексированных материалов |
| `title` | строка | да | — |
| `amountQuestions` | целое 1..30 | да | «Ровно столько вопросов» |
| `difficulty` | `easy`\|`medium`\|`hard` | да | Уровень теста, микс типов (§5) |
| `course_id` | uuid-строка | нет | Для логов |

`amountQuestions` в контракте ML допускает и строку `"min"` — «размер выбирает
ML сам по материалу» (`test_planner.py`). **Backend всегда присылает
конкретное число**: свои бакеты `min/medium/max` разворачиваются в 5/10/20
(`TestAmountQuestions.toMlAmount()`). Причина — расхождение смыслов: бакет
backend'а «min» = «маленький тест», режим ML «min» = «планировщик сам». Одно
и то же слово означало бы разное, поэтому backend не даёт ML выбирать размер
сам, а микс и объём остаются на стороне ML.

### 3.2 ML → BE

Успех:

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
        "type": "single_choice",
        "text": "Текст вопроса",
        "options": ["A", "B", "C", "D"],
        "answer_key": { "correct_index": 0, "explanation": "Почему так" },
        "key_points": [],
        "source_chunk_id": "05a801d9-15ea-48f2-86cb-bd47f3e15610"
      }
    ]
  }
}
```

Ошибка:

```json
{
  "task_id": "36557924-95eb-49f7-8ca1-ed8317d7cb7f",
  "status": "error",
  "test_id": "57800578-3084-4553-ad11-0b79490daaa7",
  "error": "…"
}
```

`test_id` обязателен в обеих ветках — по нему backend переводит `tests.status_test`
в `error`.

### 3.3 Формат вопроса

| Поле | Тип | Описание |
|---|---|---|
| `id` | целое | Порядковый номер в тесте. В БД не сохраняется — backend генерирует свой `question_id` |
| `type` | `single_choice`\|`multi_choice`\|`open_answer` | Тип вопроса |
| `text` | строка | Текст вопроса |
| `options` | список строк | `[]` у `open_answer`, 2–4 у `single_choice`, 4–6 у `multi_choice` |
| `answer_key` | объект | Эталон, форма — по типу (§3.4) |
| `key_points` | список строк | 2–4 опорных пункта у `open_answer`, `[]` у закрытых типов |
| `source_chunk_id` | uuid-строка \| null | Чанк, из которого взят вопрос. `null`, если чанка нет в БД |

`answer_key` и `key_points` backend пишет **as-is** — не пересобирает, не
валидирует заново. Валидацию уже сделал ML (см. §3.5).

### 3.4 `answer_key` по типам

| Тип | `answer_key` | `key_points` | `options` |
|---|---|---|---|
| `single_choice` | `{"correct_index": 0, "explanation": "…"}` | `[]` | 2–4 |
| `multi_choice` | `{"correct_indexes": [0, 2], "explanation": "…"}` | `[]` | 4–6 |
| `open_answer` | `{"reference_answer": "эталон", "explanation": "…"}` | 2–4 строки | `[]` |

`explanation` есть у всех типов — короткое объяснение правильного ответа.
Backend кладёт его в `test_questions.answer_key` и отдаёт клиенту вместе с
эталоном.

`multi_choice` — 2 или 3 правильных варианта, индексы отсортированы.

### 3.5 Проверка на стороне ML

ML отвергает ответ сам, до отправки в backend (`TestQuestion.from_dict`):
`single_choice` — меньше двух вариантов или `correct_index` вне диапазона;
`multi_choice` — меньше двух правильных индексов, дубликаты, выход за
диапазон; `open_answer` — пустой `reference_answer`.

Генерация идёт через **JSON Schema** (`response_format=json_schema`,
`strict: true`), а не через `json_object`: на `json_object` модель
`deepseek/deepseek-v4.1-flash` в 5 прогонов из 5 отдавала мусор — пустой `{}`
или обрыв по `finish_reason=length`. Constrained decoding делает структурную
ошибку невозможной на уровне декодирования. Схема жёстко фиксирует
`minItems = maxItems = N` — модель физически не может вернуть не то число
вопросов.

Если LLM не дала нужный микс типов — вторая попытка, потом ошибка. Молчаливой
деградации нет: `open_answer` не подменяется на `single_choice`.

### 3.6 Что делает backend

| Шаг | Действие |
|---|---|
| 1 | `tests.status_test` ← `CREATING` (тест создан, задача ушла в ML) |
| 2 | По `status:"ok"`: сохранить вопросы в `test_questions`, `tests.status_test` ← `READY` |
| 3 | По `status:"error"`: `tests.status_test` ← `ERROR` |

Поля вопроса пишутся один-в-один: `type` → `type_question`, `text` →
`text_question`, `options` → `options` (JSONB), `answer_key` → `answer_key`
(JSONB), `key_points` → `key_points` (JSONB), `source_chunk_id` →
`source_chunk_id` (FK на `material_chunks`, `NULL`, если чанка нет).

`question_id` должен быть **детерминированным** (предложение для
backend'а — `uuid5(test_id, "q:" + i)`, где `i` — порядковый номер вопроса):
один и тот же результат, обработанный дважды, не создаст дубли. Конкретная
формула — на усмотрение backend'а, важна сама детерминированность.

`source_chunk_id` проверяется на существование в `material_chunks`: чанка
нет (in-memory vector store, материал переиндексирован) → пишем `NULL`, а не
роняем вставку по FK.

## 4. `grade_attempt`

### 4.1 BE → ML

```json
{
  "task_id": "3b170e9a-faf0-494b-99d5-c98f73f8dbdc",
  "attempt_id": "dc128404-b7c6-4134-8c45-1b22bb9c8cc6",
  "test_id": "57800578-3084-4553-ad11-0b79490daaa7",
  "user_id": "2c9e…",
  "answers": [
    { "question_id": "05a8…", "student_answer": { "index": 0 } },
    { "question_id": "06b1…", "student_answer": { "indexes": [0, 2] } },
    { "question_id": "07c3…", "student_answer": { "text": "мой ответ" } }
  ]
}
```

`student_answer` — ровно один из трёх видов, по типу вопроса:

| Вид | Когда |
|---|---|
| `{"index": 2}` | `single_choice` |
| `{"indexes": [0, 2]}` | `multi_choice` |
| `{"text": "…"}` | `open_answer` |

`question_id` — это `question_id` из `test_questions` (тот самый детерминированный
uuid5), а не порядковый номер: ML читает вопросы из БД по этому id.

ML читает `test_questions` сам — отдавать ему текст вопросов и эталоны в
payload'е незачем, они уже в БД.

### 4.2 ML → BE

Успех:

```json
{
  "task_id": "3b170e9a-faf0-494b-99d5-c98f73f8dbdc",
  "status": "ok",
  "attempt_id": "dc128404-b7c6-4134-8c45-1b22bb9c8cc6",
  "test_id": "57800578-3084-4553-ad11-0b79490daaa7",
  "score_pct": 60.0,
  "grade": 3,
  "items": [
    {
      "question_id": "05a8…",
      "is_correct": true,
      "score": 1.0,
      "feedback": "Верно",
      "correct_answer": "Текст правильного варианта",
      "student_answer": "Текст отмеченного варианта"
    }
  ]
}
```

Ошибка:

```json
{
  "task_id": "3b170e9a-faf0-494b-99d5-c98f73f8dbdc",
  "status": "error",
  "attempt_id": "dc128404-b7c6-4134-8c45-1b22bb9c8cc6",
  "test_id": "57800578-3084-4553-ad11-0b79490daaa7",
  "error": "…"
}
```

### 4.3 Правила проверки

| Тип | Проверка | Балл |
|---|---|---|
| `single_choice` | `student_answer.index == answer_key.correct_index` | 1.0 или 0.0 |
| `multi_choice` | детерминированно, со штрафом за лишние отметки | `max(0, |верные ∩ отмеченные| − |отмеченные неверные|) / |верные|` |
| `open_answer` | LLM-судья (`open_answer_judge.py`): эталон + `key_points` + ответ студента | дробный 0..1 + `feedback` |

- `is_correct = score ≥ 0.5` (`PARTIAL_CORRECT_THRESHOLD`).
- `score_pct` — процент по **всем** вопросам теста, а не только отвеченным:
  пропущенный вопрос = 0. Иначе попытка без ответов набрала бы 100 %.
- Шкала: ≥90 → 5, ≥70 → 4, ≥50 → 3, иначе 2.
- Fallback судьи: LLM упал или вернула кривой JSON → `score = 0.0`,
  `feedback = "Не удалось автоматически оценить открытый ответ."`. Один
  сбойный вопрос не роняет попытку.
- Тип, которого ML не умеет проверять (`true_false`), → `is_correct=false`,
  `score=0.0`, `feedback` = «Автопроверка для типа … пока не реализована».
  ML не угадывает.

`correct_answer` и `student_answer` в `items[]` приходят строками: текст
правильного варианта (для `open_answer` — эталон) и то, что ответил студент.
**В БД backend их не сохраняет**: `correct_answer` выводится из
`answer_key` + `options` при чтении попытки, `student_answer` backend и так
знает — он писал его при сдаче.

### 4.4 Что делает backend

Порядок при сдаче попытки:

1. Проверить, что тест в статусе `READY` → иначе 400.
2. Создать `student_attempts`: `started_at = now()`, `finished_at`/`score_pct`/
   `grade` — `NULL`.
3. Создать `attempt_answers` — по одной строке на ответ: `student_answer`
   (типизированный JSONB), `score`/`feedback` — `NULL`.
4. Опубликовать задачу `grade_attempt` в `grade-test:be-to-ml`.
5. Ответить клиенту **202 Accepted**: попытка в статусе `processing`.

Порядок при получении вердикта:

| Шаг | Действие |
|---|---|
| 1 | `status:"ok"` → `attempt_answers.score` ← `score`, `attempt_answers.feedback` ← `feedback` |
| 2 | `student_attempts.finished_at` ← now, `score_pct` ← `score_pct`, `grade` ← `grade` |
| 3 | `status:"error"` | попытку **не трогаем** — она остаётся `processing`, ошибка логируется |

Повторный вердикт по той же попытке перезаписывает те же строки — операция
идемпотентна.

### 4.5 Чтение попытки

`GET /api/attempts/{attemptId}` отдаёт:

| Поле | Откуда |
|---|---|
| `status` | `processing` (нет `finished_at`) / `graded` |
| `scorePct`, `grade` | `student_attempts` |
| `items[].isCorrect` | **выводится**: `score ≥ 0.5` |
| `items[].correctAnswer` | **выводится**: `answer_key.correct_index` → `options[i]`; `correct_indexes` → склейка отмеченных вариантов; иначе `answer_key.reference_answer` |
| `items[].studentAnswer` | `attempt_answers.student_answer` |
| `items[].feedback` | `attempt_answers.feedback` |

Отдельных колонок `is_correct` / `correct_answer` в `attempt_answers` нет —
в ERD их нет, и хранить дублирующее поле, которое можно вывести, незачем.

Доступ к попытке: владелец (`student_attempts.user_id`) или владелец курса
(`courses.owner_id`). Иначе 403.

## 5. Типы вопросов, сложность, количество

### 5.1 Микс

`difficulty` приходит в `create_test` и пишется в `tests.difficulty`. Микс
считает **ML** (`test_generator.question_mix`); backend только раскладывает
`type_question` в `test_questions` — никакой логики микса на его стороне
нет, иначе появятся две реализации одного правила, которые разъедутся.

| `difficulty` | `single_choice` | `multi_choice` | `open_answer` |
|---|---|---|---|
| `easy` | 70 % | 30 % | 0 % |
| `medium` | 40 % | 30 % | 30 % |
| `hard` | 10 % | 30 % | 60 % |

Расчёт — метод Д'Хондта (`spread_types`), чтобы доли округлялись без
перекоса; при `easy` вопросов `open_answer` не бывает вовсе.

### 5.2 Размер

1..30 вопросов (`MIN_QUESTIONS`/`MAX_QUESTIONS` в `contracts.py`), вне
диапазона — ошибка контракта.

Backend бакеты `min/medium/max` → 5/10/20 вопросов. ML этот режим («min»,
выбор размера планировщиком по материалу) поддерживает, но backend его не
использует — см. §3.1.

### 5.3 Требование заказчика

Тест содержит и `open_answer` (студент пишет ответ, LLM сверяет с эталоном и
оценивает, допускается частичное совпадение), и `single_choice`, и
`multi_choice` (несколько правильных). Реализовано.

## 6. Разделение записи в БД

| Таблица | Кто пишет |
|---|---|
| `material_chunks` | **ML** (чанки + эмбеддинги) |
| `materials.status_material` | backend (по результату `ingest`) |
| `tests`, `test_questions` | backend |
| `tests.status_test` | backend (по результату `create_test`) |
| `student_attempts`, `attempt_answers` | backend (ответы студента) |
| `student_attempts.score_pct/grade/finished_at`, `attempt_answers.score/feedback` | backend (по вердикту ML) |

ML в таблицы `tests`, `test_questions`, `student_attempts`, `attempt_answers`
не пишет.

## 7. HTTP-слой

Синхронного HTTP между backend и ML нет — только Redis Streams. Все
эндпоинты асинхронные: работа идёт через очередь, клиент опрашивает GET.

| Метод | Путь | Ответ |
|---|---|---|
| `POST` | `/api/tests` | 202 — создание теста, задача ушла в ML |
| `GET` | `/api/tests/{id}` | 200 — тест с вопросами (в статусе `READY`) |
| `POST` | `/api/tests/{id}/attempts` | 202 — попытка создана, ждём вердикт |
| `GET` | `/api/attempts/{id}` | 200 — попытка (`processing` / `graded`) |

## 8. Схема БД: отклонения от ERD

| Что | ERD | В ветке | Почему |
|---|---|---|---|
| `test_questions.answer_key` | есть | есть, JSONB (миграция 006) | Эталон нужен и бэкенду (показать клиенту), и ML (проверка) |
| `test_questions.question_order` | **нет** | **на усмотрение backend'а** (предложение — `INT`, миграция 006) | В ERD нет порядка, а `question_id` — случайный UUID: без порядка вопросы выводились бы в случайном порядке. **ML эту колонку не читает** — это решение backend'а, и отклонение от ERD требует согласования с заказчиком |
| `attempt_answers.is_correct` | **нет** | **нет** — удалено миграцией 006 | Выводится из `score` (порог 0.5) |
| `attempt_answers.correct_answer` | **нет** | **нет** — удалено миграцией 006 | Выводится из `answer_key` + `options` |
| `tests.difficulty` | есть | есть (миграция 004) | Уровень теста |
| `query_tasks`, `query_tasks_materials` | есть | есть (миграция 004-query-tasks) | Очередь задач в БД |
| `course_students` | нет | нет | В ERD нет модели «зачисление на курс». Доступ к курсу — по `courses.owner_id`: курс доступен только владельцу, и попытку может сдать только он |

## 9. Обязанности backend — чек-лист

1. Публиковать в `<тип-задачи>:be-to-ml` с конвертом `payload '<JSON>'`, без
   поля `type`.
2. `create_test`: `amountQuestions` — целое 1..30 (бакет развернуть в число),
   `difficulty` — `easy|medium|hard`, `material_ids` — непустой список.
3. `grade_attempt`: `answers[]` — `{question_id, student_answer}`, где
   `student_answer` — `{index}` | `{indexes}` | `{text}` по типу вопроса.
4. Писать `answer_key` / `key_points` / `options` as-is, не пересобирая.
5. `source_chunk_id` — `NULL`, если чанка нет в `material_chunks`.
6. Писать `attempt_answers` (с `student_answer`) **до** публикации задачи в ML.
7. Не сохранять `is_correct` / `correct_answer` — выводить при чтении.
8. `XACK` — только после успешной обработки; при исключении не подтверждать.
9. `XACK` — в тот же канал, откуда пришло сообщение.
10. Идемпотентность: вопросы — по детерминированному `question_id`, вердикт —
    `UPDATE` по `attempt_id`.

## 10. Известные ограничения

- **Backend не делает reclaim.** Сообщение, застрявшее в pending канала
  результатов, нужно забрать вручную (`XCLAIM`) или переиграть. На стороне ML
  reclaim есть (`XAUTOCLAIM`, `reclaim_idle_ms`).
- **`source_chunk_id` может быть `null`.** ML отдаёт UUID чанка, но если
  векторное хранилище было in-memory или материал переиндексировали — чанка
  в БД нет, backend пишет `NULL`.
- **Нет модели «зачисление на курс».** Попытку может сдать только владелец
  курса. Для сдачи студентом нужен отдельный механизм (в ERD его нет).
- **`rag_question` вне контракта.** Код в ML жив (`RAGQuestionTask`), но
  backend его не использует и канал не подписывает.
- **`query_tasks` не участвует в потоке.** Задача создаётся и уходит в ML
  напрямую; таблица используется как журнал.

## 11. Где что лежит

### ML (`ml/`)

| Файл | Роль |
|---|---|
| `app/contracts.py` | Источник правды по payload'ам: dataclass'ы задач и результатов, `parse_task()`, `stream_channel()` |
| `app/handlers/rag.py` | Handler'ы: `process_ingest`, `process_question`, `process_create_test`, `process_grade_attempt` |
| `app/workers/rag.py` | Redis-цикл: `XREADGROUP` по всем каналам, `XAUTOCLAIM`, `XADD` результата, `XACK` |
| `app/services/test_planner.py` | Размер теста и темы (режим `"min"`) |
| `app/services/test_generator.py` | Генерация теста: микс типов, JSON Schema, привязка к чанкам |
| `app/services/grader.py` | Проверка: `single_choice`, `multi_choice` — детерминированно |
| `app/services/open_answer_judge.py` | LLM-судья для `open_answer` |
| `app/services/test_store.py` | Чтение `test_questions` из Postgres |

### Backend (требования — в этой ветке этих файлов нет)

Backend-часть контракта реализуется на стороне backend-разработчика. Таблица ниже — **не описание существующих файлов**, а список того, что должно появиться и за что отвечает. Формулировки «данные, а не код» — в `ml/docs/backend-tz-contract-v4.md`.

| Что должно быть у backend'а | Роль |
|---|---|
| Словарь имён каналов + consumer group | `ingest:be-to-ml` / `create-test:be-to-ml` / `grade-test:be-to-ml`, группа `ml-workers`; три канала результатов `…:ml-to-be`, своя группа на каждом |
| Продюсер задач | `XADD <канал> * payload '<JSON>'`, без поля `type` |
| Record'ы результатов ML | `IngestResult`, `CreateTestResult` (с вопросами), `GradeAttemptResult` (с items) — по схемам из `ml/docs/contracts/` |
| Подписка на результаты | Три канала `…:ml-to-be`, группы с `MKSTREAM`, чтение с `>` |
| Listener'ы | `ingest` → `materials.status_material`; `create_test` → `test_questions` + `tests.status_test`; `grade_attempt` → `student_attempts` + `attempt_answers`. `XACK` — только после успешной записи |
| Сдача попытки | `student_attempts` + `attempt_answers` создаются **до** публикации задачи, затем 202 Accepted |
| Миграция | `answer_key`, `question_order`, дроп `is_correct` / `correct_answer` |

## 12. Предыдущие версии

| Версия | Файл | Что было |
|---|---|---|
| design | `ml/docs/superpowers/specs/2026-10-22-ml-backend-contract-design.md` | Первая договорённость: три канала вместо одного, ML пишет только `material_chunks` |
| v2 | ветка `back-ml-connect-2` | Наш прежний вариант: `num_questions`, плоские `correct_index`/`student_answer_index`, `overall_feedback` |
| v3 | ветка `back-ml-connect-2` | Контракт тиммейта, приведённый к ERD: `amountQuestions`, `type`, `answer_key`, `status` в результате |

v4 — финальная: она описывает не «как договорились», а **что реализовано в
ветке `ml/redis-jobs`**, где backend и ML живут на одной ветке.
