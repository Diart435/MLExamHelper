# ТЗ для backend-разработчика: приём ML-задач и результатов (контракт v4)

**Зачем документ.** ML-сторона готова: воркер читает Redis Streams, генерирует тесты, проверяет попытки и отвечает. Backend должен научиться публиковать задачи в каналы и принимать результаты. Ниже — требования к backend'у, сформулированные как контракт, а не как готовый код: реализация (имена классов, слои, DTO) — на ваше усмотрение.

**Источник правды по формату сообщений — `ml/app/contracts.py`.** Если сомневаетесь в поле или его типе — смотрите туда, а не в этот документ. Полная спека с обоснованием: `ml/docs/superpowers/specs/2026-11-17-ml-backend-contract-v4.md`.

**Машино-читаемые схемы.** Все шесть контрактов (3 типа задач × 2 направления) описаны JSON Schema draft 2020-12 в `ml/docs/contracts/` — по файлу на канал, плюс канонические примеры payload'ов в `ml/docs/contracts/examples/`. Примеры сгенерированы из `ml/app/contracts.py`, тест `ml/tests/test_contract_schema.py` следит, чтобы они не разъехались с кодом. Можно валидировать свои сообщения по схеме на своей стороне.

---

## 1. Транспорт

**1.1. Один тип задачи — один канал.** Тип задачи задаёт **имя канала**, отдельного поля `type` в сообщении нет.

Имя канала: `<тип-задачи>:<направление>`, где направление — `be-to-ml` (backend → ML) или `ml-to-be` (ML → backend).

| Направление | Каналы | Consumer-группа | Кто читает |
|---|---|---|---|
| backend → ML | `ingest:be-to-ml`, `create-test:be-to-ml`, `grade-test:be-to-ml` | `ml-workers` | ML-воркер |
| ML → backend | `ingest:ml-to-be`, `create-test:ml-to-be`, `grade-test:ml-to-be` | своя у backend'а (предложение: `ml-backend`) | backend |

Имена каналов — **константы контракта**: обе стороны задают их одинаково в коде, без env-переменных. Так ML и backend не могут разойтись по названию стрима (конфигурируемый префикс расходится тихо и ловится только на проде). Если стримы нужно переименовать — это правка контракта для обеих сторон сразу.

Готовые машинно-читаемые схемы всех шести контрактов (JSON Schema draft 2020-12) лежат в `ml/docs/contracts/` — там же канонические примеры payload'ов. Ориентироваться на них, а не на этот документ: **источник правды — `ml/app/contracts.py`**.

**1.2. Конверт сообщения.** Ровно одно поле:

```
XADD <канал> * payload '<JSON одной строкой>'
```

**1.3. Подписка.** Backend читает **три** канала результатов. Consumer-группа привязана к одному стриму, поэтому группу создают на **каждом** канале: `MKSTREAM` (канал появляется на лету), `BUSYGROUP` при повторном создании — норма, её надо проглатывать. Читать с `lastConsumed` (`>`), чтобы сообщения, опубликованные пока backend лежал, не потерялись.

**1.4. Подтверждение.** `XACK` — **только после успешной записи в БД** и **в тот же канал, откуда пришло сообщение**. При исключении при обработке — не подтверждать: сообщение остаётся в pending (его можно переиграть вручную `XCLAIM`).

**1.5. Ошибка — это нормальный ответ.** ML отвечает на **каждое** полученное сообщение, в том числе на битый JSON и на любое исключение:

```json
{"task_id": "...", "status": "error", "error": "текст ошибки"}
```

Успех — `status:"ok"`, для `ingest` — `status:"ready"`. Backend обязан обрабатывать `status:"error"` без падения и **применить его к нужной строке**: по `material_id` (если он есть) перевести материал в «ошибка», по `test_id` — тест, по `attempt_id` — **попытку не трогать** (оставить в статусе «обрабатывается»), только залогировать.

В ветке `status:"error"` идентификаторы могут отсутствовать: если payload не удалось разобрать, ML не знает ни о каком материале/тесте/попытке речь. Поэтому **обязателен только `error`**, а `task_id`/`material_id`/`test_id`/`attempt_id` — необязательные (backend читает их, если они есть, и не падает, если их нет).

