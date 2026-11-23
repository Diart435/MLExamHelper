# JSON-контракты backend ↔ ML

Связь между backend и ML осуществляется только через Redis Streams. Ниже зафиксированы payload'ы для трёх типов задач в обоих направлениях.

Источник правды по структуре payload'ов — dataclass'ы и методы `_as_dict()` / `to_json()` из `ml/app/contracts.py`. Все примеры в `examples/` сгенерированы из этого кода, а не придуманы вручную.

## Каналы и артефакты

| Канал | Направление | Схема | Пример | Кто пишет | Кто читает |
|---|---|---|---|---|---|
| `ingest:be-to-ml` | Backend → ML | [`ingest-be-to-ml.schema.json`](ingest-be-to-ml.schema.json) | [`examples/ingest-be-to-ml.json`](examples/ingest-be-to-ml.json) | Backend | ML-воркер |
| `ingest:ml-to-be` | ML → Backend | [`ingest-ml-to-be.schema.json`](ingest-ml-to-be.schema.json) | [`examples/ingest-ml-to-be.json`](examples/ingest-ml-to-be.json) | ML-воркер | Backend |
| `create-test:be-to-ml` | Backend → ML | [`create-test-be-to-ml.schema.json`](create-test-be-to-ml.schema.json) | [`examples/create-test-be-to-ml.json`](examples/create-test-be-to-ml.json) | Backend | ML-воркер |
| `create-test:ml-to-be` | ML → Backend | [`create-test-ml-to-be.schema.json`](create-test-ml-to-be.schema.json) | [`examples/create-test-ml-to-be.json`](examples/create-test-ml-to-be.json) | ML-воркер | Backend |
| `grade-test:be-to-ml` | Backend → ML | [`grade-test-be-to-ml.schema.json`](grade-test-be-to-ml.schema.json) | [`examples/grade-test-be-to-ml.json`](examples/grade-test-be-to-ml.json) | Backend | ML-воркер |
| `grade-test:ml-to-be` | ML → Backend | [`grade-test-ml-to-be.schema.json`](grade-test-ml-to-be.schema.json) | [`examples/grade-test-ml-to-be.json`](examples/grade-test-ml-to-be.json) | ML-воркер | Backend |

## Формат сообщения Redis Streams

Сообщение содержит ровно одно поле `payload`, значением которого является JSON-строка в одну строку:

```text
XADD <канал> * payload '<JSON>'
```

Поля `type` в payload нет: тип задачи однозначно задаётся именем канала. Поле `task_id` служит для корреляции конкретной задачи и её результата (в `ingest` корреляция идёт по `material_id`).

Ошибка — нормальный ответ. ML обязан ответить на каждое принятое сообщение, в том числе когда обработка завершилась ошибкой; backend не должен считать задачу «зависшей» из-за отсутствия успешного результата.

## Что изменилось в v4.2 (2026-11-23)

Правка касается только канала `create-test` — **состав payload'ов не изменился**, изменился смысл размера теста (полное обоснование — в спеке `ml/docs/superpowers/specs/2026-11-17-ml-backend-contract-v4.md` §0.4):

1. **В задаче `create-test:be-to-ml` поля размера нет вообще** — ни числа, ни `"min"`, ни бакета `min`/`med`/`max`. Payload — **ровно 5 ключей**: `task_id`, `test_id`, `material_ids`, `title`, `difficulty`.
2. **Размер теста (1..30) определяет ML-планировщик по числу проверяемых фактов в материале.** `app/services/test_planner.py`, `plan_test(llm, digest)` — ни параметра `difficulty`, ни параметра размера. Границы 1..30 — рамка, а не цель: фактов 3 → 3 вопроса, фактов 40 → 30 самых важных. Добивать выдуманными фактами нельзя.
3. **`difficulty` на количество вопросов не влияет** — только на микс типов вопросов и глубину формулировки.
4. **`tests.amount_questions` — всегда число, не бакет:** `"0"` при создании теста (вопросов ещё нет) → фактическое число `len(questions)` после ответа ML. Бакеты остались только в legacy-таблице `query_tasks`.

## Что изменилось в v4.1 (2026-11-17)

Три изменения в канале `create-test` (полное обоснование — в спеке `ml/docs/superpowers/specs/2026-11-17-ml-backend-contract-v4.md` §0.3):

1. **Из задачи `create-test:be-to-ml` убрано поле `amountQuestions`.** Backend присылает только `task_id`, `test_id`, `material_ids`, `title`, `difficulty`. Число вопросов (1..30) определяет сам ML — отдельным LLM-вызовом планировщика (`app/services/test_planner.py`, `plan_test(llm, digest)`), который смотрит на материал и возвращает `num_questions` + список тем. Backend после получения теста пишет `tests.amount_questions = len(questions)`.
2. **В ответе `create-test:ml-to-be` поле `answer_key` есть** — по объекту на вопрос: `{"correct_index": N}` (single_choice), `{"correct_indexes": [N, M]}` (multi_choice), `{"reference_answer": "<эталон>"}` (open_answer), плюс необязательный `explanation`. Backend пишет его в колонку `test_questions.answer_key` (есть в ERD заказчика).
3. **Приоритет эталона при проверке: БД → Redis → LLM-судья.** Раньше было Redis → LLM-судья. Redis (`ml:answers:{test_id}`, TTL 30 дней) остаётся резервной копией, но больше не единственный источник.

