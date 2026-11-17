package com.examassistant.jobs.listener;

import com.examassistant.ml.MlChannels;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import tools.jackson.databind.ObjectMapper;

/**
 * Обработчик результата ML.
 *
 * Формат сообщения: XADD &lt;канал&gt; * payload '&lt;JSON&gt;'. Разбор конверта и
 * подтверждение сообщения — общие для всех типов задач, различается только
 * разбор payload.
 *
 * Сообщение подтверждается только после успешной обработки: необработанное
 * остаётся в pending-списке канала, где его видно в XPENDING.
 */
@Slf4j
public abstract class MlResultListener<T> implements StreamListener<String, MapRecord<String, String, String>> {

    private final StringRedisTemplate redisTemplate;
    private final MlChannels channels;
    private final ObjectMapper objectMapper;
    private final Class<T> payloadType;

    protected MlResultListener(StringRedisTemplate redisTemplate,
                               MlChannels channels,
                               ObjectMapper objectMapper,
                               Class<T> payloadType) {
        this.redisTemplate = redisTemplate;
        this.channels = channels;
        this.objectMapper = objectMapper;
        this.payloadType = payloadType;
    }

    @Override
    public void onMessage(MapRecord<String, String, String> message) {
        try {
            handle(parse(message));
            acknowledge(message);
        } catch (Exception e) {
            log.error("Не удалось обработать результат ML из канала {}: {}",
                    message.getStream(), e.getMessage(), e);
        }
    }

    private T parse(MapRecord<String, String, String> message) {
        String payload = message.getValue().get("payload");
        if (payload == null) {
            throw new IllegalStateException("В сообщении нет поля payload");
        }
        return objectMapper.readValue(payload, payloadType);
    }

    /**
     * Подтверждаем сообщение в том же канале, откуда его получили: у каждого
     * типа задачи своя consumer-группа на своём канале.
     */
    private void acknowledge(MapRecord<String, String, String> message) {
        redisTemplate.opsForStream()
                .acknowledge(message.getStream(), channels.consumerGroup(), message.getId());
    }

    protected abstract void handle(T result);
}