**1.6. Идемпотентность обязательна.** Доставка — «хотя бы один раз»: ML может упасть между `XADD` результата и `XACK` и выполнить задачу заново. Повторная обработка результата не должна ни плодить дубли вопросов, ни ломать уже записанный вердикт.

**1.7. Где живёт разбор payload'ов.** Отдельный верхнеуровневый пакет `ml` в backend'е **не нужен и не создаётся**: в Spring Modulith верхнеуровневый пакет — это модуль, и отдельный «ml-модуль» тянет за собой объявления зависимостей и риск циклов в графе модулей. Словарь payload'ов (record'ы результатов ML, имена каналов) размещайте внутри существующих модулей backend'а — там, где уже лежат обработчики и продюсеры сообщений (например `jobs` и `messaging`). Названия типов и методов — на ваше усмотрение; важно лишь то, чтобы форма разбора соответствовала `ml/app/contracts.py`.

**1.8. Лишнее поле в результатах.** К каждому результату ML добавляет `input_msg_id` — id исходного сообщения в Redis (служебная корреляция). Backend его **игнорирует**, но и **не отвергает** сообщение из-за него: в JSON-схемах он помечен как необязательное поле.

---

## 2. Задачи: что backend отправляет ML

### 2.1. `ingest` — разобрать материал

```json
{"task_id": "8f1b…", "material_id": "5a2c…", "storage_key": "uploads/lec.pdf"}
```

- `material_id` — **обязательно**, UUID **строкой** (не число);
- `storage_key` — **обязательно**: путь объекта внутри бакета, ML скачивает сам;
- `task_id` — необязательно (корреляция), но лучше присылать.

Ответ ML:

```json
{"task_id": "8f1b…", "material_id": "5a2c…", "status": "ready", "chunks_indexed": 29}
{"task_id": "8f1b…", "material_id": "5a2c…", "status": "error", "error": "unsupported format: .xyz"}
```

**Кто что пишет в БД:** backend — только `materials.status_material`; **чанки в `material_chunks` пишет сам ML**. Backend не вставляет строки в `material_chunks` и не ждёт их появления перед `create_test` — к моменту генерации они уже там.

### 2.2. `create_test` — сгенерировать тест

```json
{"task_id": "3655…", "test_id": "5780…", "material_ids": ["78f2…"], "title": "Модели",
 "amountQuestions": 10, "difficulty": "medium", "course_id": "b7fa…"}
```

- `task_id`, `test_id`, `material_ids` (непустой список UUID-строк), `title` — обязательны;
- `amountQuestions` — **необязательно**: целое **1..30** («ровно столько вопросов») либо строка `"min"` / `"auto"` / пустая строка / отсутствие поля («размер выбирает ML сам по материалу»). Вне диапазона ML отвечает `status:"error"`;
- `difficulty` — `easy` | `medium` | `hard`, по умолчанию `medium`. **Микс типов вопросов считает ML** — backend своей логики микса не реализует.

Ответ ML:

```json
{"task_id": "3655…", "status": "ok", "test_id": "5780…",
 "test": {"title": "Модели", "questions": [
   {"id": 1, "type": "single_choice", "text": "…", "options": ["A","B","C","D"],
    "answer_key": {"correct_index": 0, "explanation": "Потому что"},
    "key_points": [], "source_chunk_id": "05a801d9-…"}]}}
```

Ошибка: `{"task_id": "…", "status": "error", "test_id": "5780…", "error": "…"}` — в ветке ошибки обязателен только `error`; `test_id` может отсутствовать (тогда backend не знает, какой тест переводить в «ошибка» — только логирует).

**Что backend обязан записать в `test_questions`** — по строке на вопрос, один-в-один, без пересборки и повторной валидации (ML уже проверил):

| Поле ответа ML | Куда в БД |
|---|---|
| `type` | `type_question` |
| `text` | `text_question` |
| `options` | `options` (JSONB) |
| `answer_key` | `answer_key` (JSONB) |
| `key_points` | `key_points` (JSONB) |
| `source_chunk_id` | `source_chunk_id` (UUID, **nullable**) |
| `id` | **не сохраняется** — это порядковый номер |

Плюс: колонка порядка вопроса (предложение — `question_order INT`), см. §4.2. И `tests.status_test` → «готов» (или «ошибка»).

