package com.examassistant.jobs;

import com.examassistant.jobs.listener.CreateTestListener;
import com.examassistant.jobs.listener.GradeAttemptListener;
import com.examassistant.jobs.listener.ProcessingMaterialListener;
import com.examassistant.ml.MlChannels;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;
import org.springframework.stereotype.Component;

/**
 * Подписка backend'а на каналы результатов ML.
 *
 * У каждого типа задачи свой канал и своя consumer-группа: сообщение нельзя
 * прочитать не тем обработчиком. Группа создаётся с MKSTREAM, поэтому каналы
 * создаются на лету первым же сообщением ML.
 *
 * Читаем с lastConsumed (">"): сообщения, опубликованные пока backend лежал,
 * не теряются — группа отдаст их при первом же чтении после поднятия.
 *
 * Живёт в модуле jobs рядом с обработчиками: подписка знает их конкретные
 * типы, а модуль ml (словарь контракта) не должен зависеть от jobs.
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class MlResultsSubscriber {

    private final StringRedisTemplate redisTemplate;
    private final StreamMessageListenerContainer<String, MapRecord<String, String, String>> container;
    private final MlChannels channels;
    private final ProcessingMaterialListener materialListener;
    private final CreateTestListener createTestListener;
    private final GradeAttemptListener gradeAttemptListener;

    @EventListener(ApplicationReadyEvent.class)
    public void subscribe() {
        subscribe(channels.resultChannel(MlChannels.INGEST), materialListener);
        subscribe(channels.resultChannel(MlChannels.CREATE_TEST), createTestListener);
        subscribe(channels.resultChannel(MlChannels.GRADE_ATTEMPT), gradeAttemptListener);
    }

    private void subscribe(String channel, StreamListener<String, MapRecord<String, String, String>> listener) {
        try {
            redisTemplate.opsForStream().createGroup(channel, ReadOffset.lastConsumed(), channels.consumerGroup());
        } catch (RuntimeException e) {
            if (!isBusyGroup(e)) {
                throw e;
            }
        }

        container.receive(
                Consumer.from(channels.consumerGroup(), channels.consumerName()),
                StreamOffset.create(channel, ReadOffset.lastConsumed()),
                listener);
        log.info("Backend подписан на канал {}", channel);
    }

    private boolean isBusyGroup(Throwable e) {
        while (e != null) {
            if (e.getMessage() != null && e.getMessage().contains("BUSYGROUP")) {
                return true;
            }
            e = e.getCause();
        }
        return false;
    }
}
