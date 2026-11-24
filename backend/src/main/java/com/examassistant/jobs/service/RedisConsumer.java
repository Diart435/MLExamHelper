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
            log.error("Failed to create consumer group {} on channel {}: {}", group, channel, e.getMessage(), e);
        }
    }

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