**`source_chunk_id`:** ML присылает **UUID чанка** (метки `C1`, `C2` живут только в промпте, ML разворачивает их в UUID). Если чанка нет в `material_chunks` — писать `NULL`, **не ронять вставку по FK**.

### 2.3. `grade_attempt` — проверить попытку

```json
{"task_id": "3b17…", "attempt_id": "dc12…", "test_id": "5780…", "user_id": "2c9e…",
 "answers": [
   {"question_id": "05a8…", "student_answer": {"index": 0}},
   {"question_id": "06b1…", "student_answer": {"indexes": [0, 2]}},
   {"question_id": "07c3…", "student_answer": {"text": "мой ответ"}}]}
```

- `task_id`, `attempt_id`, `test_id`, `user_id` (все — UUID-строки) и `answers` (непустой список) обязательны;
- `student_answer` — **ровно один** вид, по типу вопроса: `{index}` — `single_choice`, `{indexes}` — `multi_choice`, `{text}` — `open_answer`. Плоские `student_answer_index` / `student_answer_indexes` / `student_answer_text` ML принимает как legacy, но канонична вложенная форма;
- `question_id` — это id из `test_questions` (не порядковый номер). ML читает вопросы из БД сам.

**Порядок действий backend'а при сдаче попытки (важно!):**

1. Тест должен быть в статусе «готов» — иначе 400, а не 202;
2. создать `student_attempts`: `started_at = now()`, `finished_at` / `score_pct` / `grade` — `NULL`;
3. создать `attempt_answers` — по строке на ответ: `student_answer` (типизированный JSONB), `score` / `feedback` — `NULL`;
4. **только потом** опубликовать задачу в `grade-test:be-to-ml`;
5. ответить клиенту **202 Accepted**, попытка в статусе «обрабатывается».

Если публиковать раньше записи строк, вердикт может прийти раньше, чем backend сможет его записать.

Ответ ML:

```json
{"task_id": "3b17…", "status": "ok", "attempt_id": "dc12…", "test_id": "5780…",
 "score_pct": 60.0, "grade": 3,
 "items": [{"question_id": "05a8…", "is_correct": true, "score": 1.0,
            "feedback": "Верно", "correct_answer": "Текст варианта", "student_answer": "Текст ответа"}]}
```

Ошибка: `{"task_id": "…", "status": "error", "attempt_id": "dc12…", "test_id": "5780…", "error": "…"}` — обязателен только `error`; `attempt_id` и `test_id` могут отсутствовать, если payload не удалось разобрать.

**Как применять вердикт:** по каждому item — `attempt_answers.score` ← `score`, `attempt_answers.feedback` ← `feedback` (по `question_id`); затем `student_attempts.finished_at` ← now, `score_pct` ← `score_pct`, `grade` ← `grade`. При `status:"error"` попытку не трогать. Повторный вердикт перезаписывает те же строки.

**Шкала:** `score_pct` — процент по **всем** вопросам теста (пропущенный = 0), округление до 2 знаков. `grade`: ≥90 → 5, ≥70 → 4, ≥50 → 3, иначе 2.

---

## 3. Формат данных

**3.1. `answer_key` зависит от типа вопроса** (`explanation` есть у всех типов и лежит внутри `answer_key`):

| `type` | `answer_key` | `key_points` | `options` |
|---|---|---|---|
| `single_choice` | `{"correct_index": N, "explanation": "…"}`, N — индекс с нуля | `[]` | 2–4 строки |
| `multi_choice` | `{"correct_indexes": [N, M…], "explanation": "…"}`, 2–3 индекса | `[]` | 4–6 строк |
| `open_answer` | `{"reference_answer": "эталон", "explanation": "…"}` | 2–4 строки | `[]` |

`key_points` — **плоский список строк** (критерии для `open_answer`). `true_false` ML не генерирует и не проверяет.

**3.2. `is_correct` = `score ≥ 0.5`.** Колонок `is_correct` / `correct_answer` в `attempt_answers` быть не должно — их нет в ERD заказчика. Backend выводит их **при чтении**: `isCorrect` = `score ≥ 0.5`; `correctAnswer` = из `answer_key` + `options` вопроса (`correct_index` → `options[i]`, `correct_indexes` → склейка вариантов, иначе `reference_answer`).

---

## 4. Схема БД

