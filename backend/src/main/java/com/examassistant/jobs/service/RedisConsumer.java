package com.examassistant.jobs.service;

import com.examassistant.common.config.MlStreamsProperties;
import com.examassistant.common.redis.MlChannels;
import com.examassistant.jobs.listener.CreateTestListener;
import com.examassistant.jobs.listener.GradeTestListener;
import com.examassistant.jobs.listener.ProcessingMaterialListener;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.SmartLifecycle;
import org.springframework.data.domain.Range;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.PendingMessage;
import org.springframework.data.redis.connection.stream.PendingMessages;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StreamOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * Подписка backend'а на три канала результатов ML.
 *
 * Consumer-группа одна ({@code ml-backend}), но она привязана к одному стриму,
 * поэтому группу создаём на каждом канале отдельно — сырой командой
 * {@code XGROUP CREATE ... 0-0 MKSTREAM}, каналы появляются на лету.
 *
 * XACK не настроен: подтверждает сам listener после успешной обработки.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class RedisConsumer implements SmartLifecycle {

    private static final long PENDING_BATCH_SIZE = 50L;

    private final StreamMessageListenerContainer<String, MapRecord<String, String, String>> container;
    private final StringRedisTemplate redisTemplate;
    private final ProcessingMaterialListener ingestListener;
    private final CreateTestListener createTestListener;
    private final GradeTestListener gradeTestListener;
    private final MlStreamsProperties properties;

    private volatile boolean running;

    @Override
    public void start() {
        String group = properties.getConsumerGroup();
        String consumerName = properties.getConsumerName();

        for (String channel : MlChannels.resultChannels()) {
            createConsumerGroup(channel, group);
        }

        for (String channel : MlChannels.resultChannels()) {
            // Consumer.from(group, consumerName) — порядок именно такой:
            // первым идёт ИМЯ ГРУППЫ, вторым имя консьюмера. Наоборот — backend
            // читает группой "backend-1", которой не существует → NOGROUP.
            container.receive(Consumer.from(group, consumerName),
                    StreamOffset.create(channel, ReadOffset.lastConsumed()),
                    listenerFor(channel));
        }
        container.start();
        running = true;
        log.info("Subscribed to ML result channels {} as {} / {}", MlChannels.resultChannels(), group, consumerName);
    }

    /**
     * Создаёт consumer-группу на канале результатов.
     *
     * <p>Команда уходит в Redis сырой строкой, а не через
     * {@code opsForStream().createGroup(...)}: там идентификатор группы
     * берётся из {@link ReadOffset#lastConsumed()} — это «>», а такой
     * идентификатор {@code XGROUP CREATE} не принимает («ERR Invalid stream
     * ID specified as stream command argument»). Плюс нужен {@code MKSTREAM},
     * чтобы канал создавался на лету, до первого сообщения ML.
     *
     * <p>Смещение {@code 0-0} — группа читает поток с самого начала, так что
     * результаты, опубликованные ML пока backend лежал, не теряются.
     */
    private void createConsumerGroup(String channel, String group) {
        try {
            redisTemplate.execute((RedisCallback<Object>) conn -> conn.execute("XGROUP", "CREATE".getBytes(),
                    channel.getBytes(), group.getBytes(), "0-0".getBytes(), "MKSTREAM".getBytes()));
            log.info("Consumer group {} created on channel {}", group, channel);
        } catch (RuntimeException e) {
            // BUSYGROUP — группа уже есть (backend перезапустился), это штатно.
            if (isBusyGroup(e)) {
                log.info("Consumer group {} on channel {} already exists", group, channel);
                return;
            }
            // Любая другая ошибка — транспорт не работает: логируем громко,
            // но приложение не роняем, иначе стенд поднять не получится.
            log.error("Failed to create consumer group {} on channel {}: {}", group, channel, e.getMessage(), e);
        }
    }

    /**
     * Проверяет, что ошибка — это именно BUSYGROUP (группа уже существует),
     * а не что-то другое. Сообщение Lettuce может быть обёрнуто в несколько
     * слоёв, поэтому ищем маркер во всей цепочке причин.
     */
    private boolean isBusyGroup(Throwable error) {
        for (Throwable cause = error; cause != null; cause = cause.getCause()) {
            String message = cause.getMessage();
            if (message != null && message.contains("BUSYGROUP")) {
                return true;
            }
            if (cause.getCause() == cause) {
                break;
            }
        }
        return false;
    }

    @Override
    public void stop() {
        running = false;
        container.stop();
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return SmartLifecycle.DEFAULT_PHASE - 10;
    }

    /**
     * Возврат зависших сообщений: забираем pending, которые долго лежат без
     * обработки. Сообщения, которые не удалось обработать слишком много раз,
     * считаем poison — подтверждаем и удаляем, не перечитывая.
     */
    @Scheduled(fixedDelayString = "${ml.streams.reclaim-interval-ms:60000}")
    public void reclaimPending() {
        String group = properties.getConsumerGroup();
        String consumerName = properties.getConsumerName();
        StreamOperations<String, String, String> streams = redisTemplate.opsForStream();

        for (String channel : MlChannels.resultChannels()) {
            PendingMessages pending;
            try {
                pending = streams.pending(channel, group, Range.unbounded(), PENDING_BATCH_SIZE,
                        properties.getReclaimIdle());
            } catch (RuntimeException e) {
                log.warn("Failed to read pending messages on channel {}: {}", channel, e.getMessage());
                continue;
            }
            if (pending == null) {
                continue;
            }
            for (PendingMessage message : pending) {
                reclaim(streams, channel, group, consumerName, message);
            }
        }
    }

    private void reclaim(StreamOperations<String, String, String> streams, String channel, String group,
                         String consumerName, PendingMessage message) {
        RecordId id = message.getId();
        if (message.getTotalDeliveryCount() >= properties.getReclaimMaxAttempts()) {
            log.error("Dropping poison message channel={} msg_id={} deliveries={}",
                    channel, id, message.getTotalDeliveryCount());
            // XACKDEL есть только в Redis 8.2+, у нас Redis 7.4 — команда не поддерживается.
            // Подтверждаем и удаляем отдельно: XACK, затем XDEL (удаление после подтверждения).
            streams.acknowledge(channel, group, id);
            streams.delete(channel, id);
            return;
        }
        List<MapRecord<String, String, String>> claimed = streams.claim(channel, group, consumerName,
                properties.getReclaimIdle(), id);
        if (claimed == null) {
            return;
        }
        StreamListener<String, MapRecord<String, String, String>> listener = listenerFor(channel);
        for (MapRecord<String, String, String> record : claimed) {
            listener.onMessage(record);
        }
    }

    private StreamListener<String, MapRecord<String, String, String>> listenerFor(String channel) {
        if (channel.equals(MlChannels.resultChannel(MlChannels.INGEST))) {
            return ingestListener;
        }
        if (channel.equals(MlChannels.resultChannel(MlChannels.CREATE_TEST))) {
            return createTestListener;
        }
        if (channel.equals(MlChannels.resultChannel(MlChannels.GRADE_TEST))) {
            return gradeTestListener;
        }
        throw new IllegalArgumentException("Unknown ML result channel: " + channel);
    }
}
