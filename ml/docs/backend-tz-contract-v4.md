# ТЗ для backend-разработчика: приём ML-задач и результатов (контракт v4.1)

**Зачем документ.** ML-сторона готова: воркер читает Redis Streams, генерирует тесты, проверяет попытки и отвечает на **каждое** сообщение. Backend должен публиковать задачи в каналы и раскладывать результаты в БД. Ниже — требования к backend'у, сформулированные как контракт, а не как готовый код: имена классов, слои и DTO — на ваше усмотрение.

**Источник правды по формату сообщений — `ml/app/contracts.py`.** Если сомневаетесь в поле или его типе — смотрите туда, а не в этот документ. Полная спека с обоснованием: `ml/docs/superpowers/specs/2026-11-17-ml-backend-contract-v4.md`.

**Машино-читаемые схемы.** Все шесть контрактов (3 типа задач × 2 направления) описаны JSON Schema draft 2020-12 в `ml/docs/contracts/` — по файлу на канал, плюс канонические примеры payload'ов в `ml/docs/contracts/examples/`. Примеры сгенерированы из `ml/app/contracts.py`, тест `ml/tests/test_contract_schema.py` следит, чтобы они не разъехались с кодом. Свои сообщения можно валидировать по схемам на своей стороне.

**Состояние схемы БД** в этом документе — по миграциям `backend/src/main/resources/db/changelog/changes/001…005-materials-test.sql` (то, что реально применено сейчас). Расхождения с ERD заказчика (`ml/docs/erd.png`) выписаны явно в §4.

---

## 0. Что изменилось относительно прежних черновиков ТЗ

| Что | Было | Стало |
|---|---|---|
| `amountQuestions` в задаче `create-test` | необязательное целое 1..30 **или** строка `"min"` | **поля нет.** Размер теста всегда выбирает ML планировщиком; backend пишет `tests.amount_questions = len(questions)` по ответу |
| `answer_key` в ответе `create-test` | **ML не отдавал эталон.** В вопросе только `id, type, text, options, key_points, source_chunk_id` | **ML отдаёт эталон в каждом вопросе:** `answer_key` = `{correct_index}` \| `{correct_indexes}` \| `{reference_answer}` (+ необязательный `explanation`). Backend пишет его в `test_questions.answer_key` |
| `status` в ответе `grade-test` | `{"status": "ok", …}` | **поля `status` нет.** Признак ошибки — само наличие ключа `error` |
| `task_id` в задаче `ingest` | был | **нет.** Корреляция в ingest — по `material_id` |
| `user_id` в задаче `grade-test` | требовался | **не требуется.** Студент известен backend'у по `attempt_id` |
| `chunks_indexed` в ответе `ingest` | был | **нет** |
| `input_msg_id`, `course_id` | были | **нет** ни в одном payload'е |

Три первых пункта — правка **v4.1** (2026-11-17), обоснование — в спеке `ml/docs/superpowers/specs/2026-11-17-ml-backend-contract-v4.md` §0.3. Главное для backend'а: `answer_key` теперь приходит в ответе и его надо сохранить — без эталона frontend не может показать студенту правильный ответ.

В переписке заказчик местами писал «injest» и «rate-test» — это опечатки. Канонические имена каналов — как в таблице §1.1.

---

## 1. Транспорт

**1.1. Один тип задачи — один канал.** Тип задачи задаёт **имя канала**, отдельного поля `type` в сообщении нет.

Имя канала: `<тип-задачи>:<направление>`, где направление — `be-to-ml` (backend → ML) или `ml-to-be` (ML → backend).

| Направление | Каналы | Consumer-группа | Кто читает |
|---|---|---|---|
| backend → ML | `ingest:be-to-ml`, `create-test:be-to-ml`, `grade-test:be-to-ml` | `ml-workers` | ML-воркер |
| ML → backend | `ingest:ml-to-be`, `create-test:ml-to-be`, `grade-test:ml-to-be` | своя у backend'а (предложение: `ml-backend`) | backend |