**4.1. Обязательно (это читает или пишет ML):**

- `test_questions.answer_key` (JSONB) — **ML читает эту колонку** при проверке попытки. Без неё проверка не работает вовсе;
- `test_questions.key_points` (JSONB) и `options` (JSONB) — ML читает;
- `material_chunks`: `chunk_id` UUID PK, `material_id` UUID FK, `text_chunk`, `embedding vector(1536)`, `created_at` — **ML пишет сам**, детерминированным UUID, поэтому повторный ingest перезаписывает те же строки, а не плодит дубли. Права: пользователю ML нужен `INSERT` в `material_chunks` и `SELECT` в `test_questions`;
- `attempt_answers`: `student_answer` (JSONB, типизированный), `score`, `feedback`; `student_attempts`: `started_at`, `finished_at`, `score_pct`, `grade`.

**4.2. На усмотрение backend'а (ML это не читает, но для удобства нужно):**

- колонка порядка вопроса в `test_questions` (предложение — `question_order INT`). **В ERD её нет** — это отклонение от схемы заказчика, его надо письменно согласовать;
- детерминированный `question_id` (предложение — `uuid5(test_id, "q:" + порядковый номер)`): гарантирует, что повторный результат не создаст дубль вопросов. Конкретная формула — на ваше усмотрение, важна детерминированность.

**4.3. Убрать:** колонки `attempt_answers.is_correct` и `attempt_answers.correct_answer` — в ERD заказчика их нет.

---

## 5. Чего backend НЕ должен делать

- пересобирать, «приводить к своему виду» и заново валидировать `answer_key` / `key_points` / `options` — ML уже проверил;
- считать микс типов вопросов — это зона ML;
- публиковать сообщения без поля `payload` или с полем `type`;
- писать в `material_chunks` — это делает ML;
- определять тип задачи по `task_id` — только по имени канала;
- отправлять `grade_attempt` раньше, чем записаны `student_attempts` и `attempt_answers`;
- использовать старые имена каналов `ml-tasks:<type>` / `ml-results:<type>` — они больше не существуют, ML их не слушает;
- делать синхронный HTTP-запрос в ML — транспорт только Redis Streams, HTTP-эндпоинты клиента возвращают **202 Accepted** и статус проверяется опросом `GET`.

---

## 6. Чек-лист приёмки

| # | Что проверить | Как |
|---|---|---|
| 1 | Задача уходит в правильный канал и в одном поле | `redis-cli XRANGE create-test:be-to-ml - + COUNT 1` → ровно одно поле `payload` |
| 2 | Backend подписан на все три результата | `redis-cli XINFO GROUPS create-test:ml-to-be` |
| 3 | Ошибка от ML не роняет backend, а ставит нужную строку в «ошибка» | отправить в `create-test:be-to-ml` заведомо битый payload → в `create-test:ml-to-be` придёт `status:"error"` |
| 4 | `XACK` — после успешной записи, в исходном канале | `redis-cli XPENDING create-test:ml-to-be` после искусственно брошенного исключения |
| 5 | Материал проиндексирован | `SELECT count(*) FROM material_chunks WHERE material_id::text = '<id>'` > 0 |
| 6 | Вопросы записаны как есть, порядок стабилен | `SELECT type_question, answer_key FROM test_questions WHERE test_id=… ORDER BY question_order` |
| 7 | Вопрос с несуществующим чанком сохранился, `source_chunk_id` = NULL | вставить вопрос с чужой меткой → строка есть, FK не упал |
| 8 | Повторный результат не удвоил вопросы | обработать один и тот же результат дважды → `count(*)` не изменился |
| 9 | Попытка создаётся до публикации задачи | после сдачи: строки в `student_attempts` и `attempt_answers` есть, `score` = NULL, попытка в статусе «обрабатывается» |
| 10 | Вердикт применился | после ответа ML: `finished_at` заполнен, `score_pct` и `grade` совпадают с ответом, `GET` попытки отдаёт «проверена» |
| 11 | `multi_choice` с частичными отметками | ответ `{indexes:[0,2]}` → дробный `score`; `{index}` на `open_answer` → `status:"error"` |
| 12 | В схеме нет `is_correct` / `correct_answer` | `\d attempt_answers`; `GET` попытки всё равно отдаёт `isCorrect` / `correctAnswer` |
