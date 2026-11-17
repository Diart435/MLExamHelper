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

Поля `type` в payload нет: тип задачи однозначно задаётся именем канала. Поле `task_id` служит для корреляции конкретной задачи и её результата.

Ошибка — нормальный ответ. ML обязан ответить на каждое принятое сообщение, в том числе когда обработка завершилась ошибкой; backend не должен считать задачу «зависшей» из-за отсутствия успешного результата.

В направлении ML → Backend в каждый опубликованный результат ML-воркер добавляет необязательное поле `input_msg_id` — Redis Stream ID исходного входящего сообщения.

## Примечания по контрактам

### `ingest:be-to-ml`

- Обязательны `material_id` и `storage_key`.
- `task_id` и `course_id` необязательны; `task_id` используется для корреляции.
- Идентификаторы передаются строками.

### `ingest:ml-to-be`

- Успех: `status: "ready"`, обязательны `chunks_indexed` (целое ≥ 0) и `material_id`; `task_id` необязателен (в `ingest` backend может не прислать `task_id`).
- Ошибка: `status: "error"`, обязателен только `error`. `material_id` и `task_id` могут отсутствовать или быть пустыми: если payload не удалось разобрать, ML не знает ни о каком материале речь, ни какой это task.
- При `status: "error"` backend по `material_id` (если он есть) переводит соответствующий материал в статус «ошибка» и сохраняет текст `error` для диагностики.

### `create-test:be-to-ml`

- Обязательны `task_id`, `test_id`, `material_ids` (непустой массив строк), `title`.
- `amountQuestions` необязателен: целое 1..30 означает «ровно столько вопросов»; строка `"min"`, `"auto"` или `""` означает, что размер выбирает ML.
- `difficulty` необязателен, допустимы `easy`, `medium`, `hard`; значение по умолчанию — `medium`.
- `course_id` необязателен.

### `create-test:ml-to-be`

- Успех: `status: "ok"`, обязательны `task_id`, `test_id`, `test`; `test` содержит `title` и непустой массив `questions`.
- Вопрос различается по полю `type`: `single_choice`, `multi_choice`, `open_answer`. У каждого типа свой состав `options`, `answer_key` и `key_points`.
- Ошибка: `status: "error"`, обязателен только `error`. `test_id` может отсутствовать, `task_id` может быть пустой строкой — если payload не удалось разобрать, ML не знает, для какого теста задача.
- При `status: "error"` backend по `test_id` (если он есть) переводит соответствующий тест в статус «ошибка» и сохраняет текст `error` для диагностики.

### `grade-test:be-to-ml`

- Обязательны `task_id`, `attempt_id`, `test_id`, `user_id` и непустой массив `answers`.
- Элемент `answers` содержит `question_id` и ровно один вариант `student_answer`: `{index}`, `{indexes}` либо `{text}`.
- Ответ студента может ссылаться на вопрос по его строковому идентификатору.

### `grade-test:ml-to-be`

- Успех: `status: "ok"`, обязательны `task_id`, `attempt_id`, `test_id`, `score_pct` (0..100), `grade` (целое 2..5), `items`.
- Элемент `items` содержит `question_id`, `is_correct`, `score` (0..1), `feedback`, `correct_answer`, `student_answer`.
- Ошибка: `status: "error"`, обязателен только `error`. `attempt_id` и `test_id` могут отсутствовать, `task_id` может быть пустой строкой — если payload не удалось разобрать, ML не знает, какую попытку проверял.
- При `status: "error"` backend попытку по `attempt_id` (если он есть) **не изменяет**: не проставляет `finished_at`, `score_pct`, `grade` и оценки ответов. Ошибка только записывается в лог.

## Проверка контрактов

Из корня `ml/`:

```bash
python -m pytest ml/tests/test_contract_schema.py
```

Тест проверяет, что пример совпадает с реальной сериализацией dataclass'ов из `ml/app/contracts.py`, а JSON Schema валидирует пример.

Для перегенерации примеров:

```bash
python tools/generate_contract_examples.py
```

Для самостоятельной проверки всех шести схем и примеров:

```bash
python tools/validate_contract_examples.py
```
