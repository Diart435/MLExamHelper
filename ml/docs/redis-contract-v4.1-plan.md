# План: Redis-контракт v4.1 (backend + ML)

> ⚠️ **План написан для другого репозитория** (`C:\MLExamHelper`, ветка-основание `master` `176e5de`) и под состояние ML, где контракт был ещё v4.0. Как **карта работы в backend'е** он годится; как описание формата — нет.
>
> Расхождения с действующим контрактом **v4.2** (repo `tp_ivt_team5_2026`, ветка `ml/redis-jobs`) разобраны в **`backend-redis-requirements.md` §0.1**:
> - §1.3 / D3 — плоская форма вопроса (`correct_index` на верхнем уровне) **неверна**: у вопроса есть `type` и **вложенный** `answer_key`;
> - D5 — фиксированные 10 вопросов **неверно**: размер выбирает ML-планировщик по материалу (1..30), `difficulty` задаёт микс типов и на количество вопросов **не влияет**;
> - §1.3 — `items[]` ML шлёт полный набор (`is_correct`, `correct_answer`, `feedback`), а не минимальный.
>
> Источник правды по формату — `ml/app/contracts.py` и `ml/docs/contracts/*.schema.json`. ML-часть плана (блок 8, блок 9) выполнена по этому контракту; см. `backend-redis-requirements.md` §4.6–§4.7 (порядок `XADD → XACK → XDEL`, reclaim по интервалу, ядовитое сообщение).

**Статус:** план, файлы проекта не изменялись.
**Источник истины:** `C:\test\backend-redis-requirements.md` (v4.1).
**Репозиторий:** `C:\MLExamHelper`, ветка-основание — текущий `master` (`176e5de`).
**Не использовать:** старые v4-разборы, `ml/docs/superpowers/specs/2026-10-22-...`, ветку `feature/redis-jobs-back` как готовое решение.

---

## 1. Контракт (freeze)

### 1.1. Каналы — константы в коде

| Направление | Канал | Кто читает |
|---|---|---|
| BE → ML | `ingest:be-to-ml` | ML, группа `ml-workers` |
| BE → ML | `create-test:be-to-ml` | ML, группа `ml-workers` |
| BE → ML | `grade-test:be-to-ml` | ML, группа `ml-workers` |
| ML → BE | `ingest:ml-to-be` | backend, группа `ml-backend` |
| ML → BE | `create-test:ml-to-be` | backend, группа `ml-backend` |
| ML → BE | `grade-test:ml-to-be` | backend, группа `ml-backend` |

Имена каналов — **константы в коде обеих сторон**, не env. В env допустимо только имя consumer-группы backend и consumer name.

Конверт:

```
XADD <канал> * payload '<JSON одной строкой>'
```

Ровно одно поле `payload`. JSON — compact, без переносов.

### 1.2. Payload BE → ML

```json
// ingest:be-to-ml
{"material_id":"<uuid>","storage_key":"<string>"}

// create-test:be-to-ml
{"task_id":"<uuid>","test_id":"<uuid>","material_ids":["<uuid>"],"title":"...","difficulty":"easy|medium|hard"}

// grade-test:be-to-ml
{"task_id":"<uuid>","attempt_id":"<uuid>","test_id":"<uuid>",
 "answers":[{"question_id":"<uuid>","student_answer":{"index":0}}]}
```

`student_answer` — ровно один вариант:

- `{"index":N}` — single_choice;
- `{"indexes":[...]}` — multi_choice;
- `{"text":"..."}` — open_answer.

Запрещены: `task_id` в ingest, `amount_questions`/`course_id` в create-test, `user_id` в grade, `type`, `input_msg_id`. Payload `create-test:be-to-ml` — **ровно 5 ключей**: `task_id`, `test_id`, `material_ids`, `title`, `difficulty`.

### 1.3. Результаты ML → BE

