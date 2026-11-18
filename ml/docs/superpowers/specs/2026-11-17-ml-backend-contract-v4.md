# Контракт ML ↔ backend, v4.1

Дата: 2026-11-17
Ветка: `ml/redis-jobs`
Зона: `ml/` (ML). Backend-часть контракта — **требования** (`ml/docs/backend-tz-contract-v4.md`), а не код в этой ветке: backend ведёт другой разработчик.

**Канон — контракт заказчика.** Шесть payload'ов, присланных заказчиком (09.11.2026), — источник истины по составу полей. Всё, чего в них нет, в контракте отсутствует: `input_msg_id`, `course_id`, `chunks_indexed`, `user_id`, `status` в ответе по проверке. Источник правды по реализации — `ml/app/contracts.py`, машинно-читаемые схемы — `ml/docs/contracts/`.

⚠️ **Версия контракта — v4.1** (правка 2026-11-17). Относительно v4 поле `amountQuestions` убрано, а `answer_key` в ответе `create_test` возвращено. Все изменения — в §0.3.

**Схема БД** — по фактически применённым миграциям `001…005-materials-test.sql`. Где они расходятся с ERD заказчика (`ml/docs/erd.png`) — в §8, с обоснованием.

## 0. Что изменилось с v3

v3 — контракт тиммейта, приведённый к ERD. v4 — тот же каркас (каналы, конверт, at-least-once), но **состав полей приведён к контракту заказчика**, а эталон правильного ответа переехал внутрь ML.