Имена каналов — **константы контракта**: обе стороны задают их одинаково в коде, без env-переменных. Так ML и backend не могут разойтись по названию стрима (конфигурируемый префикс расходится тихо и ловится только на проде). Если стримы нужно переименовать — это правка контракта для обеих сторон сразу.

> В коде ML есть ещё один канал — `rag-question:be-to-ml` (legacy-ветка «вопрос по материалу»). Он не входит в контракт заказчика: backend его публиковать не обязан, но если опубликует — ML ответит в `rag-question:ml-to-be`.

**1.2. Конверт сообщения.** Ровно одно поле:

```
XADD <канал> * payload '<JSON одной строкой>'
```

**1.3. Подписка.** Backend читает **три** канала результатов. Consumer-группа привязана к одному стриму, поэтому группу создают на **каждом** канале: `MKSTREAM` (канал появляется на лету), `BUSYGROUP` при повторном создании — норма, её надо проглатывать. Читать с `>`: непрочитанные сообщения, опубликованные пока backend лежал, останутся в стриме и доедут при следующем чтении.

**1.4. Подтверждение.** `XACK` — **только после успешной записи в БД** и **в тот же канал, откуда пришло сообщение**. При исключении при обработке — не подтверждать: сообщение остаётся в pending (его можно переиграть вручную `XCLAIM`).

**1.5. Ошибка — это нормальный ответ.** ML отвечает на **каждое** полученное сообщение, в том числе на битый JSON и на любое исключение. Форма ответа зависит от канала:

| Канал ответа | Успех | Ошибка |
|---|---|---|
| `ingest:ml-to-be` | `{"material_id": "…", "status": "ready"}` | `{"status": "error", "error": "текст", "material_id": "…"}` — `material_id` может отсутствовать |
| `create-test:ml-to-be` | `{"task_id": "…", "status": "ok", "test_id": "…", "test": {…}}` | `{"task_id": "…", "status": "error", "error": "текст", "test_id": "…"}` — `test_id` может отсутствовать |
| `grade-test:ml-to-be` | `{"task_id": "…", "attempt_id": "…", "test_id": "…", "score_pct": 60.0, "grade": 3, "items": […]}` — **поля `status` нет** | `{"task_id": "…", "error": "текст"}` — **поля `status` нет**, `attempt_id`/`test_id` могут отсутствовать |

Backend обязан обрабатывать ошибку без падения и **применить её к нужной строке**: по `material_id` (если он есть) перевести материал в «ошибка», по `test_id` — тест, по `attempt_id` — **попытку не трогать** (оставить в статусе «обрабатывается»), только залогировать.

В ветке ошибки идентификаторы могут отсутствовать: если payload не удалось разобрать, ML не знает ни о каком материале/тесте/попытке речь. Поэтому **обязателен только `error`**, а идентификаторы — необязательные (backend читает их, если они есть, и не падает, если их нет).

> Признак ошибки в `grade-test:ml-to-be` — **наличие ключа `error`**, а не значение `status`. Backend не должен ждать `status` в этом канале: его там нет, и проверка «`status == "ok"`» всегда будет ложной.

**1.6. Идемпотентность обязательна.** Доставка — «хотя бы один раз»: ML может упасть между `XADD` результата и `XACK` и выполнить задачу заново. Повторная обработка результата не должна ни плодить дубли вопросов, ни ломать уже записанный вердикт. См. §4.2 — детерминированные `question_id` и `answer_id`.

**1.7. Где живёт разбор payload'ов.** Отдельный верхнеуровневый пакет `ml` в backend'е **не нужен и не создаётся**: в Spring Modulith верхнеуровневый пакет — это модуль, и отдельный «ml-модуль» тянет за собой объявления зависимостей и риск циклов в графе модулей. Словарь payload'ов (record'ы результатов ML, имена каналов) размещайте внутри существующих модулей backend'а — там, где уже лежат обработчики и продюсеры сообщений (например `jobs` и `messaging`). Названия типов и методов — на ваше усмотрение; важно лишь то, чтобы форма разбора соответствовала `ml/app/contracts.py`.