```json
// ingest ok
{"material_id":"<uuid>","status":"ready"}

// ingest error — material_id может отсутствовать
{"status":"error","error":"...","material_id":"<uuid>"}

// create-test ok
{"task_id":"<uuid>","status":"ok","test_id":"<uuid>",
 "test":{"title":"...","questions":[
   {"id":1,"text":"...","options":["..."],"correct_index":0,"source_chunk_id":"<uuid>"}]}}

// create-test error — test_id может отсутствовать
{"task_id":"<uuid>","status":"error","error":"...","test_id":"<uuid>"}

// grade-test ok — поля status НЕТ
{"task_id":"<uuid>","attempt_id":"<uuid>","test_id":"<uuid>",
 "score_pct":83.3,"grade":4,"items":[{"question_id":"<uuid>","score":1.0}]}

// grade-test error — только task_id и error
{"task_id":"<uuid>","error":"..."}
```

`items[]`: backend принимает необязательные `is_correct`, `correct_answer`, `feedback`. Если их нет — выводит сам. ML отправляет минимальный вариант `{question_id, score}`.

### 1.4. Инварианты

- `question_order` — 1-based, непрерывный (1..n).
- `question_id = uuid5(test_id, "q:" + order)`.
- `answer_id = uuid5(attempt_id, question_id)`.
- Вердикт — `UPDATE` по `(attempt_id, question_id)`; повторная доставка не плодит дубли.
- `XACK` — только после успешной записи в БД, в `message.getStream()`.
- Ошибка в `grade-test:ml-to-be` определяется наличием `error`, а не значением `status`.
- Доставка «хотя бы один раз» → все записи идемпотентны.

---

## 2. Решения по умолчанию

| # | Решение | Значение |
|---|---|---|
| D1 | `GET /api/tests/{id}/questions` | добавить, без `answer_key` |
| D2 | Доступ к попытке | только владелец; чужой `GET /api/attempts/{id}` → 404 |
| D3 | Внутренняя форма вопроса | старая: `id/text/options/correct_index/source_chunk_id`; backend пишет `single_choice`, `answer_key={"correct_index":N}` |
| D4 | Поля `items[]` | принимать `is_correct`/`correct_answer`/`feedback`, если есть; иначе выводить (`score >= 0.5`, `answer_key`) |
| D5 | Число вопросов | ~~ML-константа `DEFAULT_NUM_QUESTIONS = 10`; `difficulty` влияет только на содержание~~ **Устарело (v4.2):** размер выбирает ML-планировщик по материалу (1..30) — по числу проверяемых фактов; `difficulty` задаёт только микс типов, на количество вопросов не влияет |
| D6 | `tests.amount_questions` | ~~оставить значение из запроса~~ **Устарело (v4.2):** значение в колонке — всегда **число**: `"0"` при создании теста, затем фактическое число `questions.size()` из ответа ML. Бакетов `min`/`med`/`max` в `tests` не бывает |

D1–D6 подтвердить до начала реализации.

---

## 3. Порядок работ

### Блок 0. Ветка и baseline

- `git switch master`, `git status` чистый.
- `git switch -c feature/redis-contract-v4.1`.
- Baseline: backend `.\mvnw.cmd -o test` (141 тест), ML `python -m pytest -q`.
- Не мержить `feature/redis-jobs-back`.
- Не менять миграции `001`–`005`.

### Блок 1. Backend: примитивы контракта

**Новые файлы:**

- `backend/src/main/java/com/examassistant/common/redis/MlChannels.java`
  - `INGEST`, `CREATE_TEST`, `GRADE_TEST`, `BE_TO_ML`, `ML_TO_BE`;
  - `taskChannel(slug)`, `resultChannel(slug)`, `resultChannels()`.
- `backend/src/main/java/com/examassistant/common/util/UuidV5.java`
  - SHA-1 UUIDv5; не `UUID.nameUUIDFromBytes` (это MD5/v3).
- `backend/src/main/java/com/examassistant/messaging/IngestRedisRequest.java`
  - `materialId`, `storageKey`.
- `backend/src/main/java/com/examassistant/messaging/GradeTestRedisRequest.java`
  - `taskId`, `attemptId`, `testId`, `List<Answer> answers`;
  - вложенный `Answer`: `questionId`, `StudentAnswerPayload`.
