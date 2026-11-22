package com.examassistant.jobs.service;

import com.examassistant.common.config.MlStreamsProperties;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.RedisStreamCommands.XDelOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
@Slf4j
public class MlResultAckSupport {
    private final StringRedisTemplate redisTemplate;
    private final MlStreamsProperties properties;

    public String payload(MapRecord<String, String, String> message) {
        String payload = message.getValue().get("payload");
        if (payload == null || payload.isBlank()) {
            throw new IllegalArgumentException("Redis message must contain a non-empty payload");
        }
        return payload;
    }

    public void ack(MapRecord<String, String, String> message) {
        try {
            redisTemplate.opsForStream().acknowledgeAndDelete(
                    message.getStream(),
                    properties.getConsumerGroup(),
                    XDelOptions.defaults(),
                    message.getId()
            );
        } catch (RuntimeException e) {
            log.error("Failed to acknowledge ML result channel={} msg_id={}", message.getStream(), message.getId(), e);
        }
    }

    public void ackPoison(MapRecord<String, String, String> message, RuntimeException error) {
        log.error("Discarding invalid ML result channel={} msg_id={}: {}",
                message.getStream(), message.getId(), error.getMessage());
        ack(message);
    }
}