**1.8. Никаких лишних полей.** В сообщениях ML **нет** служебных полей: `input_msg_id`, `course_id`, `chunks_indexed`, а в `grade-test:ml-to-be` — и `status`. Backend не должен рассчитывать на наличие каких-либо дополнительных полей — разбирать ровно перечисленные в §2 и §3. Отдельно: `answer_key` в ответе `create-test:ml-to-be` **есть** — это эталон правильного ответа по каждому вопросу (§2.2), его надо писать в `test_questions.answer_key`.

> **Про сам Redis — отдельный документ:** `ml/docs/backend-redis-requirements.md`. Здесь (§1) — контракт сообщений; там — конфигурация Redis в backend'е, группы и подтверждения, reclaim зависших сообщений, уборка стримов, и разбор расхождений текущего кода backend'а с этим контрактом.

---

## 2. Задачи: что backend отправляет ML

### 2.1. `ingest` — разобрать материал

```json
{"material_id": "5a2c…", "storage_key": "materials/5a2c…/lecture.pdf"}
```

- `material_id` — **обязательно**, UUID **строкой** (не число);
- `storage_key` — **обязательно**: путь объекта внутри бакета, ML скачивает сам;
- это **ровно два поля** — никакого `task_id` в ingest-задаче нет.

Ответ ML:

```json
{"material_id": "5a2c…", "status": "ready"}
{"status": "error", "error": "unsupported format: .xyz", "material_id": "5a2c…"}
```

**Кто что пишет в БД:** backend — только `materials.status_material` (`ready` при успехе, `error` при ошибке); **чанки в `material_chunks` пишет сам ML**. Backend не вставляет строки в `material_chunks` и не ждёт их появления перед `create_test` — к моменту генерации они уже там.

### 2.2. `create-test` — сгенерировать тест

```json
{"task_id": "3655…", "test_id": "5780…", "material_ids": ["78f2…"], "title": "Модели",
 "difficulty": "medium"}
```

- `task_id`, `test_id`, `material_ids` (непустой список UUID-строк), `title` — обязательны;
- **`amountQuestions` в задаче нет** (v4.1). Размер теста определяет ML: отдельный LLM-вызов планировщика (`app/services/test_planner.py`, `plan_test(llm, digest, difficulty)`) смотрит на материал и возвращает `num_questions` (1..30) + список тем. Backend присылает только `task_id`, `test_id`, `material_ids`, `title`, `difficulty`;
- `difficulty` — `easy` | `medium` | `hard`, по умолчанию `medium`. **Микс типов вопросов считает ML** — backend своей логики микса не реализует;
- `course_id` в payload'е **нет** — связь теста с курсом backend хранит у себя.

Ответ ML:

```json
{"task_id": "3655…", "status": "ok", "test_id": "5780…",
 "test": {"title": "Модели", "questions": [
   {"id": 1, "type": "single_choice", "text": "…", "options": ["A","B","C","D"],
    "key_points": null, "source_chunk_id": "05a801d9-…",
    "answer_key": {"correct_index": 2, "explanation": "…"}}]}}
```

Вопрос различается по полю `type`: `single_choice`, `multi_choice`, `open_answer`.

**`answer_key` — эталон правильного ответа, по объекту на вопрос.** Формат по типу:

| `type` | `answer_key` |
|---|---|
| `single_choice` | `{"correct_index": N}` |
| `multi_choice` | `{"correct_indexes": [N, M]}` |
| `open_answer` | `{"reference_answer": "<эталон>"}` |