- `backend/src/main/java/com/examassistant/messaging/StudentAnswerPayload.java`
  - `index`, `indexes`, `text`; `@JsonInclude(NON_NULL)`;
  - `toMap()` с проверкой «ровно один вариант».
- `backend/src/main/java/com/examassistant/common/config/MlStreamsProperties.java`
  - `consumerGroup`, `consumerName`, `reclaimIdle`, `reclaimIntervalMs`, `reclaimMaxAttempts`.

**Изменяются:**

- `messaging/CreateTestRedisRequest.java` — убрать `amountQuestions`, `courseId`; `difficulty` — `String`. ✅ сделано (и в `tests/DTO/CreateTestRequest.java` — поле `amountQuestions` тоже убрано).
- `messaging/Producer.java` — `publishIngest`, `publishCreateTest`, `publishGradeTest`.
- `messaging/producer/RedisProducer.java` — один `payload`, `ObjectMapper.writeValueAsString`; producer не пишет в БД.
- `materials/service/MaterialsService.java` — ingest без `task_id`.
- `tests/service/TestsService.java` — task создаётся здесь, затем publish; статус `CREATING`.
- `application.properties`, `application-docker.properties` — Redis timeouts, client-name, repositories=false, `ml.streams.*`.
- `TestFixtures`, `RedisProducerTest`, `MaterialServiceTest`, `TestsServiceTest` — под новые конструкторы.

Каждое поле wire-DTO — `@JsonProperty("snake_case")`.

### Блок 2. Миграция 006 + сущности

**Файлы:**

- `backend/src/main/resources/db/changelog/changes/006-redis-contract-v4.1.sql`
- `backend/src/main/resources/db/changelog/db.changelog-master.yaml` — include 006.

**SQL:**

```sql
-- 1. test_questions: answer_key + question_order
ALTER TABLE test_questions ADD COLUMN answer_key JSONB;
ALTER TABLE test_questions ADD COLUMN question_order INT;

WITH numbered AS (
    SELECT question_id,
           ROW_NUMBER() OVER (
               PARTITION BY test_id
               ORDER BY created_at, question_id
           ) AS rn
    FROM test_questions
)
UPDATE test_questions q
SET question_order = n.rn
FROM numbered n
WHERE q.question_id = n.question_id;

ALTER TABLE test_questions ALTER COLUMN question_order SET NOT NULL;
ALTER TABLE test_questions
    ADD CONSTRAINT uq_questions_test_order UNIQUE (test_id, question_order);

-- 2. attempt_answers: вердикт может отсутствовать до проверки
ALTER TABLE attempt_answers ALTER COLUMN is_correct DROP NOT NULL;
ALTER TABLE attempt_answers ALTER COLUMN correct_answer DROP NOT NULL;

-- 3. дедуп перед unique
DELETE FROM attempt_answers a
USING attempt_answers b
WHERE a.attempt_id = b.attempt_id
  AND a.question_id = b.question_id
  AND a.ctid > b.ctid;

ALTER TABLE attempt_answers
    ADD CONSTRAINT uq_answers_attempt_question UNIQUE (attempt_id, question_id);
```

**Сущности/репозитории:**

- `tests/entity/Question.java` — `questionOrder`.
- `tests/enums/TestStatus.java` — `ERROR("error")`.
- `messaging/enums/StatusTask.java` — `ERROR("error")`.
- `tests/entity/StudentAttempt.java`, `tests/entity/AttemptAnswer.java`.
- `tests/repository/StudentAttemptRepository.java`, `tests/repository/AttemptAnswerRepository.java`.
- `tests/repository/QuestionRepository.java` — `findByTestIdOrderByQuestionOrderAsc`.
- `tests/repository/TestRepository.java` — `findByIdForUpdate` (`PESSIMISTIC_WRITE`).
- `common/exception/TestNotReadyException.java` (409), `AttemptNotFoundException.java` (404) + `GlobalExceptionHandler`.
- `QuestionDTO`/`QuestionsService` — добавить `questionOrder`, `answerKey`.