| # | Изменение | Почему |
|---|---|---|
| 1 | В ответе `create_test` у вопроса **есть `answer_key`** *(v4 → v4.1: поле возвращено, см. §0.3)* | Эталон правильного ответа нужен backend'у: без него нельзя показать студенту правильный ответ. В ERD заказчика есть колонка `test_questions.answer_key` — теперь ML её заполняет |
| 2 | ML хранит эталоны у себя в Redis (`ml:answers:{test_id}`) — **резервная копия**, не единственный источник | Приоритет при проверке: **БД → Redis → LLM-судья** (§0.3, §4.3). Backend не знает `question_id` на момент генерации (он его назначает сам), поэтому в Redis эталон лежит по нормализованному тексту вопроса |
| 3 | В ответе `grade_test` **нет поля `status`** | Признак ошибки — само наличие ключа `error`. Раньше backend различал ветки по `status`, теперь в этом канале такого поля нет |
| 4 | В задаче `ingest` **нет `task_id`** | Корреляция в ingest — по `material_id` |
| 5 | В задаче `grade_test` **нет `user_id`** | Студент известен backend'у по `attempt_id`; ML его не требует |
| 6 | Из ответа `ingest` убран `chunks_indexed` | В контракте заказчика его нет |
| 7 | `amountQuestions` **убрано из задачи** *(v4 → v4.1: поле удалено, см. §0.3)* | Размер теста всегда выбирает ML планировщиком (`test_planner.plan_test`) — единый режим вместо двух («число» и `"min"») |
| 8 | `course_id` убран из payload'ов | Связь теста с курсом backend хранит у себя |
| 9 | `is_correct` и `correct_answer` в `attempt_answers` **заполняются из вердикта ML** | В миграции `001` обе колонки NOT NULL, и ML присылает обе величины в `items[]`. Заполнить их — обязанность backend'а, а не вывод при чтении |

### 0.1 Переименование каналов (2026-11-17)

Имена каналов изменены по требованию заказчика: было `ml-tasks:<type>` / `ml-results:<type>` — стало `<тип-задачи>:<направление>`, где направление — `be-to-ml` или `ml-to-be`:

| Было | Стало |
|---|---|
| `ml-tasks:ingest` / `ml-results:ingest` | `ingest:be-to-ml` / `ingest:ml-to-be` |
| `ml-tasks:create_test` / `ml-results:create_test` | `create-test:be-to-ml` / `create-test:ml-to-be` |
| `ml-tasks:grade_attempt` / `ml-results:grade_attempt` | `grade-test:be-to-ml` / `grade-test:ml-to-be` |

Причина: старое имя прятало направление в префиксе и не читалось как «от кого к кому». Слаг в имени канала — kebab-case, поэтому он не обязан совпадать с внутренним типом в коде (`create_test` → `create-test`, `grade_attempt` → `grade-test`); перевод живёт в `app/contracts.py`.

Заодно убрана конфигурируемость префиксов: имена каналов — часть контракта, и если у сторон разъедутся значения переменной, стримы перестанут совпадать тихо, с обнаружением только на проде.

### 0.2 Канонические payload'ы заказчика

```jsonc
// ingest:be-to-ml
{"material_id": "uuid-material", "storage_key": "uuid-material/file.pdf"}
// ingest:ml-to-be
{"material_id": "uuid-material", "status": "ready"}

// create-test:be-to-ml
{"task_id": "…", "test_id": "…", "material_ids": ["…"], "title": "Test on models",
 "difficulty": "medium"}
// create-test:ml-to-be
{"task_id": "…", "status": "ok", "test_id": "…",
 "test": {"title": "…", "questions": [{"id": 1, "type": "single_choice", "text": "…",
          "options": ["…"], "key_points": null, "source_chunk_id": "…",
          "answer_key": {"correct_index": 0, "explanation": "…"}}]}}

// grade-test:be-to-ml
{"task_id": "…", "attempt_id": "…", "test_id": "…",
 "answers": [{"question_id": "…", "student_answer": {"index": 0}}]}
// grade-test:ml-to-be
{"task_id": "…", "attempt_id": "…", "test_id": "…", "score_pct": 60.0, "grade": 3,
 "items": [{"question_id": "…", "is_correct": true, "score": 1.0, "feedback": "…",
            "correct_answer": "…", "student_answer": "…"}]}
```

### 0.3 Что изменилось в v4.1 (2026-11-17)

v4.1 — точечная правка v4 по результатам прогона ML на живом стенде. Три изменения, все в канале `create_test`.

**1. Из задачи `create-test:be-to-ml` убрано поле `amountQuestions`.** Backend присылает только `task_id`, `test_id`, `material_ids`, `title`, `difficulty`. Число вопросов определяет **сам ML** — отдельным LLM-вызовом планировщика (`app/services/test_planner.py`, `plan_test(llm, digest, difficulty)`), который смотрит на материал и возвращает `num_questions` (1..30) и список тем. Backend после получения теста пишет `tests.amount_questions = len(questions)`.

*Почему:* два режима («ровно N» и «`"min"`») требовали от backend'а знать про планировщик и ошибаться в границах диапазона, а на практике почти всегда использовался `"min"`. Единый режим — меньше мест, где можно разойтись: убрали поле, значит убрали и целый класс расхождений («backend прислал 0 или 31 — кто виноват»). Заодно снят вопрос «а что писать в `tests.amount_questions`, если backend просил не `"min"`?» — ответ теперь всегда один, и он проверяем: длина полученного массива.

**2. В ответ `create-test:ml-to-be` возвращено поле `answer_key` — по объекту на вопрос.** Это эталон правильного ответа:

| Тип вопроса | `answer_key` |
|---|---|
| `single_choice` | `{"correct_index": N}` |
| `multi_choice` | `{"correct_indexes": [N, M]}` |
| `open_answer` | `{"reference_answer": "<эталон>"}` |

Плюс необязательный `explanation` (пояснение к правильному ответу) — в том же объекте. Backend пишет это в колонку `test_questions.answer_key` (она есть в ERD заказчика, `ml/docs/erd.png`).

*Почему:* три причины, накопившиеся вместе.
- **Эталон в Redis с TTL 30 дней ненадёжен.** Redis чистят, TTL истекает, контейнер пересоздаётся — и ML при проверке не находит эталон.
- **LLM-фолбэк (когда эталон не найден) уже давал неверный вердикт.** Замер: на `multi_choice` с тремя правильными вариантами судья назвал **два** правильных вместо трёх. Это не «редкий крайний случай» — это типичная ошибка LLM-судьи на материале с несколькими верными ответами, и она молча портит оценку студенту.
- **Backend без эталона не может показать студенту правильный ответ.** В ERD колонка `test_questions.answer_key` есть, но заполнять её было нечем: ML эталон наружу не отдавал.

**3. Приоритет эталона при проверке: БД → Redis → LLM-судья.** Раньше было Redis → LLM-судья. Теперь ML сначала ищет эталон в БД backend'а (в `test_questions.answer_key`, по `question_id`), и только если там пусто — в Redis (`ml:answers:{test_id}`, TTL 30 дней, поиск по нормализованному тексту вопроса), и лишь затем — LLM-судья. Redis остаётся **резервной копией**, а не единственным источником.

*Почему:* после возврата `answer_key` эталон живёт в БД — там он не протухает и переживает чистку Redis. Redis-ключ нужен как страховка на тот случай, пока backend ещё не записал эталон в БД (окно между `create-test:ml-to-be` и записью listener'а) или если backend не выполнил требование по миграции. Порядок «БД → Redis → LLM» означает: чем надёжнее источник, тем раньше он проверяется; LLM-судья — только последний рубеж, а не штатный путь.

Требования к backend'у по п. 2 и 3 — в §3.3, §3.4, §8 и `ml/docs/backend-tz-contract-v4.md`.

## 1. Транспорт

### 1.1 Каналы

Один тип задачи — один канал. Тип задаёт **имя канала**, а не поле в payload: поля `type` в сообщениях нет вообще.

| Направление | Канал | Consumer group | Consumer |
|---|---|---|---|
| BE → ML | `ingest:be-to-ml` | `ml-workers` | `worker-1` |
| BE → ML | `create-test:be-to-ml` | `ml-workers` | `worker-1` |
| BE → ML | `grade-test:be-to-ml` | `ml-workers` | `worker-1` |
| ML → BE | `ingest:ml-to-be` | `ml-backend` | `backend-1` |
| ML → BE | `create-test:ml-to-be` | `ml-backend` | `backend-1` |
| ML → BE | `grade-test:ml-to-be` | `ml-backend` | `backend-1` |

Слаг в имени канала — kebab-case и не обязан совпадать с внутренним типом задачи в коде: `create_test` → `create-test`, `grade_attempt` → `grade-test`. Внутри ML типы задач остаются `ingest` / `create_test` / `grade_attempt` (плюс legacy `rag_question`), а `app/contracts.py` переводит тип в слаг.

**Имена каналов — константы контракта, не конфигурация.** Их задаёт обе стороны одинаково в коде. Окружением остаётся только идентификация воркера:

| Переменная | Сервис | По умолчанию |
|---|---|---|
| `CONSUMER_GROUP` | ml | `ml-workers` |
| `CONSUMER_NAME` | ml | `worker-1` |
| `ML_STREAMS_CONSUMER_GROUP` | backend | `ml-backend` |
| `ML_STREAMS_CONSUMER_NAME` | backend | `backend-1` |

Consumer group привязана к одному стриму, поэтому её создают на **каждом** канале. Backend создаёт группы с `MKSTREAM` — каналы появляются на лету первым же сообщением.

### 1.2 Конверт

```
XADD <канал> * payload '<JSON одной строкой>'
```

Ровно одно поле — `payload`. Значение — JSON-объект, сериализованный без переносов строк. Backend читает `MapRecord.getValue().get("payload")` и парсит в свой record-тип; ML читает `fields["payload"]` и парсит в dataclass по типу из имени канала.

Машино-читаемые схемы всех шести контрактов (JSON Schema draft 2020-12) — в `ml/docs/contracts/`, с каноническими примерами payload'ов в `ml/docs/contracts/examples/`. Примеры сгенерированы из `app/contracts.py`, тест `ml/tests/test_contract_schema.py` не даёт им разъехаться с кодом.

### 1.3 Семантика доставки

Redis Streams — **at-least-once**. Обе стороны это учитывают:

| Событие | ML (каналы задач) | Backend (каналы результатов) |
|---|---|---|
| Упал после чтения, до `XACK` | Сообщение висит в pending; следующий круг забирает его `XAUTOCLAIM` по `reclaim_idle_ms` | Сообщение висит в pending; **reclaim не реализован**, забирать придётся вручную |
| Упал после `XADD` результата, до `XACK` | Задача выполнится заново → backend получит результат дважды | — |
| Обработчик бросил исключение | Отправляет ошибку в зеркальный канал и `XACK`ает | Логирует и **не** `XACK`ает — сообщение остаётся в pending (его можно переиграть вручную) |
| Backend лежал, ML работал | — | Сообщения, опубликованные пока backend лежал, **не теряются**: `last-delivered-id` группы не двигается, при первом чтении после подъёма группа отдаст их |

Идемпотентность записи — обязательное условие, а не опция:

- вопросы теста — `question_id = uuid5(test_id, "q:" + порядковый номер)`; повторная обработка результата `create_test` не плодит дубли;
- строки ответов — `answer_id = uuid5(attempt_id, question_id)`; повторная сдача не плодит дубли;
- вердикт — `UPDATE` по `attempt_id` + `question_id`, повторный вердикт перезаписывает те же строки.

**Асимметрия намеренная.** Reclaim на стороне ML нужен, потому что там долгая работа (индексация, генерация теста, LLM-судья) и падение воркера — commonplace. На стороне backend'а обработка — короткая транзакция; reclaim не реализован, чтобы не тащить непроверенный API в код, который никто не тестировал. Следствие: если backend упал **в момент** обработки результата, этот результат останется в pending и потребует ручного `XCLAIM`. Все остальные сценарии (backend лежал до чтения; ML перезапустился) отрабатывают без потерь.

### 1.4 Ошибки

ML **всегда отвечает** — в том числе на ошибку. Форма ответа зависит от канала:

| Канал | Ошибка |
|---|---|
| `ingest:ml-to-be` | `{"status":"error","error":"…","material_id":"…"}` — `material_id` может отсутствовать |
| `create-test:ml-to-be` | `{"task_id":"…","status":"error","error":"…","test_id":"…"}` — `test_id` может отсутствовать |
| `grade-test:ml-to-be` | `{"task_id":"…","error":"…"}` — **поля `status` нет**; `attempt_id`/`test_id` могут отсутствовать |

Ошибка в `grade-test:ml-to-be` — **единственный** канал, где у результата нет `status`: признак ошибки — само наличие ключа `error`. Backend не должен ждать `status` в этом канале (проверка «`status == "ok"`» всегда была бы ложной).

Backend на ошибке не падает: он переводит нужную строку в статус `error` (материал / тест) или оставляет попытку без изменений.

## 2. `ingest`

### 2.1 BE → ML

```json
{"material_id": "5a2c…", "storage_key": "materials/5a2c…/lecture.pdf"}
```

Ровно два поля: `material_id` (uuid-строка) и `storage_key` (путь объекта внутри бакета — ML скачивает сам). `task_id` в этом канале нет: корреляция идёт по `material_id`.

### 2.2 ML → BE

Успех (`status:"ready"` — тот же смысл, что у `materials.status_material`):

```json
{"material_id": "5a2c…", "status": "ready"}
```

Ошибка:

```json
{"status": "error", "error": "unsupported format: .xyz", "material_id": "5a2c…"}
```

`material_id` в error-ветке может отсутствовать (если payload не удалось разобрать — ML не знает, о каком материале речь). Если есть — backend переводит эту строку `materials` в `error`.

### 2.3 Что делает backend

`materials.status_material` ← `ready` / `error`. Больше ничего: чанки в БД пишет сам ML (`material_chunks`).

## 3. `create_test`

### 3.1 BE → ML

```json
{
  "task_id": "36557924-95eb-49f7-8ca1-ed8317d7cb7f",
  "test_id": "57800578-3084-4553-ad11-0b79490daaa7",
  "material_ids": ["78f214ee-e482-4404-a942-d9c269fa65c0"],
  "title": "Test on models",
  "difficulty": "medium"
}
```

| Поле | Тип | Обяз. | Правило |
|---|---|---|---|
| `task_id` | uuid-строка | да | Корреляция «какая именно задача» внутри канала |
| `test_id` | uuid-строка | да | Запись в `tests`, которую надо обновить |
| `material_ids` | список uuid-строк | да | Непустой список уже проиндексированных материалов |
| `title` | строка | да | — |
| `difficulty` | `easy`\|`medium`\|`hard` | нет | Уровень теста, микс типов (§5). По умолчанию `medium` |

Поля `amountQuestions` в задаче **нет** (v4.1, §0.3): размер теста определяет ML планировщиком. Backend после получения ответа пишет `tests.amount_questions = len(questions)`.

`course_id` в payload'е нет: связь теста с курсом backend хранит у себя.

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
        "key_points": [],
        "source_chunk_id": "05a801d9-15ea-48f2-86cb-bd47f3e15610",
        "answer_key": {"correct_index": 2, "explanation": "Правильный вариант — C"}
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

`test_id` может отсутствовать в error-ветке — тогда backend не знает, какой тест переводить в `error`, и только логирует.

### 3.3 Формат вопроса

| Поле | Тип | Описание |
|---|---|---|
| `id` | целое | Порядковый номер в тесте (1, 2, 3…). В БД — `question_order` (колонки сейчас нет, см. §8) |
| `type` | `single_choice`\|`multi_choice`\|`open_answer` | Тип вопроса |
| `text` | строка | Текст вопроса |
| `options` | список строк \| null | `null` у `open_answer`, 2–4 у `single_choice`, 4–6 у `multi_choice` |
| `key_points` | список строк \| null | 2–4 опорных пункта у `open_answer`, `null`/`[]` у закрытых типов |
| `source_chunk_id` | uuid-строка \| null | Чанк, из которого взят вопрос. `null`, если чанка нет в БД |
| `answer_key` | объект | **Эталон правильного ответа** (v4.1, §0.3). Формат — по типу вопроса, см. §3.4 |

Backend пишет `options`, `key_points` и `answer_key` as-is — не пересобирает, не валидирует заново (валидацию уже сделал ML, §3.5).

`answer_key` пишется в колонку `test_questions.answer_key` (JSONB) — она есть в ERD заказчика, но **в текущих миграциях её нет**: её добавляет backend своей миграцией (требование — §8). Пока колонки нет, ML работает без неё — проверка идёт по Redis, а LLM-судья остаётся последним рубежом.

### 3.4 Эталон правильного ответа — в ответе ML и в БД

**Формат `answer_key`** — по типу вопроса:

| Тип | `answer_key` | `key_points` | `options` |
|---|---|---|---|
| `single_choice` | `{"correct_index": 0}` (+ необязательный `explanation`) | `[]` | 2–4 |
| `multi_choice` | `{"correct_indexes": [0, 2]}` (+ необязательный `explanation`) | `[]` | 4–6 |
| `open_answer` | `{"reference_answer": "эталон"}` (+ необязательный `explanation`) | 2–4 строки | `[]` |

`multi_choice` — 2 или 3 правильных варианта, индексы отсортированы. `explanation` — короткое пояснение к правильному ответу; поле необязательное, backend кладёт его в `answer_key` как есть.

**Где лежит эталон при проверке — приоритет БД → Redis → LLM-судья:**

| Источник | Когда | Как ищется |
|---|---|---|
| **БД backend'а** — `test_questions.answer_key` | основной | по `question_id` (у ML он уже есть — он читает вопросы из БД) |
| **Redis ML** — `ml:answers:{test_id}`, TTL 30 дней | резервная копия | по нормализованному тексту вопроса (регистр + пробелы приведены к канону): на момент генерации `question_id` ещё не существует — его назначает backend уже по результату |
| **LLM-судья** (`choice_judge.py`, `open_answer_judge.py`) | последний рубеж | если эталона нет ни в БД, ни в Redis |

Почему такой порядок — в §0.3. Ключевой момент: LLM-судья на `multi_choice` может ошибиться в числе правильных вариантов (замер: назвал 2 вместо 3), поэтому это не штатный путь, а последний.

**Что хранится в Redis.** Ключ `ml:answers:{test_id}`, TTL 30 дней; значение — JSON `{"1": {"type": …, "text": …, "options": […], "answer_key": {…}}, "2": {…}}`, где ключ — порядковый номер вопроса. Это **резервная копия**, а не единственный источник: она нужна, пока backend не записал эталон в БД (окно между `create-test:ml-to-be` и записью listener'а) или если backend не выполнил требование по миграции.

### 3.5 Проверка на стороне ML

ML отвергает ответ сам, до отправки в backend (`TestQuestion.from_dict`): `single_choice` — меньше двух вариантов или `correct_index` вне диапазона; `multi_choice` — меньше двух правильных индексов, дубликаты, выход за диапазон; `open_answer` — пустой `reference_answer`.

Генерация идёт через **JSON Schema** (`response_format=json_schema`, `strict: true`), а не через `json_object`: на `json_object` модель `deepseek/deepseek-v4.1-flash` в 5 прогонов из 5 отдавала мусор — пустой `{}` или обрыв по `finish_reason=length`. Constrained decoding делает структурную ошибку невозможной на уровне декодирования. Схема жёстко фиксирует `minItems = maxItems = N` — модель физически не может вернуть не то число вопросов.

Если LLM не дала нужный микс типов — вторая попытка, потом ошибка. Молчаливой деградации нет: `open_answer` не подменяется на `single_choice`.

### 3.6 Что делает backend

| Шаг | Действие |
|---|---|
| 1 | `tests.status_test` ← `CREATING` (тест создан, задача ушла в ML) |
| 2 | По `status:"ok"`: сохранить вопросы в `test_questions`, `tests.status_test` ← `READY` |
| 3 | По `status:"error"`: `tests.status_test` ← `ERROR` |

Поля вопроса пишутся один-в-один: `type` → `type_question`, `text` → `text_question`, `options` → `options` (JSONB), `key_points` → `key_points` (JSONB), `answer_key` → `answer_key` (JSONB), `source_chunk_id` → `source_chunk_id` (FK на `material_chunks`, `NULL`, если чанка нет). `id` → `question_order` — **колонки в текущей схеме нет, её надо добавить** (§8).

`question_id` должен быть **детерминированным** (предложение для backend'а — `uuid5(test_id, "q:" + id)`): один и тот же результат, обработанный дважды, не создаст дубли.

`source_chunk_id` проверяется на существование в `material_chunks`: чанка нет (in-memory vector store, материал переиндексирован) → пишем `NULL`, а не роняем вставку по FK.

`tests.amount_questions` — NOT NULL: заполняется **длиной полученного массива вопросов**, `len(questions)` (в v4.1 поле `amountQuestions` из задачи убрано, §0.3).

## 4. `grade_attempt`

### 4.1 BE → ML

```json
{
  "task_id": "3b170e9a-faf0-494b-99d5-c98f73f8dbdc",
  "attempt_id": "dc128404-b7c6-4134-8c45-1b22bb9c8cc6",
  "test_id": "57800578-3084-4553-ad11-0b79490daaa7",
  "answers": [
    { "question_id": "05a8…", "student_answer": { "index": 0 } },
    { "question_id": "06b1…", "student_answer": { "indexes": [0, 2] } },
    { "question_id": "07c3…", "student_answer": { "text": "мой ответ" } }
  ]
}
```

`user_id` в payload'е нет — студент известен backend'у по `attempt_id`. Если backend пришлёт `user_id` лишним, ML его проигнорирует (разбор терпимый к лишним полям), но полагаться на это нельзя.

`student_answer` — ровно один из трёх видов, по типу вопроса:

| Вид | Когда |
|---|---|
| `{"index": 2}` | `single_choice` |
| `{"indexes": [0, 2]}` | `multi_choice` |
| `{"text": "…"}` | `open_answer` |

`question_id` — это `question_id` из `test_questions` (тот самый детерминированный uuid5), а не порядковый номер: ML читает вопросы из БД по этому id.

### 4.2 ML → BE

Успех — **без поля `status`**:

```json
{
  "task_id": "3b170e9a-faf0-494b-99d5-c98f73f8dbdc",
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

Ошибка — тоже без `status`:

```json
{
  "task_id": "3b170e9a-faf0-494b-99d5-c98f73f8dbdc",
  "attempt_id": "dc128404-b7c6-4134-8c45-1b22bb9c8cc6",
  "test_id": "57800578-3084-4553-ad11-0b79490daaa7",
  "error": "…"
}
```

### 4.3 Правила проверки

| Тип | Проверка | Балл |
|---|---|---|
| `single_choice` | `student_answer.index` vs эталон (БД → Redis → LLM-судья, §3.4) | 1.0 или 0.0 |
| `multi_choice` | детерминированно, со штрафом за лишние отметки; эталон — по тому же приоритету БД → Redis → LLM-судья | `max(0, |верные ∩ отмеченные| − |отмеченные неверные|) / |верные|` |
| `open_answer` | LLM-судья (`open_answer_judge.py`): эталон + `key_points` + ответ студента | дробный 0..1 + `feedback` |

Эталон берётся из первого доступного источника: `test_questions.answer_key` в БД → `ml:answers:{test_id}` в Redis → LLM-судья. Обоснование порядка — §0.3.

- `is_correct = score ≥ 0.5` (`PARTIAL_CORRECT_THRESHOLD`).
- `score_pct` — процент по **всем** вопросам теста, а не только отвеченным: пропущенный вопрос = 0. Иначе попытка без ответов набрала бы 100 %.
- Шкала: ≥90 → 5, ≥70 → 4, ≥50 → 3, иначе 2.
- Fallback судьи: LLM упала или вернула кривой JSON → `score = 0.0`, `feedback = "Не удалось автоматически оценить открытый ответ."`. Один сбойный вопрос не роняет попытку.
- Тип, которого ML не умеет проверять (`true_false`), → `is_correct=false`, `score=0.0`, `feedback` = «Автопроверка для типа … пока не реализована». ML не угадывает.

`correct_answer` и `student_answer` в `items[]` приходят строками: текст правильного варианта (для `open_answer` — эталон) и то, что ответил студент.

### 4.4 Что делает backend

Порядок при сдаче попытки:

1. Проверить, что тест в статусе `READY` → иначе 400.
2. Создать `student_attempts`: `started_at = now()`, `finished_at`/`score_pct`/`grade` — `NULL`.
3. Создать `attempt_answers` — по одной строке на ответ: `student_answer` (типизированный JSONB), `score`/`feedback` — `NULL`. `is_correct` и `correct_answer` — **NOT NULL** в текущей миграции: либо снять NOT NULL своей миграцией и писать `NULL` до вердикта, либо писать заглушку и обновлять из вердикта (§8).
4. Опубликовать задачу `grade_test` в `grade-test:be-to-ml`.
5. Ответить клиенту **202 Accepted**: попытка в статусе `processing`.

Порядок при получении вердикта:

| Шаг | Действие |
|---|---|
| 1 | По каждому `item`: `attempt_answers.score` ← `score`, `feedback` ← `feedback`, `is_correct` ← `is_correct`, `correct_answer` ← `correct_answer` (по `question_id`) |
| 2 | `student_attempts.finished_at` ← now, `score_pct` ← `score_pct`, `grade` ← `grade` |
| 3 | Ошибка (наличие ключа `error`) | попытку **не трогаем** — она остаётся `processing`, ошибка логируется |

`correct_answer` — колонка JSONB, а ML присылает строку: хранить как JSON-строку (`"Read committed"`) или как объект `{"text": "…"}` — решение backend'а, но зафиксировать его в одном месте.

Повторный вердикт по той же попытке перезаписывает те же строки — операция идемпотентна.

### 4.5 Чтение попытки

`GET /api/attempts/{attemptId}` отдаёт:

| Поле | Откуда |
|---|---|
| `status` | `processing` (нет `finished_at`) / `graded` |
| `scorePct`, `grade` | `student_attempts` |
| `items[].isCorrect` | `attempt_answers.is_correct` — заполняется из вердикта ML |
| `items[].correctAnswer` | `attempt_answers.correct_answer` — заполняется из вердикта ML |
| `items[].studentAnswer` | `attempt_answers.student_answer` |
| `items[].feedback` | `attempt_answers.feedback` |

Доступ к попытке: владелец (`student_attempts.user_id`) или владелец курса (`courses.owner_id`). Иначе 403.

## 5. Типы вопросов, сложность, количество

### 5.1 Микс

`difficulty` приходит в `create_test` и пишется в `tests.difficulty`. Микс считает **ML** (`test_generator.question_mix`); backend только раскладывает `type_question` в `test_questions` — никакой логики микса на его стороне нет, иначе появятся две реализации одного правила, которые разъедутся.

| `difficulty` | `single_choice` | `multi_choice` | `open_answer` |
|---|---|---|---|
| `easy` | 70 % | 30 % | 0 % |
| `medium` | 40 % | 30 % | 30 % |
| `hard` | 10 % | 30 % | 60 % |

Расчёт — метод Д'Хондта (`spread_types`), чтобы доли округлялись без перекоса; при `easy` вопросов `open_answer` не бывает вовсе.

### 5.2 Размер

1..30 вопросов (`MIN_QUESTIONS`/`MAX_QUESTIONS` в `contracts.py`), вне диапазона — ошибка контракта.

**Размер всегда выбирает ML.** В задаче `create_test` поля `amountQuestions` нет (v4.1, §0.3) — backend не может ни «заказать» конкретное число, ни передать `"min"`. Единственный путь: планировщик `test_planner.py` (`plan_test(llm, digest, difficulty)`) перебирает проверяемые факты в материале и отдаёт `num_questions` (clamp по границам 1..30) + список тем. Темы уходят в промпт генератора — вопросы почти не дублируются.

Backend узнаёт фактический размер из ответа: `tests.amount_questions = len(questions)`.

### 5.3 Требование заказчика

Тест содержит и `open_answer` (студент пишет ответ, LLM сверяет с эталоном и оценивает, допускается частичное совпадение), и `single_choice`, и `multi_choice` (несколько правильных). Реализовано.

## 6. Разделение записи в БД

| Таблица | Кто пишет |
|---|---|
| `material_chunks` | **ML** (чанки + эмбеддинги) |
| `materials.status_material` | backend (по результату `ingest`) |
| `tests`, `test_questions` | backend |
| `tests.status_test` | backend (по результату `create_test`) |
| `test_questions.answer_key` | backend (из `answer_key` в ответе ML, §3.4) |
| `student_attempts`, `attempt_answers` | backend (ответы студента) |
| `student_attempts.score_pct/grade/finished_at`, `attempt_answers.score/feedback/is_correct/correct_answer` | backend (по вердикту ML) |

ML в таблицы `tests`, `test_questions`, `student_attempts`, `attempt_answers` не пишет.

Эталоны правильных ответов лежат **в БД backend'а** (`test_questions.answer_key` — заполняет backend из ответа ML) и **в Redis ML** (`ml:answers:{test_id}`, TTL 30 дней) как резервная копия. При проверке приоритет: БД → Redis → LLM-судья (§0.3, §3.4).

## 7. HTTP-слой

Синхронного HTTP между backend и ML нет — только Redis Streams. Все эндпоинты асинхронные: работа идёт через очередь, клиент опрашивает GET.

| Метод | Путь | Ответ |
|---|---|---|
| `POST` | `/api/tests` | 202 — создание теста, задача ушла в ML |
| `GET` | `/api/tests/{id}` | 200 — тест с вопросами (в статусе `READY`) |
| `POST` | `/api/tests/{id}/attempts` | 202 — попытка создана, ждём вердикт |
| `GET` | `/api/attempts/{id}` | 200 — попытка (`processing` / `graded`) |

## 8. Схема БД: факт и отклонения

Сейчас применены миграции `001-initial-schema.sql`, `002`, `003`, `004-query-tasks.sql`, `005-materials-test.sql`. Релевантные таблицы:

```sql
tests(test_id PK, course_id NOT NULL, title NOT NULL, amount_questions VARCHAR(50) NOT NULL,
      status_test NOT NULL, difficulty DEFAULT 'medium', created_at)

test_questions(question_id PK, test_id NOT NULL, type_question NOT NULL, text_question NOT NULL,
                options JSONB, key_points JSONB, source_chunk_id UUID NULL, created_at)

attempt_answers(answer_id PK, attempt_id NOT NULL, question_id NOT NULL,
                is_correct BOOLEAN NOT NULL, student_answer JSONB NOT NULL,
                correct_answer JSONB NOT NULL, score NUMERIC(3,2), feedback TEXT, created_at)
```

| Что | ERD заказчика | Миграции (факт) | Кто решает |
|---|---|---|---|
| `test_questions.answer_key` | есть | **нет** — колонку добавляет **backend своей миграцией** (`ADD COLUMN answer_key JSONB`) | **Backend**: с v4.1 ML отдаёт эталон в `answer_key` каждого вопроса (§0.3, §3.4) — backend пишет его в эту колонку. Требование к миграции: `test_questions.answer_key JSONB` |
| `test_questions.question_order` | **нет** | **нет** — надо добавить | **Backend**, осознанное отклонение от ERD, требует письменного согласования: без порядка вопросы выводятся в порядке случайных UUID, а `id` из ответа ML — это ординал. Требование к миграции: `test_questions.question_order INT` |
| `attempt_answers.is_correct` | **нет** | **есть, NOT NULL** — заполняется из `items[].is_correct` | Backend: снять NOT NULL миграцией либо писать заглушку и обновлять из вердикта |
| `attempt_answers.correct_answer` | **нет** | **есть, NOT NULL** — заполняется из `items[].correct_answer` | То же |
| `tests.difficulty` | есть | есть | — |
| `query_tasks`, `query_tasks_materials` | есть | есть (004) | — |
| `course_students` | нет | нет | Продуктовое решение: доступ к курсу — по `courses.owner_id`, попытку может сдать только владелец курса |

## 9. Обязанности backend — чек-лист

1. Публиковать в `<тип-задачи>:be-to-ml` с конвертом `payload '<JSON>'`, без поля `type`.
2. `ingest`: ровно два поля — `material_id`, `storage_key`.
3. `create_test`: `task_id`, `test_id`, `material_ids` (непустой список), `title`, `difficulty` — `easy|medium|hard`. **Поля `amountQuestions` нет** — число вопросов определяет ML планировщиком.
4. `grade_test`: `task_id`, `attempt_id`, `test_id`, `answers[]` — `{question_id, student_answer}`, где `student_answer` — `{index}` | `{indexes}` | `{text}` по типу вопроса.
5. Писать `options` / `key_points` as-is, не пересобирая.
6. **Писать `answer_key` из ответа ML в `test_questions.answer_key`** (JSONB) — эталон правильного ответа по каждому вопросу (§0.3, §3.4). Backend без него не может показать студенту правильный ответ.
7. **Число вопросов определяет ML; backend пишет `tests.amount_questions = len(questions)`** — по фактической длине массива вопросов из ответа.
8. `source_chunk_id` — `NULL`, если чанка нет в `material_chunks`.
9. Писать `attempt_answers` (с `student_answer`) **до** публикации задачи в ML.
10. Заполнять `is_correct` и `correct_answer` из `items[]` вердикта.
11. `XACK` — только после успешной обработки; при исключении не подтверждать.
12. `XACK` — в тот же канал, откуда пришло сообщение.
13. Идемпотентность: вопросы — по детерминированному `question_id`, строки ответов — по `answer_id`, вердикт — `UPDATE` по `attempt_id` + `question_id`.
14. В `grade-test:ml-to-be` признак ошибки — наличие `error`, а не `status`.
15. **Миграция backend'а:** добавить `test_questions.answer_key JSONB` и `test_questions.question_order INT` (§8). Без них ML работает (фолбэк на Redis и LLM-судью), но backend не может показать правильный ответ, а вопросы выдаются в случайном порядке.

## 10. Известные ограничения

- **Backend не делает reclaim.** Сообщение, застрявшее в pending канала результатов, нужно забрать вручную (`XCLAIM`) или переиграть. На стороне ML reclaim есть (`XAUTOCLAIM`, `reclaim_idle_ms`).
- **`source_chunk_id` может быть `null`.** ML отдаёт UUID чанка, но если векторное хранилище было in-memory или материал переиндексировали — чанка в БД нет, backend пишет `NULL`.
- **Эталоны лежат в двух местах.** Основное — `test_questions.answer_key` в БД backend'а (её заполняет backend из ответа ML); резервное — `ml:answers:{test_id}` в Redis ML (TTL 30 дней). Если backend не выполнил требование по миграции и не пишет эталон в БД, ML при проверке идёт в Redis, а если Redis очищен — к LLM-судье; качество может отличаться от эталонного (замер: судья назвал 2 правильных варианта вместо 3).
- **Нет модели «зачисление на курс».** Попытку может сдать только владелец курса. Для сдачи студентом нужен отдельный механизм (в ERD его нет).
- **`rag_question` вне контракта.** Код в ML жив (`RAGQuestionTask`), но backend его не использует и канал не подписывает.
- **`query_tasks` не участвует в потоке.** Задача создаётся и уходит в ML напрямую; таблица используется как журнал.

## 11. Где что лежит

### ML (`ml/`)

| Файл | Роль |
|---|---|
| `app/contracts.py` | Источник правды по payload'ам: dataclass'ы задач и результатов, `parse_task()`, `task_channel()` / `result_channel()` |
| `app/handlers/rag.py` | Handler'ы: `process_ingest`, `process_question`, `process_create_test`, `process_grade_attempt` |
| `app/workers/rag.py` | Redis-цикл: `XREADGROUP` по всем каналам, `XAUTOCLAIM`, `XADD` результата, `XACK` |
| `app/services/answer_store.py` | Хранилище эталонов в Redis: `ml:answers:{test_id}`, поиск по нормализованному тексту вопроса (резервная копия, §3.4) |
| `app/services/choice_judge.py` | LLM-фолбэк: определить правильные варианты, если эталона нет ни в БД, ни в Redis |
| `app/services/test_planner.py` | Размер теста и темы: `plan_test(llm, digest, difficulty)` → `num_questions` (1..30) + список тем |
| `app/services/test_generator.py` | Генерация теста: микс типов, JSON Schema, привязка к чанкам |
| `app/services/grader.py` | Проверка: `single_choice`, `multi_choice` — детерминированно; эталон — БД → Redis → LLM-судья |
| `app/services/open_answer_judge.py` | LLM-судья для `open_answer` |
| `app/services/test_store.py` | Чтение `test_questions` из Postgres |

### Backend (требования — в этой ветке этих файлов нет)

Backend-часть контракта реализуется на стороне backend-разработчика. Таблица ниже — **не описание существующих файлов**, а список того, что должно появиться и за что отвечает. Формулировки «данные, а не код» — в `ml/docs/backend-tz-contract-v4.md`.

| Что должно быть у backend'а | Роль |
|---|---|
| Словарь имён каналов + consumer group | `ingest:be-to-ml` / `create-test:be-to-ml` / `grade-test:be-to-ml`, группа `ml-workers`; три канала результатов `…:ml-to-be`, своя группа на каждом |
| Продюсер задач | `XADD <канал> * payload '<JSON>'`, без поля `type` |
| Record'ы результатов ML | `IngestResult`, `CreateTestResult` (с вопросами), `GradeAttemptResult` (с items, **без** `status`) — по схемам из `ml/docs/contracts/` |
| Подписка на результаты | Три канала `…:ml-to-be`, группы с `MKSTREAM`, чтение с `>` |
| Listener'ы | `ingest` → `materials.status_material`; `create_test` → `test_questions` + `tests.status_test`; `grade_attempt` → `student_attempts` + `attempt_answers`. `XACK` — только после успешной записи |
| Сдача попытки | `student_attempts` + `attempt_answers` создаются **до** публикации задачи, затем 202 Accepted |
| Миграция | `test_questions.answer_key JSONB` (эталон из ответа ML) и `test_questions.question_order INT` (порядок вопроса); решение по `attempt_answers.is_correct`/`correct_answer` (NOT NULL) |

## 12. Предыдущие версии

| Версия | Файл | Что было |
|---|---|---|
| design | `ml/docs/superpowers/specs/2026-10-22-ml-backend-contract-design.md` | Первая договорённость: три канала вместо одного, ML пишет только `material_chunks` |
| v2 | ветка `back-ml-connect-2` | Наш прежний вариант: `num_questions`, плоские `correct_index`/`student_answer_index`, `overall_feedback` |
| v3 | ветка `back-ml-connect-2` | Контракт тиммейта, приведённый к ERD: `amountQuestions`, `type`, `answer_key`, `status` в результате |
| v4 | `ml/docs/superpowers/specs/2026-11-17-ml-backend-contract-v4.md` | Контракт заказчика: каналы переименованы, `status` убран из grade-ответа, `amountQuestions` допускал число или `"min"`, `answer_key` наружу не отдавался |
| **v4.1** | тот же файл, §0.3 | `amountQuestions` убран из задачи (размер всегда выбирает ML); `answer_key` возвращён в ответ `create_test`; приоритет эталона БД → Redis → LLM-судья |

v4.1 — финальная: она описывает **контракт заказчика**, реализованный в ветке `ml/redis-jobs`, и требования к backend'у, с которыми он должен сойтись.