Плюс необязательный `explanation` — короткое пояснение к правильному ответу, лежит в том же объекте. Backend пишет объект **as-is** в `test_questions.answer_key` (JSONB) — колонка есть в ERD заказчика, но в текущих миграциях её нет, её надо добавить (§4.1).

Ошибка: `{"task_id": "…", "status": "error", "test_id": "5780…", "error": "…"}` — в ветке ошибки обязателен только `error`; `test_id` может отсутствовать (тогда backend не знает, какой тест переводить в «ошибка» — только логирует).

**Что backend обязан записать в `test_questions`** — по строке на вопрос, один-в-один, без пересборки и повторной валидации (ML уже проверил):

| Поле ответа ML | Куда в БД |
|---|---|
| `type` | `type_question` |
| `text` | `text_question` |
| `options` | `options` (JSONB) |
| `key_points` | `key_points` (JSONB) |
| `answer_key` | `answer_key` (JSONB) — **эталон, §4.1** |
| `source_chunk_id` | `source_chunk_id` (UUID, **nullable**) |
| `id` | `question_order` — **колонки сейчас нет, её надо добавить**, см. §4.1 |
| — | `question_id` — детерминированный, см. §4.2 |

Плюс в `tests`: `status_test` → «готов» (или «ошибка»), `difficulty` → из задачи, `amount_questions` → **NOT NULL**, заполняется **фактическим числом вопросов из ответа**: `len(questions)`. Поля `amountQuestions` в задаче больше нет, писать «`"min"`» не нужно.

**`source_chunk_id`:** ML присылает **UUID чанка** (метки `C1`, `C2` живут только в промпте, ML разворачивает их в UUID). Если чанка нет в `material_chunks` — писать `NULL`, **не ронять вставку по FK**: сначала найти чанк (`SELECT chunk_id FROM material_chunks WHERE chunk_id = :id`), и если его нет — `NULL`.

### 2.3. `grade-test` — проверить попытку

```json
{"task_id": "3b17…", "attempt_id": "dc12…", "test_id": "5780…",
 "answers": [
   {"question_id": "05a8…", "student_answer": {"index": 0}},
   {"question_id": "06b1…", "student_answer": {"indexes": [0, 2]}},
   {"question_id": "07c3…", "student_answer": {"text": "мой ответ"}}]}
```

- `task_id`, `attempt_id`, `test_id` и непустой `answers` — обязательны;
- `user_id` **не нужен**: студент известен backend'у по `attempt_id`. Если backend всё же пришлёт `user_id` — ML его проигнорирует (разбор терпимый к лишним полям), но полагаться на него нельзя;
- `student_answer` — **ровно один** вид, по типу вопроса: `{index}` — `single_choice`, `{indexes}` — `multi_choice`, `{text}` — `open_answer`;
- `question_id` — это id из `test_questions` (не порядковый номер). ML читает вопросы из БД сам.

**Порядок действий backend'а при сдаче попытки (важно!):**

1. Тест должен быть в статусе «готов» — иначе 400, а не 202;
2. создать `student_attempts`: `started_at = now()`, `finished_at` / `score_pct` / `grade` — `NULL`;
3. создать `attempt_answers` — по строке на ответ: `student_answer` (типизированный JSONB), `score` / `feedback` — `NULL`; `is_correct` и `correct_answer` — см. §4.4, они NOT NULL;
4. **только потом** опубликовать задачу в `grade-test:be-to-ml`;
5. ответить клиенту **202 Accepted**, попытка в статусе «обрабатывается».

Если публиковать раньше записи строк, вердикт может прийти раньше, чем backend сможет его записать.

Ответ ML:

```json
{"task_id": "3b17…", "attempt_id": "dc12…", "test_id": "5780…",
 "score_pct": 60.0, "grade": 3,
 "items": [{"question_id": "05a8…", "is_correct": true, "score": 1.0,
            "feedback": "Верно", "correct_answer": "Текст варианта", "student_answer": "Текст ответа"}]}
```