### Блок 3. Create-test flow

- `TestsService.create`: статус `CREATING`, `TaskService.create`, публикация нового payload.
- `TestService.markError` + реализация (только из `CREATING`).
- `jobs/DTO/CreateTestResultMessage.java`, `TestDataMessage.java`, `QuestionDataMessage.java`; удалить старые `TestResultResponse`/`TestData`/`QuestionData`.
- `jobs/service/CreateTestResultService.java`:
  - `findByIdForUpdate`; применять только при `CREATING`;
  - валидация: `id == 1..n`, непустой текст, ≥2 options, `correct_index` в диапазоне;
  - `question_id = uuid5(test_id, "q:"+id)`, `question_order=id`, `answer_key={"correct_index":N}`;
  - `source_chunk_id` — только если чанк существует (`JdbcTemplate SELECT EXISTS`);
  - статус теста `CREATED`, task `FINISHED`;
  - при невалидном payload — тест `ERROR`, task `ERROR`.
- `jobs/listener/CreateTestListener.java` — success/error/poison; `XACK` через общий `MlResultAckSupport`.

### Блок 4. Ingest flow

- `jobs/DTO/IngestResultMessage.java`.
- `jobs/listener/ProcessingMaterialListener.java`:
  - `ready` → `changeStatus(materialId, "ready")`;
  - `error` → `changeStatus(materialId, "error")`;
  - без `material_id` не падать;
  - `FileNotFoundException` → ack+log;
  - прочие ошибки БД → без ack.
- Удалить неиспользуемый `jobs/ProcessMaterialResponse.java`, если он нигде не нужен.

### Блок 5. Grade flow + attempts API

- `tests/entity/StudentAttempt`, `AttemptAnswer` (если не в блоке 2).
- `tests/DTO/SubmitAttemptRequest.java`, `SubmitAttemptResponse.java`, `AttemptResponse.java`, `AttemptAnswerResponse.java`, `QuestionResponse.java`.
- `tests/service/AttemptsService.java`:
  - `POST /api/tests/{id}/attempts`: тест `CREATED`, доступ через `testService.getById`; валидация `question_id` и формы ответа; создать attempt + answer rows с `uuid5(attempt_id, question_id)`; publish grade task; вернуть `attemptId`.
  - `GET /api/attempts/{id}`: только владелец; `status=processing|finished`.
- `tests/controller/AttemptsController.java` — `/api/tests/{testId}/attempts`, `/api/attempts/{attemptId}`.
- `tests/controller/TestsController.java` — `GET /api/tests/{id}/questions` (409, если тест не `CREATED`).
- `jobs/DTO/GradeTestResultMessage.java`, `GradeItemMessage.java`.
- `jobs/service/GradeTestResultService.java`:
  - attempt не найден → log+return (ack);
  - обновить `score_pct`, `grade`, `finished_at`;
  - по каждому item: `UPDATE` строки `(attempt_id, question_id)`; нет строки (не отвечал) — пропустить;
  - `is_correct` из item или `score >= 0.5`;
  - `correct_answer` из item или из `answer_key`;
  - `feedback` из item.
- `jobs/listener/GradeTestListener.java` — error только log, попытку не трогать.

### Блок 6. Consumer + reclaim

- `jobs/service/RedisConsumer.java`:
  - `SmartLifecycle`, phase `DEFAULT_PHASE - 10`;
  - на старте `createGroup(channel, ReadOffset.lastConsumed(), "ml-backend")` для 3 каналов, `BUSYGROUP` глотать;
  - `container.receive(Consumer.from(group, name), StreamOffset.create(channel, lastConsumed()), listener)` — **не** `receiveAutoAck`;
  - `@Scheduled` reclaim: `pending(..., Range.unbounded(), 50, idle)` → `claim(...)` → передать полученные `MapRecord` слушателю;
  - при `getTotalDeliveryCount() >= max` — `acknowledgeAndDelete` + log;
  - ack всегда `acknowledgeAndDelete(message.getStream(), group, XDelOptions.defaults(), message.getId())`.
