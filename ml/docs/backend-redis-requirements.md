# Redis в backend: требования для корректного обмена с ML (контракт v4.2)

**Кому.** Backend-разработчику.

**Зачем этот документ.** `backend-tz-contract-v4.md` описывает контракт сообщений: какие поля кладутся в payload, что backend пишет в БД, когда подтверждать. Этот документ — про **Redis**: какая конфигурация, какие вызовы и в каком порядке нужны backend'у, чтобы каналы вообще заработали. Всё выведено из `ml/` — источник правды.

**Связанные документы.** Форма сообщений — `ml/docs/backend-tz-contract-v4.md`; машино-читаемые схемы — `ml/docs/contracts/`; полная спека с обоснованием — `ml/docs/superpowers/specs/2026-11-17-ml-backend-contract-v4.md`.

**Статус кода backend'а (на 2026-11-23).** Реализация Redis в backend'е приведена к контракту v4.2: имена каналов, форма сообщения, подписка, listener'ы — всё как описано ниже. Разбор того, что было и что стало, — §5.

---

## 0. Коротко

| Что | Значение |
|---|---|
| Транспорт | Redis Streams, HTTP между ML и backend нет |
| Каналы | 6 штук, имена — **константы в коде**, не конфигурация |
| Конверт | `XADD <канал> * payload '<JSON одной строкой>'` — ровно одно поле |
| Consumer-группа ML | `ml-workers` (на каждом из трёх каналов задач) |
| Consumer-группа backend | одна своя, например `ml-backend`, на **каждом** из трёх каналов результатов |
| Consumer name | уникален на реплику (иначе две реплики сражаются за одно сообщение) |
| Подтверждение | `XACK` — **только после** успешной записи в БД, и **в тот канал**, откуда пришло |
| Ошибка | ML отвечает **всегда**; в `grade-test:ml-to-be` поля `status` нет — ошибка это наличие ключа `error` |
| Доставка | «хотя бы один раз» → запись в БД обязана быть идемпотентной |

### 0.1 План `ml/docs/redis-contract-v4.1-plan.md` — три расхождения с контрактом v4.2

План написан для **другого репозитория** (`C:\MLExamHelper`) и под состояние ML, где контракт был ещё v4.0. Если backend-разработчик пойдёт по нему буквально, ML и backend не сойдутся. Расходятся три пункта:

| Пункт плана | Что в плане | Что в контракте v4.2 (наша правда) |
|---|---|---|
| §1.3 / D3 — форма вопроса | плоская: `{"id":1,"text":"…","options":[…],"correct_index":0,"source_chunk_id":"…"}` | у вопроса есть **`type`** (`single_choice` \| `multi_choice` \| `open_answer`) и **вложенный** `answer_key`: `{"correct_index": N}` \| `{"correct_indexes": [N,M]}` \| `{"reference_answer":"…"}` + необязательный `explanation`. Плоского `correct_index` в ответе **нет** |
| D5 — размер теста | фиксированные 10 вопросов (`DEFAULT_NUM_QUESTIONS = 10`), `difficulty` влияет только на содержание | размер выбирает **ML-планировщик** по материалу (1..30) — по числу проверяемых фактов, `difficulty` задаёт **микс типов** (70/30/0, 40/30/30, 10/30/60) и на количество вопросов **не влияет**. Backend узнаёт фактический размер из ответа: `len(questions)` |
| §1.3 — `items[]` вердикта | `{"question_id":"…","score":1.0}` — минимальный вариант | ML шлёт полный набор: `is_correct`, `feedback` тоже приходят, а `correct_answer` — **объект-эталон** (та же форма, что `answer_key`: `{"correct_index": N}` \| `{"correct_indexes": [N,M]}` \| `{"reference_answer":"…"}`), `student_answer` — объект (`{"index"}` \| `{"indexes"}` \| `{"text"}`). Backend берёт их, если есть (D4 плана совпадает) |