**Поля `status` в ответе нет.** Ошибка: `{"task_id": "…", "error": "…"}` — обязателен только `error`; `attempt_id` и `test_id` могут отсутствовать, если payload не удалось разобрать.

**Как применять вердикт:** по каждому item — `attempt_answers.score` ← `score`, `attempt_answers.feedback` ← `feedback`, `attempt_answers.is_correct` ← `is_correct`, `attempt_answers.correct_answer` ← `correct_answer` (по `question_id`); затем `student_attempts.finished_at` ← now, `score_pct` ← `score_pct`, `grade` ← `grade`. При ошибке попытку **не трогать** (только лог). Повторный вердикт перезаписывает те же строки.

**Шкала:** `score_pct` — процент по **всем** вопросам теста (пропущенный = 0), округление до 2 знаков. `grade`: ≥90 → 5, ≥70 → 4, ≥50 → 3, иначе 2.

---

## 3. Формат данных

**3.1. Формат вопроса — по типам.** `key_points` — критерии для `open_answer`, у закрытых типов `null` или `[]`. Эталон `answer_key` в payload'е **есть** — по объекту на вопрос, формат по типам в §2.2.

| `type` | `options` | `key_points` | `answer_key` |
|---|---|---|---|
| `single_choice` | 2–4 строки | `null` / `[]` | `{"correct_index": N}` |
| `multi_choice` | 4–6 строк | `null` / `[]` | `{"correct_indexes": [N, M]}` |
| `open_answer` | `null` | 2–4 строки — критерии оценки | `{"reference_answer": "<эталон>"}` |

`key_points` — **плоский список строк**. `true_false` ML не генерирует и не проверяет.

**3.2. `is_correct` = `score ≥ 0.5`.** Значение приходит от ML в `items[].is_correct` — backend пишет его как есть (в `attempt_answers` эта колонка есть и NOT NULL, см. §4.4). Backend не пересчитывает его сам.

**3.3. `correct_answer` — это текст**, а не индекс: для закрытых вопросов — текст правильного варианта, для `open_answer` — эталонный ответ. В `items[]` он приходит строкой. Колонка `attempt_answers.correct_answer` — JSONB; форма хранения (JSON-строка `"Read committed"` или объект `{"text": "…"}`) — на ваше усмотрение, но её надо зафиксировать в одном месте и отдать фронту в том же виде.

---

## 4. Схема БД: что есть сейчас и что требуется

Сейчас применены миграции `001-initial-schema.sql`, `002`, `003`, `004-query-tasks.sql`, `005-materials-test.sql`. Релевантные таблицы:

```sql
tests(test_id PK, course_id NOT NULL, title NOT NULL, amount_questions VARCHAR(50) NOT NULL,
      status_test NOT NULL, difficulty DEFAULT 'medium', created_at)

test_questions(question_id PK, test_id NOT NULL, type_question NOT NULL, text_question NOT NULL,
                options JSONB, key_points JSONB, source_chunk_id UUID NULL, created_at)

attempt_answers(answer_id PK, attempt_id NOT NULL, question_id NOT NULL,
                is_correct BOOLEAN NOT NULL, student_answer JSONB NOT NULL,
                correct_answer JSONB NOT NULL, score NUMERIC(3,2), feedback TEXT, created_at)

student_attempts(attempt_id PK, test_id NOT NULL, user_id NOT NULL,
                 started_at NOT NULL, finished_at, score_pct NUMERIC(5,2), grade INT)
```

**4.1. Добавить колонки `test_questions.answer_key JSONB` и `test_questions.question_order INT`.** Обе добавляются backend'ом своей миграцией.

**`test_questions.answer_key JSONB`** — в ERD заказчика колонка **есть** (эталон правильного ответа по каждому вопросу), в текущих миграциях её нет. С v4.1 ML отдаёт эталон в ответе `create-test:ml-to-be` (§2.2) — backend пишет объект `answer_key` as-is в эту колонку. Форма внутри: `{"correct_index": N}` \| `{"correct_indexes": [N, M]}` \| `{"reference_answer": "<эталон>"}`, плюс необязательный `explanation`.