- `common/config/RedisConfig.java` — pollTimeout, batchSize, errorHandler.
- `jobs/service/MlResultAckSupport.java` — единые `payload()`, `ack()`, `ackPoison()`.

### Блок 7. Backend tests

Обязательные:

- `MlChannelsTest`, `UuidV5Test` (векторы `3ca4bc9c-3865-5f44-9f91-a19b5cfb788f`, `0d53909a-e8e3-5793-8fd1-2b4ebea2be16`, `3116d980-cdc2-54c8-bddf-f62a03c9f1d2`).
- `RedisProducerTest` — ровно один `payload`, запрещённые поля, массивы, варианты `student_answer`.
- `ProcessingMaterialListenerTest`, `CreateTestListenerTest`, `GradeTestListenerTest` — success/error/poison/DB-fail/no-ack.
- `CreateTestResultServiceTest` — идемпотентность, ids/order/answer_key.
- `GradeTestResultServiceTest` — вывод `is_correct`/`correct_answer`, повторное применение.
- `AttemptsServiceTest` — 202-сценарий, валидации, доступ.
- Обновить `TestsServiceTest`, `QuestionsServiceTest`, `TestFixtures`.
- `.\mvnw.cmd -o test` + ArchUnit.

### Блок 8. ML

**`ml/app/contracts.py`:**

- `TASK_CHANNEL_SLUGS`, `task_channel()`, `result_channel()`;
- `IngestTask` без `task_id`; `IngestResult` с `material_id`, `status=ready|error`;
- `CreateTestTask` без `num_questions`/`course_id`; ~~`DEFAULT_NUM_QUESTIONS = 10`~~ — **устарело (v4.2)**: размер выбирает планировщик по материалу, фиксированной константы нет;
- `StudentAnswer` — `index|indexes|text`;
- `GradeAttemptResult` без `status`/`overall_feedback`; error `{task_id, error}`;
- `parse_task` по slug/полному каналу.

**`ml/app/core/config.py`:**

- убрать `stream_*`;
- `consumer_name` по умолчанию `socket.gethostname()`;
- `worker_claim_max_attempts`, `worker_claim_interval_ms`.

**`ml/app/workers/worker.py`:**

- каналы из констант;
- `XADD result → XACK → XDEL`;
- `_reject` для ingest умеет отдать ошибку без `material_id`;
- reclaim `xpending_range` + `xclaim` + poison после N попыток;
- лог статуса через `getattr(result, "status", "ok")`.

**Остальное:**

- `handlers/ingest.py` — `material_id` вместо `task_id`.
- `handlers/create_test.py` — ~~`DEFAULT_NUM_QUESTIONS`~~ → планировщик `test_planner.plan_test(llm, digest)`.
- `handlers/grade_attempt.py` — убрать LLM/`overall_feedback`.
- `services/grader.py` — single/multi/open; open → 0 без падения; все вопросы теста.
- `db/questions.py` — `ORDER BY question_order, question_id`.
- `services/test_generator.py` — перенумеровать вопросы 1..n после фильтрации.
- `tests/test_contracts.py`, `test_config.py`, `test_worker.py`, `test_handlers.py`, `test_grader.py`, `test_test_generator.py` — обновить.
- `ml/.env.example`, `docker-compose.yml` — убрать `STREAM_*`, `CONSUMER_NAME`; добавить reclaim-настройки.
- `python -m pytest -q`.

### Блок 9. Compose/env

- ML: `CONSUMER_GROUP=ml-workers`, `WORKER_CLAIM_IDLE_MS=30000`, `WORKER_CLAIM_INTERVAL_MS=60000`, `WORKER_CLAIM_MAX_ATTEMPTS=5`; `CONSUMER_NAME` не задавать (hostname).
- Backend: каналы не передавать; `ml.streams.consumer-name=${HOSTNAME:backend-1}`.
- `docker compose config`.