## Чего в payload нет

В контракте **нет** полей `input_msg_id`, `course_id`, `user_id` и `chunks_indexed`. Если такое поле появится в сообщении — это разъезд с backend'ом, который обнаружится только в рантайме.

Отдельно: в ответе `grade-test:ml-to-be` **нет поля `status`**. Признак ошибки — наличие поля `error`.

Поля `amountQuestions` нет **ни** в задаче `create-test:be-to-ml` (v4.1; в v4.2 — нет и никакого другого поля размера), **ни** в ответе `create-test:ml-to-be`.

`answer_key` (эталон правильного ответа) — **есть** в ответе `create-test:ml-to-be`, по объекту на каждый вопрос (v4.1). Backend пишет его в `test_questions.answer_key`. При проверке ML берёт эталон из первого доступного источника: `test_questions.answer_key` в БД → `ml:answers:{test_id}` в Redis → LLM-судья.

## Примечания по контрактам

### `ingest:be-to-ml`

- Обязательны `material_id` и `storage_key` — это ровно все поля контракта.
- Идентификаторы передаются строками.
- Если backend пришлёт лишние поля (`task_id`, `course_id` от старого контракта) — ML их проигнорирует, ошибки не будет.

### `ingest:ml-to-be`

- Успех: `status: "ready"`, обязателен `material_id`.
- Ошибка: `status: "error"`, обязателен `error`. `material_id` может отсутствовать: если payload не удалось разобрать, ML не знает, ни о каком материале речь.
- При `status: "error"` backend по `material_id` (если он есть) переводит соответствующий материал в статус «ошибка» и сохраняет текст `error` для диагностики.

### `create-test:be-to-ml`

- Обязательны `task_id`, `test_id`, `material_ids` (непустой массив строк), `title`.
- Поля `amountQuestions` **нет** (v4.1), и никакого другого поля размера нет (v4.2): размер теста определяет ML планировщиком — `num_questions` (1..30) + список тем. Размер = число проверяемых фактов в материале; если фактов 30 или больше — ровно 30, если 3 — 3. Выдумывать факты, чтобы добить число, нельзя.
- `difficulty` необязателен, допустимы `easy`, `medium`, `hard`; значение по умолчанию — `medium`. На **количество** вопросов не влияет (v4.2) — только на микс типов.

### `create-test:ml-to-be`

- Успех: `status: "ok"`, обязательны `task_id`, `test_id`, `test`; `test` содержит `title` и непустой массив `questions`.
- Вопрос различается по полю `type`: `single_choice`, `multi_choice`, `open_answer`. Поля вопроса: `id`, `type`, `text`, `options`, `key_points`, `source_chunk_id`, `answer_key`.
- `options` — массив строк, для `open_answer` может быть `null`. `key_points` — массив строк (критерии оценки), у закрытых типов может быть `null`. `source_chunk_id` — UUID чанка или `null`.
- `answer_key` — эталон правильного ответа (v4.1): `{"correct_index": N}` \| `{"correct_indexes": [N, M]}` \| `{"reference_answer": "<эталон>"}`, плюс необязательный `explanation`. Backend пишет объект as-is в `test_questions.answer_key`.
- Ошибка: `status: "error"`, обязателен только `error`. `test_id` может отсутствовать, `task_id` может быть пустой строкой — если payload не удалось разобрать, ML не знает, для какого теста задача.
- При `status: "error"` backend по `test_id` (если он есть) переводит соответствующий тест в статус «ошибка» и сохраняет текст `error` для диагностики.

### `grade-test:be-to-ml`

- Обязательны `task_id`, `attempt_id`, `test_id` и непустой массив `answers`.
- Элемент `answers` содержит `question_id` и ровно один вариант `student_answer`: `{index}`, `{indexes}` либо `{text}`.
- Ответ студента может ссылаться на вопрос по его строковому идентификатору.

### `grade-test:ml-to-be`

- Успех: обязательны `task_id`, `attempt_id`, `test_id`, `score_pct` (0..100), `grade` (целое 2..5), `items`. Поля `status` нет.
- Элемент `items` содержит `question_id`, `is_correct`, `score` (0..1), `feedback`, `correct_answer`, `student_answer`.
- `correct_answer` — **текст** правильного варианта (для `open_answer` — эталонный ответ), а не индекс.
- Ошибка: обязателен только `error`. `attempt_id` и `test_id` могут отсутствовать, `task_id` может быть пустой строкой — если payload не удалось разобрать, ML не знает, какую попытку проверял.
- При ошибке backend попытку по `attempt_id` (если он есть) **не изменяет**: не проставляет `finished_at`, `score_pct`, `grade` и оценки ответов. Ошибка только записывается в лог.

## Проверка контрактов

Из корня `ml/`:

```bash
python -m pytest ml/tests/test_contract_schema.py
```

Тест проверяет, что пример совпадает с реальной сериализацией dataclass'ов из `ml/app/contracts.py`, что JSON Schema валидирует пример и что в примерах и схемах нет полей, которых нет в контракте.

Для перегенерации примеров:

```bash
python tools/generate_contract_examples.py
```

Для самостоятельной проверки всех шести схем и примеров:

```bash
python tools/validate_contract_examples.py
```