Зачем: (1) без эталона backend не может показать студенту правильный ответ; (2) ML при проверке берёт эталон из БД первым источником (приоритет **БД → Redis → LLM-судья**) — эталон в БД не протухает, в отличие от Redis-ключа с TTL 30 дней. Пока колонки нет, ML работает и без неё (фолбэк на Redis, затем LLM-судья), но качество проверки падает: замер — LLM-судья на `multi_choice` назвал 2 правильных варианта вместо 3.

**`test_questions.question_order INT`** — в текущей схеме нет колонки порядка, а в ERD заказчика её тоже нет — это **осознанное отклонение, его надо письменно согласовать**. Причина: в ответе ML `id` вопроса — это порядковый номер (1, 2, 3…), а `question_id` — UUID; без отдельной колонки вопросы выдаются в порядке случайных UUID, и порядок теста «плывёт» от запуска к запуску. Требование: `question_order` = `id` из ответа ML.

**4.2. Детерминированные id** (обязательно, см. §1.6):
- `question_id = uuid5(test_id, "q:" + порядковый номер)` — повторный результат обновит те же строки, а не создаст дубли;
- `answer_id = uuid5(attempt_id, question_id)` — повторная обработка не плодит строки ответов.

Конкретная формула — на ваше усмотрение, важна детерминированность и стабильность между перезапусками.

**4.3. Где ML берёт эталон при проверке.** Приоритет: **БД → Redis → LLM-судья**.