Источник правды — `ml/app/contracts.py` и `ml/docs/contracts/*.schema.json`, а не план. План полезен как **карта работы** (что и в каком порядке делать в backend'е), но не как описание формата.

---

## 1. Источник правды — что смотреть в `ml/`

| Файл | Что там истина |
|---|---|
| `ml/app/contracts.py` | имена каналов (`TASK_CHANNEL_SLUGS`, `task_channel()`, `result_channel()`), dataclass'ы задач и результатов, `parse_task()` |
| `ml/app/workers/rag.py` | цикл чтения: `XREADGROUP` по трём каналам, роутинг по имени канала, `XADD` результата → `XACK` в исходный канал → `XDEL` обработанного сообщения, `XAUTOCLAIM` зависших |
| `ml/app/handlers/rag.py` | сборка результата (`IngestResult`, `CreateTestResult`, `GradeAttemptResult`) |
| `ml/app/core/config.py` | env ML: `REDIS_URL`, `CONSUMER_GROUP`, `CONSUMER_NAME` (дефолт — hostname), `WORKER_CLAIM_IDLE_MS`, `WORKER_CLAIM_INTERVAL_MS`, `WORKER_CLAIM_MAX_ATTEMPTS` |
| `ml/app/services/answer_store.py` | ключи ML в Redis: `ml:answers:{test_id}`, TTL 30 суток |
| `ml/docs/contracts/*.schema.json` | шесть JSON Schema (draft 2020-12) — по файлу на канал, с примерами в `examples/` |
| `ml/tools/stub_backend.py` | стенд: целиком эмулирует backend на Redis + Postgres. Готовый образец «как правильно» |

Стенд (`ml/tools/stub_backend.py`) — самый близкий к эталону образец: он публикует задачи, читает результаты своей consumer-группой, раскладывает их в БД. Если сомневаетесь в детали Redis-части — откройте его.

---

## 2. Конфигурация Redis в backend'е

### 2.1 Подключение

В `application-docker.properties` уже есть:

```properties
spring.data.redis.host=redis
spring.data.redis.port=6379
```

Дописать стоит:

```properties
# Таймауты: контейнер стримов работает опросом (poll), но падение Redis не должно
# висеть на HTTP-запросах бесконечно.
spring.data.redis.timeout=5s
spring.data.redis.connect-timeout=5s
# Имя клиента видно в CLIENT LIST / CLIENT NAME — проще искать в мониторинге.
spring.data.redis.client-name=${spring.application.name}
# Redis-репозитории Spring Data не нужны: @RedisHash-сущностей в проекте нет.
spring.data.redis.repositories.enabled=false
```

Пароля у Redis в compose нет (`redis:7.4-alpine` без `requirepass`). Если добавите пароль — он должен быть одинаковым у обеих сторон: ML читает `REDIS_URL` (`redis://redis:6379/0`), backend — `spring.data.redis.password`.

### 2.2 База данных: разделять нельзя

**Обе стороны должны быть в одной БД Redis (сейчас — `0`).**

Consumer group привязана к базе: если backend окажется в `db 1`, он просто не увидит стримы ML, а ML — сообщения backend'а. Обмен перестанет работать без единой ошибки в логах.

Отсюда — правило гигиены ключей, а не разделение баз:

- **ML владеет префиксом `ml:*`** (`ml:answers:{test_id}` — резервная копия эталонов правильных ответов, TTL 30 суток). Backend эти ключи **не читает, не пишет, не удаляет**.
- Backend выбирает себе префикс (например `app:refresh:*` для refresh-токенов) и не выходит за него.
- Backend **не вызывает `FLUSHDB`/`FLUSHALL`** — это снесёт эталон ML, и проверка попыток уйдёт в LLM-судью (вердикты станут хуже).
- Любая админская функция, обходящая ключи (`KEYS`, `SCAN` по всей базе, скрипты чистки), обязана фильтровать по своему префиксу.

### 2.3 Имена каналов — константы, не конфигурация

Имена каналов задаёт **обе стороны одинаково в коде**. Значение по env для них не предусмотрено: конфигурируемый префикс расходится тихо и ловится уже на проде.

```java
// names — константы контракта, НЕ @Value из properties
public final class MlChannels {
    public static final String INGEST      = "ingest";
    public static final String CREATE_TEST = "create-test";
    public static final String GRADE_TEST  = "grade-test";
    public static final String BE_TO_ML    = "be-to-ml";
    public static final String ML_TO_BE    = "ml-to-be";

    public static String taskChannel(String slug)   { return slug + ":" + BE_TO_ML; }
    public static String resultChannel(String slug) { return slug + ":" + ML_TO_BE; }
}
```

Итоговый список (шесть каналов):

| Направление | Канал | Кто читает |
|---|---|---|
| BE → ML | `ingest:be-to-ml` | ML, группа `ml-workers` |
| BE → ML | `create-test:be-to-ml` | ML, группа `ml-workers` |
| BE → ML | `grade-test:be-to-ml` | ML, группа `ml-workers` |
| ML → BE | `ingest:ml-to-be` | backend, своя группа |
| ML → BE | `create-test:ml-to-be` | backend, своя группа |
| ML → BE | `grade-test:ml-to-be` | backend, своя группа |

> В коде ML есть ещё legacy-канал `rag-question:be-to-ml` / `rag-question:ml-to-be` — «вопрос по материалу». Он не входит в контракт заказчика: публиковать его backend не обязан, но если опубликует — ML ответит в зеркальный канал.
>
> ⚠️ В корневом `.env` остались переменные `ML_TASKS_STREAM=ml-tasks` и `ML_RESULTS_STREAM=ml-results` — это наследие прежнего контракта (префиксы потоков). Они **ни на что не влияют**: ML собирает имена каналов в `app/contracts.py`, и compose эти переменные в сервис `ml` не передаёт. Не берите их за образец.

### 2.4 Consumer group и consumer name

| Что | Значение | Комментарий |
|---|---|---|
| Группа backend | `ml-backend` | одна и та же на **всех трёх** каналах результатов |
| Consumer name | уникален на реплику | `backend-1`, `backend-2`, … |

Consumer name обязан различаться между репликами: consumer group — это по сути «кто читает», и два процесса с одинаковым именем считаются одним и тем же потребителем. На практике это означает, что одно сообщение может обработаться в двух потоках одновременно (гонка за `UPDATE` в БД) и что в PEL одно сообщение числится за одним consumer'ом.

```properties
# Значение по умолчанию — имя пода/контейнера: уникально в пределах оркестратора.
ML_STREAMS_CONSUMER_GROUP=ml-backend
ML_STREAMS_CONSUMER_NAME=${HOSTNAME}
```

Имя группы backend'а — единственное, что можно вынести в env: оно не влияет на совместимость (backend читает только свои каналы), в отличие от имён каналов.

---

## 3. Публикация задач: backend → ML

### 3.1 Конверт

Ровно одно поле стрима:

```
XADD create-test:be-to-ml * payload '{"task_id":"…","test_id":"…",…}'
```

Не «поля задачи на верхнем уровне», а **один ключ `payload` со строкой JSON**. ML читает `fields["payload"]` и больше ничего — если поля раскиданы по верхнему уровню, ML увидит `"{}"` и ответит ошибкой.

JSON — **одной строкой, без переносов**. Jackson по умолчанию пишет compact-JSON, этого достаточно. Экранирование не-ASCII не важно: ML читает через `json.loads`.

### 3.2 Что должно быть внутри payload

| Канал | Поля payload |
|---|---|
| `ingest:be-to-ml` | `material_id`, `storage_key`. **`task_id` здесь нет** — корреляция идёт по `material_id` (одна индексация — один материал) |
| `create-test:be-to-ml` | **ровно 5 ключей**: `task_id`, `test_id`, `material_ids` (**массив** UUID-строк), `title`, `difficulty` (`easy`/`medium`/`hard`). Числа вопросов **нет** — размер выбирает ML |
| `grade-test:be-to-ml` | `task_id`, `attempt_id`, `test_id`, `answers[]`. Ответ студента — `{question_id, student_answer}`, где `student_answer` = `{index}` \| `{indexes:[…]}` \| `{text}` по типу вопроса. `user_id` в контракте нет |

Чего в payload быть **не должно** (backend пришлёт — ML это проигнорирует, но лишние поля в ТЗ и схемах запрещены): `amountQuestions`/`amount_questions`, `course_id`, `user_id` (в grade), `chunks_indexed`, `input_msg_id`, `type`.

**Про размер теста (v4.2).** В payload создания теста нет **никакого** поля размера — ни числа, ни `"min"`, ни бакета `min`/`med`/`max`. Число вопросов (1..30) выбирает ML-планировщик по материалу: сколько в нём проверяемых фактов. `difficulty` на количество вопросов не влияет — только на микс типов. Backend узнаёт фактический размер из ответа и пишет `tests.amount_questions = len(questions)`: при создании теста — `"0"` (вопросов ещё нет), после ответа ML — фактическое число. Бакеты остались только в legacy-таблице `query_tasks`.

> `material_ids` — массив, а не строка через запятую: ML разбирает список и падает с `material_ids must be a non-empty list`.

### 3.3 Spring Data Redis: как именно

```java
private RecordId publish(String channel, Object task) {
    String json = objectMapper.writeValueAsString(task);   // record-задача, без лишних полей
    return stringRedisTemplate.opsForStream().add(channel, Map.of("payload", json));
}
```

`opsForStream().add(K, Map)` — это `XADD`. Возвращает `RecordId` (id сообщения) — его полезно сохранить рядом с задачей: по нему видно, опубликовали ли задачу вообще.

Сериализаторы: берите `StringRedisTemplate` (или свой `RedisTemplate<String, String>` со `StringRedisSerializer` — такой уже есть в `common/config/RedisConfig.java`). Ключ и **значение** должны быть строками: `payload` — это строка JSON, а не объект, иначе получится двойное кодирование.

---

## 4. Подписка на результаты: ML → backend

### 4.1 Создание групп — на каждом канале

Consumer group привязана к одному стриму, поэтому группа создаётся **на каждом** из трёх каналов результатов. Повторное создание (`BUSYGROUP`) — норма: приложение перезапускается, группа уже есть, её надо проглатывать и идти дальше.

```java
for (String channel : List.of(resultChannel(INGEST), resultChannel(CREATE_TEST), resultChannel(GRADE_TEST))) {
    try {
        stringRedisTemplate.opsForStream().createGroup(channel, ReadOffset.lastConsumed(), GROUP);
    } catch (RuntimeException e) {
        if (!isBusyGroup(e)) throw e;   // BUSYGROUP — штатно; остальное — пробрасывать
    }
}
```

`createGroup(key, ReadOffset, group)` в Spring Data Redis отправляет `XGROUP CREATE <key> <group> <offset> MKSTREAM` — канал создаётся на лету, первым же сообщением ML. Проверено по `spring-data-redis-4.1.1.jar`: `DefaultStreamOperations.createGroup` вызывает `xGroupCreate(key, group, offset, true)`, а `LettuceStreamCommands` маппит флаг в `XGroupCreateArgs.Builder.mkstream(true)`.

Идентификатор для группы — `ReadOffset.lastConsumed()` («`>`»): сообщения, опубликованные ML, пока backend лежал, **не теряются** — `last-delivered-id` группы не двигается, и при первом чтении после подъёма группа отдаст их.

### 4.2 Чтение: `receive`, а не `receiveAutoAck`

```java
container.receive(
        Consumer.from(GROUP, consumerName),
        StreamOffset.create(channel, ReadOffset.lastConsumed()),
        listener);
```

`StreamMessageListenerContainer.receive(...)` **не подтверждает сообщения сам** — подтверждение только то, что вызвал обработчик. Автоподтверждение есть только у `receiveAutoAck(...)`, и его использовать **нельзя**: контракт требует «`XACK` только после успешной записи в БД», а `receiveAutoAck` подтвердит сообщение сразу после возврата обработчика — в том числе когда обработчик упал, и тогда сообщение потеряется навсегда.

`StreamMessageListenerContainer` (bean уже есть в `common/config/RedisConfig.java`) работает опросом с `pollTimeout` и **не занимает соединение** — в отличие от ручного `opsForStream().read(...)` с `StreamReadOptions.block(...)`, который в Lettuce держит соединение и блокирует остальные команды приложения (refresh-токены тоже ходят в Redis).

### 4.3 Подтверждение — после записи в БД

Порядок обработчика строго такой:

```
1. достать payload → распарсить JSON в record
2. разобрать ветку: успех / ошибка
3. записать в БД (транзакция)
4. XACK в тот канал, откуда пришло сообщение
5. только потом — лог «обработано»
```

```java
@Override
public void onMessage(MapRecord<String, String, String> message) {
    try {
        handle(parse(message));                       // разбор + запись в БД
        acknowledge(message);                        // XACK — только теперь
    } catch (Exception e) {
        log.error("Не удалось обработать результат ML из канала {}: {}",
                message.getStream(), e.getMessage(), e);
        // БЕЗ XACK: сообщение остаётся в pending и будет переиграно.
    }
}
```

`XACK` идемпотентен, но **канал в `acknowledge` — тот, откуда пришло сообщение** (`message.getStream()`), а не «общий»:

```java
private void acknowledge(MapRecord<String, String, String> message) {
    stringRedisTemplate.opsForStream()
            .acknowledge(message.getStream(), GROUP, message.getId());
}
```

### 4.4 Ветка ошибки — отдельная, а не «статус не равен ok»

ML **всегда отвечает**, в том числе на ошибку. Форма ответа зависит от канала:

| Канал ответа | Успех | Ошибка |
|---|---|---|
| `ingest:ml-to-be` | `{"material_id":"…","status":"ready"}` | `{"status":"error","error":"текст","material_id":"…"}` — `material_id` может отсутствовать |
| `create-test:ml-to-be` | `{"task_id":"…","status":"ok","test_id":"…","test":{…}}` | `{"task_id":"…","status":"error","error":"текст","test_id":"…"}` — `test_id` может отсутствовать |
| `grade-test:ml-to-be` | `{"task_id":"…","attempt_id":"…","test_id":"…","score_pct":83.3,"grade":4,"items":[…]}` — **поля `status` нет** | `{"task_id":"…","error":"текст"}` — **поля `status` нет** |

Правила обработки:

- Признак ошибки в `grade-test:ml-to-be` — **наличие ключа `error`**, а не значение `status`. Проверка «`status == "ok"`» в этом канале всегда ложна — так backend посчитает успешным любой вердикт.
- В ветке ошибки идентификаторы **могут отсутствовать** (ML не знает id, если не смог разобрать payload). Обязателен только `error`. Backend читает `material_id`/`test_id`/`attempt_id`, если они есть, и не падает, если их нет.
- Ошибку применить к нужной строке: материал → `status_material='error'`; тест → `status_test='error'`; **попытку не трогать** (оставить «обрабатывается»), только залогировать — вердикта нет, оценки тоже нет.
- Текст ошибки backend хранит у себя (в `materials`/`tests` колонки для текста ошибки в ERD нет — логируется).

**Идемпотентность обязательна.** Доставка — «хотя бы один раз»: ML может упасть между `XADD` результата и `XACK` и выполнить задачу заново. Значит повторная обработка результата не должна ни плодить дубли, ни ломать уже записанный вердикт:

- вопросы теста — `question_id = uuid5(test_id, "q:" + порядковый номер)`;
- строки ответов — `answer_id = uuid5(attempt_id, question_id)`;
- вердикт — `UPDATE` по `attempt_id` + `question_id`, повторный вердикт перезаписывает те же строки.

### 4.5 Pending: сообщения, которые «зависли»

Если backend упал в момент обработки (или обработчик бросил исключение), сообщение остаётся в **pending-списке** канала. `XREADGROUP` с «`>`» его больше не отдаёт — это не новые сообщения, а уже доставленные. У ML на этот случай есть `XAUTOCLAIM` (см. `ml/app/workers/rag.py::_reclaim_pending`): сообщение, провисевшее дольше `reclaim_idle_ms`, забирается обратно в обработку.

Сценарии потери:

| Событие | Что происходит |
|---|---|
| Backend лежал, ML работал | Ничего не теряется: сообщения ждут в стриме, `last-delivered-id` группы не двигается |
| Backend упал **после** чтения, **до** `XACK` | Сообщение в pending. Без reclaim'а оно там и лежит — нужен ручной `XCLAIM` |
| Backend упал **после** `XACK`, **до** записи в БД | Результат потерян. Поэтому `XACK` — строго **после** записи в БД |
| ML упал после `XADD` результата, до `XACK` | Задача выполнится заново, backend получит результат дважды → запись идемпотентна |

**Рекомендация:** реализовать на стороне backend'а периодический reclaim зависших сообщений — иначе один упавший обработчик навсегда блокирует один результат (не весь канал, но конкретную задачу: попытка останется «в обработке»).

В Spring Data Redis 4.1.1 нет `XAUTOCLAIM`, но есть `XPENDING` + `XCLAIM`:

```java
// 1. Найти сообщения, висящие дольше idle-порога
PendingMessages pending = stringRedisTemplate.opsForStream()
        .pending(channel, GROUP, Range.unbounded(), count, minIdleTime);

// 2. Забрать их себе
stringRedisTemplate.opsForStream()
        .claim(channel, GROUP, consumerName, minIdleTime, recordIds);
```

`minIdleTime` для backend'а — порядка минуты (обработка короткая), `count` — десятки. Как только сообщение переиграно, оно снова попадёт в обработку и снова требует `XACK` — то есть цикл reclaim'а безопасный, если запись в БД идемпотентна.

Страховка от «ядовитого» сообщения: если после N попыток обработка падает всё так же — сообщение надо снять с обработки руками (`XACK` без записи + запись в лог), иначе оно будет крутиться бесконечно. У ML для этого есть `WORKER_CLAIM_MAX_ATTEMPTS`; у backend'а аналог стоит завести.

### 4.6 Ядовитое сообщение: ML отвечает ошибкой, а не молчит

Раньше ML ронял ядовитое сообщение из pending **без результата** — backend висел в ожидании вердикта, которого не будет никогда (материал навсегда «в обработке», тест — «создаётся»).

Теперь поведение такое: сообщение, которое не удалось обработать `WORKER_CLAIM_MAX_ATTEMPTS` (5) раз, ML **публикует в канал результата ошибочный результат** — `{"status":"error","error":"…"}`, а в `grade-test:ml-to-be` — `{"task_id":"…","error":"…"}` (без `status`, как и все grade-ответы) — затем подтверждает сообщение и удаляет его из стрима. Backend получает явную ошибку и переводит сущность в «ошибка».

⚠️ **Требование к backend'у: поздняя ошибка не должна понижать уже успешный статус.** Доставка — «хотя бы один раз», поэтому успешный результат может прийти после неуспешного (или наоборот). Правило: если материал/тест уже в успешном терминальном состоянии (`ready` / «готов»), пришедшая ошибка его **не** переводит в «ошибка» — только логируется. Иначе гонка «сначала успех, потом поздняя ошибка» испортит результат.

### 4.7 Порядок работы воркера ML (для сверки с логами)

1. `XREADGROUP` по трём каналам задач (блокировка 5 с, по одному сообщению за раз).
2. Роутинг по **имени канала** → handler → результат.
3. `XADD` в зеркальный канал результата (`payload` — JSON одной строкой).
4. `XACK` в **исходный** канал.
5. `XDEL` обработанного сообщения из исходного канала — чтобы стрим задач не рос.

Пункты 3–5 идут именно в таком порядке. Если `XADD` не прошёл — `XACK` **не делается**: сообщение вернётся в работу через reclaim (шаг 6), и backend получит результат ровно один раз. Если `XACK` не прошёл при успешном `XADD` — результат у backend'а уже есть, задача выполнится ещё раз, поэтому запись в БД идемпотентна.

6. Reclaim: не чаще одного раза в `WORKER_CLAIM_INTERVAL_MS` (60 с) ML проверяет pending-список и забирает сообщения, провисевшие дольше `WORKER_CLAIM_IDLE_MS` (30 с).

---

## 5. Что было и что стало (разбор прежнего кода backend'а)

Таблица показывает, как выглядел код backend'а до приведения к контракту v4.1/v4.2 и что в нём сейчас. Прежние расхождения закрыты; левая колонка осталась как история изменений.

| Где | Что было | Что стало |
|---|---|---|
| `messaging/producer/RedisProducer.java` | `STREAM_KEY_TESTS = "tests:create-test-request"`, `STREAM_KEY_MATERIALS = "materials:process-response"` | ✅ каналы из `common/redis/MlChannels.java`: `create-test:be-to-ml`, `ingest:be-to-ml`, `grade-test:be-to-ml` |
| `messaging/producer/RedisProducer.java` | поля задачи раскиданы по верхнему уровню: `task_id`, `test_id`, `material_ids`, `title`, `amount_questions`, `difficulty`, `course_id` | ✅ одно поле `payload` со строкой JSON; внутри — только поля контракта |
| `messaging/producer/RedisProducer.java` | `material_ids` — строка через запятую (`Collectors.joining(",")`) | ✅ массив `["uuid","uuid"]` |
| `messaging/producer/RedisProducer.java` | `amount_questions` и `course_id` в payload | ✅ обоих полей в контракте нет (v4.1). С v4.2 payload создания теста — **ровно 5 ключей**: `task_id`, `test_id`, `material_ids`, `title`, `difficulty` |
| `messaging/producer/RedisProducer.java` | `publishMaterialProcess` кладёт `task_id` | ✅ у `ingest` `task_id` нет, корреляция по `material_id` |
| `messaging/producer/RedisProducer.java` | нет продюсера для `grade-test` | ✅ `publishGradeTest`: `task_id`, `attempt_id`, `test_id`, `answers[]` |
| `jobs/service/RedisConsumer.java` | пустой класс | ✅ подписка на три канала результатов, создание групп (`MKSTREAM`), reclaim pending + poison |
| `common/config/RedisConfig.java` | контейнер и шаблон созданы, но `container.receive(...)` **не вызывается нигде**, группы **не создаются** | ✅ `container.receive(...)` на каждый канал в `RedisConsumer.start()`; группы создаются там же (контейнер с `autoStartup=false`, чтобы группы были до подписки) |
| `jobs/listener/ProcessingMaterialListener.java` | `STREAM_KEY = "materials:process-response"`, `GROUP_NAME = "material-status-handlers"` | ✅ канал `ingest:ml-to-be`, группа backend'а (`ml-backend`) |
| `jobs/listener/CreateTestListener.java` | `STREAM_KEY = "tests:create-test-response"`, `GROUP_NAME = "test-handlers"` | ✅ канал `create-test:ml-to-be`, та же группа |
| оба listener'а | ветки ошибки нет: `UUID.fromString(fields.get("material_id"))` → NPE, если ML прислал `error` без id | ✅ ветка ошибки обрабатывается отдельно; попытку не трогать |
| оба listener'а | читают `fields.get("test")` как отдельное поле | ✅ весь payload — один JSON, разбирать целиком |
| `jobs/listener/CreateTestListener.java` | читает `amount_questions` из ответа ML | ✅ ML размер не присылает (v4.1): размер = `len(questions)`, пишется в `tests.amount_questions` (в v4.2 — всегда **число**, не бакет: `"0"` при создании теста → фактическое число после ответа) |
| оба listener'а | нет обработки «неизвестного канала» и защиты от NPE | ✅ контрактные DTO'ы + `MlResultAckSupport`: битый payload → `ackPoison` (подтвердить и не разбирать дальше) |
| — | нет listener'а `grade-test` | ✅ `jobs/listener/GradeTestListener.java` + `GradeTestResultService`: `student_attempts` (finished_at, score_pct, grade) + `attempt_answers` (score, feedback, is_correct, correct_answer) |
| — | нет reclaim'а pending | ✅ `RedisConsumer.reclaimPending()` — `XPENDING` + `XCLAIM`, poison по счётчику доставок (§4.5) |
| — | нет `XTRIM`/`XDEL` | ✅ `acknowledgeAndDelete` — подтвердить и удалить одним заходом (§6.1) |
| `application-docker.properties` | только host/port | ✅ §2.1: таймауты, client-name, repositories.enabled |
| `jobs/DTO/*` | `correct_answer` — строка, `key_points` — не списка | ✅ `correct_answer` — объект-эталон (та же форма, что `answer_key`), `key_points` — `List<String>` |
| `jobs/Consumer.java` | пустой интерфейс | ⚠️ остался лежать (на контракт не влияет, но чистить надо) |

Отдельно: в `CreateTestListener` был `//TODO: сделать создание теста` — теперь запись вопросов в `test_questions` написана (`jobs/service/CreateTestResultService.java`), вместе с `answer_key` и `key_points`.

---

## 6. Эксплуатация

### 6.1 Стримы растут бесконечно — их надо укорачивать

`XACK` убирает запись из pending, но **не из самого стрима**. За ML эта часть закрыта: обработанное сообщение воркер удаляет сам (`XADD` → `XACK` → `XDEL`), поэтому каналы задач `*:be-to-ml` не растут. За backend'ом остаются каналы результатов `*:ml-to-be` — их чистит сам backend.

Что делать:

- **После успешной обработки** — `XDEL` вместе с `XACK`. В Spring Data Redis есть готовый вызов: `opsForStream().acknowledgeAndDelete(channel, group, XDelOptions.empty(), recordId)` — подтвердить и удалить одним заходом.
- **Осторожно с `XTRIM`**: `trim(channel, maxLen)` режет стрим по длине и может снести непрочитанное сообщение, если backend отстал. Если делать trim — только с большим запасом (`maxLen` = десятки тысяч) и понимая, что при большой задержке сообщение пропадёт. Надёжнее `XDEL` после обработки.
- Удалять надо **свои** каналы. Стримы ML (`*:be-to-ml`) backend тоже чистит в порядке подтверждения своих задач — там это безопасно, потому что сообщение уже прочитано.

### 6.2 Наблюдаемость

Минимум, который стоит видеть:

| Что | Где смотреть | Зачем |
|---|---|---|
| Длина канала | `XLEN <канал>` | растёт ли (см. 6.1) |
| Pending | `XPENDING <канал> <группа>` | «залипшие» результаты (см. 4.5) |
| Группа | `XINFO GROUPS <канал>` | жива ли, сколько pending, сколько прочитано |
| Потребление | `XINFO CONSUMERS <канал> <группа>` | не сидит ли consumer без сообщений (забыли переключить канал) |

В коде — либо микрометр-гейдж (`XLEN`/`XPENDING` по каждому каналу), либо периодическая задача, обновляющая gauge'ы. Health-check Redis в Actuator (`/actuator/health`) Spring Boot включает сам, когда на classpath `spring-boot-starter-data-redis` — в compose он уже используется как readiness-проба.

### 6.3 Что должно быть в логах

По одному структурированному событию на результат:

```
ml_result_received  channel=create-test:ml-to-be  msg_id=1751...  task_id=...  test_id=...  status=ok|error
ml_result_applied   channel=create-test:ml-to-be  msg_id=1751...  rows=12
ml_result_failed    channel=grade-test:ml-to-be    msg_id=1752...  error=...
ml_result_acked     channel=grade-test:ml-to-be    msg_id=1752...
```

`msg_id` обязателен: без него нельзя расследовать «куда делось сообщение» — в pending оно или уже применено.

### 6.4 Redis в docker-compose

Текущий `redis:7.4-alpine` в compose устроен минимально: том `redis-data:/data`, healthcheck `redis-cli ping`, пароля нет.

Что стоит учесть:

- **Версия 7.4** — все нужные команды поддерживаются (`XAUTOCLAIM` с 6.2, `MKSTREAM` с 5.0). Ничего апгрейдить не нужно.
- **Пароль**: если добавите `requirepass` — он должен совпадать с тем, что в `REDIS_URL` у ML и в `spring.data.redis.password` у backend'а. Иначе backend и ML будут видеть разные Redis (например, ML с паролем, backend без).
- **`maxmemory-policy`**: оставить `noeviction` (дефолт). При `allkeys-lru` Redis молча вытеснит `ml:answers:{test_id}` — эталон правильных ответов исчезнет, и проверка попыток уйдёт в LLM-судью (вердикты станут хуже). С `noeviction` при нехватке памяти Redis честно вернёт ошибку записи.
- **Персистентность**: по умолчанию включён только RDB-снапшот. Redis, перезапущенный без сохранённого состояния, теряет стримы — а вместе с ними задачи и результаты, которые ещё не разложены в БД. Для учебного стенда достаточно RDB; для прода — `--appendonly yes`.
- **Не запускать `redis-cli FLUSHALL` в стенде, пока в Redis живут незавершённые задачи.**

---

## 7. Чек-лист приёмки Redis-части

- [ ] Имена шести каналов — константы в коде; в env нет префиксов потоков
- [ ] Обе стороны в одной базе Redis (db 0) и в одном инстансе
- [ ] Backend читает **три** канала результатов; на каждом своя consumer-группа `ml-backend`
- [ ] Consumer name уникален на реплику (например, `${HOSTNAME}`)
- [ ] Группы создаются с `createGroup(..., ReadOffset.lastConsumed(), ...)`; `BUSYGROUP` проглатывается, остальное — пробрасывается
- [ ] Публикация задач — `XADD <канал> * payload '<JSON>'`, ровно одно поле `payload`
- [ ] Payload'ы соответствуют §3.2: без `amountQuestions`, без `course_id`, без `task_id` в ingest, `material_ids` — массив; payload создания теста — **ровно 5 ключей**
- [ ] Чтение через `container.receive(...)`, **не** `receiveAutoAck`
- [ ] `XACK` — после успешной записи в БД, в канал, откуда пришло сообщение
- [ ] Обработчик не бросает наружу исключение: ошибка → лог, без `XACK`
- [ ] Ветка ошибки разобрана отдельно; в `grade-test:ml-to-be` ошибка определяется по наличию `error`, а не `status`
- [ ] Запись в БД идемпотентна (детерминированные `question_id`/`answer_id`)
- [ ] Реализован reclaim pending (`XPENDING` + `XCLAIM`) и счётчик попыток
- [ ] Обработанные сообщения удаляются из стрима (`acknowledgeAndDelete` или `XDEL`)
- [ ] Поздняя ошибка **не понижает** уже успешный статус (`ready`/«готов» остаётся «готов»)
- [ ] Форма вопроса читается по `type` + вложенному `answer_key` — **не** по плоскому `correct_index` (§0.1)
- [ ] Размер теста = `len(questions)` из ответа — не фиксированные 10, не поле из задачи и не бакет (§0.1)
- [ ] В логах есть `channel`, `msg_id`, `task_id`
- [ ] Backend не трогает ключи `ml:*` и не вызывает `FLUSHDB`
- [ ] Проверено вживую: задача ушла в канал, ML ответил, backend разложил результат в БД, `XPENDING` пуст, `XLEN` не растёт

Проверка на стенде ML (`ml/tools/stub_backend.py`) — она эмулирует backend целиком и показывает рабочий цикл:

```bash
python -m tools.stub_backend peek create-test:ml-to-be 3      # что ML ответил
python -m tools.stub_backend peek create-test:be-to-ml 3      # что backend отправил
```

---

## 8. Приложение: соответствие API Spring Data Redis 4.1.1

Проверено по локальному артефакту `spring-data-redis-4.1.1.jar` (`RedisStreamCommands`, `StreamOperations`, `DefaultStreamOperations`, `LettuceStreamCommands`) и документации проекта.

| Задача | Вызов в Spring Data Redis | Команда Redis |
|---|---|---|
| Опубликовать | `opsForStream().add(channel, Map.of("payload", json))` | `XADD` |
| Создать группу | `opsForStream().createGroup(channel, ReadOffset.lastConsumed(), group)` | `XGROUP CREATE … MKSTREAM` (флаг `true` подставляет сам Spring) |
| Читать | `container.receive(Consumer.from(group, name), StreamOffset.create(channel, ReadOffset.lastConsumed()), listener)` | `XREADGROUP … >` (опрос, соединение не держится) |
| Подтвердить | `opsForStream().acknowledge(channel, group, recordId)` | `XACK` |
| Подтвердить и удалить | `opsForStream().acknowledgeAndDelete(channel, group, XDelOptions.empty(), recordId)` | `XACK` + `XDEL` |
| Pending | `opsForStream().pending(channel, group, Range.unbounded(), count, minIdleTime)` | `XPENDING` |
| Забрать зависшее | `opsForStream().claim(channel, group, consumer, minIdleTime, recordIds…)` | `XCLAIM` (аналога `XAUTOCLAIM` в API нет) |
| Подрезать | `opsForStream().trim(channel, maxLen, approximate)` | `XTRIM` |
| Удалить | `opsForStream().delete(channel, recordIds…)` | `XDEL` |

Особенности версии 4.1.1, на которые стоит обратить внимание:

- `StreamOperations.createGroup` **не имеет** перегрузки с `mkstream` — но она и не нужна: `MKSTREAM` подставляется всегда (проверено в байткоде `DefaultStreamOperations`). Флаг `mkstream` есть только в низкоуровневом `RedisConnection.xGroupCreate(key, group, offset, mkstream)`.
- `XAUTOCLAIM` в API **нет** — reclaim собирается из `pending()` + `claim()`.
- `acknowledge` в `StreamOperations` имеет порядок аргументов **(key, group, recordId)** — перепутать легко, и тогда `XACK` уйдёт не в тот канал или в несуществующую группу.
- `MapRecord.getValue()` отдаёт карту полей сообщения; в ней ожидается единственный ключ `payload`. Отсутствие ключа — повод вернуть ошибку в канал, а не молчаливый `NPE`.