### Блок 10. E2E

1. `docker compose up -d --build postgres redis seaweedfs backend ml`.
2. Регистрация → курс → загрузка PDF → материал `ready`.
3. Создать тест → `CREATING` → polling до `CREATED`; вопросов — сколько насчитал планировщик по материалу (1..30), `question_order` 1..N, `answer_key`, `question_id` = uuid5. ~~10 вопросов~~ — устаревшее ожидание (v4.2).
4. `GET /api/tests/{id}/questions` — без `answer_key`.
5. `POST /api/tests/{id}/attempts` → 202; polling `GET /api/attempts/{id}` до `finished`.
6. Redis: `XPENDING` пуст, `XLEN` не растёт, `XINFO GROUPS` содержит `ml-backend` на трёх каналах.
7. Повторная публикация того же результата — без дублей.
8. Ошибки: ingest без `material_id`, create-test с `test_id`, grade с `error` — без падений; попытка не меняется.
9. Битая JSON — ack+delete, без вечного pending.
10. Reclaim: pending старше порога — переигран.

---

## 4. Команды

```powershell
cd C:\MLExamHelper\backend
.\mvnw.cmd -o test
.\mvnw.cmd -o "-Dtest=com.examassistant.architecture.ArchUnit" test

cd C:\MLExamHelper\ml
python -m pytest -q

cd C:\MLExamHelper
docker compose config
docker compose up -d --build postgres redis seaweedfs backend ml
docker compose logs -f backend ml
docker compose exec redis redis-cli XPENDING grade-test:ml-to-be ml-backend
```

---

## 5. Guardrails для агентов

- Не менять `001`–`005`; только добавить `006`.
- Не мержить `feature/redis-jobs-back`.
- Не трогать `ml:*`; никаких `FLUSHDB`/`FLUSHALL`/`KEYS *`.
- Не использовать `receiveAutoAck`.
- Не добавлять `task_id` в ingest, `amount_questions`/`course_id` в create-test, `user_id` в grade, `status`/`overall_feedback` в grade-result.
- Не выносить имена каналов в env.
- `XDelOptions.defaults()`, не `empty()`.
- `acknowledge(key, group, recordId)` — именно в таком порядке.
- JSON — одной строкой; Java UUIDv5, не MD5.
- После каждого блока — тесты; красные тесты не переносить в следующий блок.
- Не коммитить `.env`, секреты, `target/`, `.pytest_cache/`.
- Не «чинить» фронтенд и несвязанный compose.

---

## 6. Приёмка

- [ ] 6 каналов — константы; env-префиксов нет.
- [ ] Backend читает 3 канала, группа `ml-backend`, consumer name уникален.
- [ ] `XACK` только после БД; `acknowledgeAndDelete`.
- [ ] Reclaim + poison после N попыток.
- [ ] Create-test сохраняет вопросы, порядок, `answer_key`, статус; дубли не появляются.
- [ ] Ingest/create-test/grade listener'ы null-safe.
- [ ] `POST /api/tests/{id}/attempts` → 202; `GET /api/attempts/{id}` работает.
- [ ] `GET /api/tests/{id}/questions` без `answer_key` (если D1 = да).
- [ ] ML: новые payload/результаты, без старых каналов; тесты зелёные.
- [ ] `docker compose config` валиден; e2e-цикл проходит.
- [ ] Backend `mvn test` + ArchUnit зелёные.

---

## 7. Открытые вопросы

Подтвердить D1–D6, особенно:

- D1 — нужен ли `GET /api/tests/{id}/questions`;
- ~~D5 — всегда ли 10 вопросов~~ — **снято в v4.2**: размер выбирает ML-планировщик по материалу (1..30), фиксированного 10 больше нет;
- ~~D6 — оставлять ли `amount_questions` из запроса~~ — **снято в v4.1/v4.2**: поля размера в задаче нет вовсе, а в `tests.amount_questions` backend пишет число (`"0"` → фактическое число).

После подтверждения переключить агента в **Build** и начать с ветки от `master` и миграции `006`.