1. **БД backend'а** — `test_questions.answer_key`, по `question_id` (ML читает вопросы из БД сам, id у него уже есть). Основной источник.
2. **Redis ML** — `ml:answers:{test_id}`, TTL 30 дней, поиск по нормализованному тексту вопроса. **Резервная копия**: нужна, пока backend не записал эталон в БД (окно между `create-test:ml-to-be` и записью listener'а) или если backend не выполнил §4.1.
3. **LLM-судья** (`choice_judge.py` / `open_answer_judge.py`) — последний рубеж, штатным путём не является: судья может ошибиться в числе правильных вариантов.

Backend на этот порядок не влияет — он отвечает только за то, чтобы эталон оказался в БД (п. 1).

**4.4. `attempt_answers.is_correct` и `attempt_answers.correct_answer` — NOT NULL.** В ERD заказчика этих колонок нет, а в миграции `001` они есть и **NOT NULL**. ML присылает обе величины в `items[]`, поэтому backend может их заполнить — но при создании строки ответа (до прихода вердикта) значений ещё нет. Выберите одно из двух и держитесь этого варианта:

- **(а) рекомендуемое** — снять NOT NOT NULL своей миграцией (`ALTER TABLE attempt_answers ALTER COLUMN is_correct DROP NOT NULL; ALTER COLUMN correct_answer DROP NOT NULL;`) и писать значения из вердикта; до вердикта — `NULL`;
- **(б) без миграции** — писать заглушку (`false` / `'{}'::jsonb`) при создании строки ответа и обновлять из `items[]` при применении вердикта. Тогда между сдачей и вердиктом в строке лежит заглушка — это надо учитывать при чтении попытки.

**4.5. Права ML в БД:** `INSERT` в `material_chunks` и `SELECT` в `test_questions` (в т. ч. `answer_key` — эталон) — больше ML в БД не пишет. Всё остальное (тесты, вопросы, попытки, ответы) пишет backend.

---

## 5. Чего backend НЕ должен делать

- пересобирать, «приводить к своему виду» и заново валидировать `options` / `key_points` / `answer_key` — ML уже проверил;
- ждать от ML поля `status` в `grade-test:ml-to-be` — его там нет;
- присылать `amountQuestions` в задаче `create-test` — поля больше нет, размер всегда выбирает ML;
- считать микс типов вопросов — это зона ML;
- публиковать сообщения без поля `payload` или с полем `type`;
- писать в `material_chunks` — это делает ML;
- определять тип задачи по `task_id` — только по имени канала;
- отправлять `grade-test` раньше, чем записаны `student_attempts` и `attempt_answers`;
- использовать старые имена каналов `ml-tasks:<type>` / `ml-results:<type>` — они больше не существуют, ML их не слушает;
- делать синхронный HTTP-запрос в ML — транспорт только Redis Streams, HTTP-эндпоинты клиента возвращают **202 Accepted** и статус проверяется опросом `GET`.

---

## 6. Чек-лист приёмки

| # | Что проверить | Как |
|---|---|---|
| 1 | Задача уходит в правильный канал и в одном поле | `redis-cli XRANGE create-test:be-to-ml - + COUNT 1` → ровно одно поле `payload` |
| 2 | Payload ingest'а — ровно два поля | `redis-cli XRANGE ingest:be-to-ml - + COUNT 1` → `{"material_id": …, "storage_key": …}` |
| 3 | Backend подписан на все три результата | `redis-cli XINFO GROUPS create-test:ml-to-be` |
| 4 | Ошибка от ML не роняет backend, а ставит нужную строку в «ошибка» | отправить в `create-test:be-to-ml` заведомо битый payload → в `create-test:ml-to-be` придёт `status:"error"` |
| 5 | Ошибка по grade распознаётся без `status` | битый payload в `grade-test:be-to-ml` → в `grade-test:ml-to-be` придёт `{"error": …}` **без** `status`, попытка не тронута |
| 6 | `XACK` — после успешной записи, в исходном канале | `redis-cli XPENDING create-test:ml-to-be` после искусственно брошенного исключения |
| 7 | Материал проиндексирован | `SELECT count(*) FROM material_chunks WHERE material_id::text = '<id>'` > 0 |
| 8 | Вопросы записаны как есть, порядок стабилен | `SELECT type_question, text_question FROM test_questions WHERE test_id=… ORDER BY question_order` |
| 9 | Вопрос с несуществующим чанком сохранился, `source_chunk_id` = NULL | вставить вопрос с чужой меткой → строка есть, FK не упал |
| 10 | Повторный результат не удвоил вопросы | обработать один и тот же результат дважды → `count(*)` не изменился |
| 11 | **Эталон сохранён в `test_questions.answer_key`** | `SELECT answer_key FROM test_questions WHERE test_id=…` → у каждого вопроса есть `correct_index` / `correct_indexes` / `reference_answer` по его типу |
| 12 | **`tests.amount_questions` = фактическое число вопросов** | `SELECT amount_questions, (SELECT count(*) FROM test_questions WHERE test_id=…) FROM tests WHERE test_id=…` → значения равны |
| 13 | **В задаче `create-test` нет поля `amountQuestions`** | `redis-cli XRANGE create-test:be-to-ml - + COUNT 1` → в payload'е только `task_id`, `test_id`, `material_ids`, `title`, `difficulty` |
| 14 | Попытка создаётся до публикации задачи | после сдачи: строки в `student_attempts` и `attempt_answers` есть, `score` = NULL, попытка в статусе «обрабатывается» |
| 15 | Вердикт применился | после ответа ML: `finished_at` заполнен, `score_pct` и `grade` совпадают с ответом, `is_correct`/`correct_answer` записаны, `GET` попытки отдаёт «проверена» |
| 16 | `multi_choice` с частичными отметками | ответ `{indexes:[0,2]}` → дробный `score`; `{index}` на `open_answer` → ошибка ML |
| 17 | **Колонки `answer_key` и `question_order` добавлены** | `SELECT column_name FROM information_schema.columns WHERE table_name='test_questions'` → есть `answer_key` и `question_order` |
