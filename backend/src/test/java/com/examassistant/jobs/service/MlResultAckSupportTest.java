package com.examassistant.jobs.service;

import com.examassistant.common.config.MlStreamsProperties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.connection.RedisStreamCommands.XDelOptions;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StreamOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MlResultAckSupportTest {
    @Mock private StringRedisTemplate redisTemplate;
    @Mock private StreamOperations<String, String, String> streams;
    @Mock private MlStreamsProperties properties;
    @InjectMocks private MlResultAckSupport support;

    @Test
    void payload_returnsTheOnlyEnvelopeField() {
        MapRecord<String, String, String> message = message("create-test:ml-to-be", "1-0", "{\"status\":\"ok\"}");

        assertThat(support.payload(message)).isEqualTo("{\"status\":\"ok\"}");
    }

    @Test
    void payload_missingField_isRejected() {
        MapRecord<String, String, String> message = mock(MapRecord.class);
        when(message.getValue()).thenReturn(Map.of());

        assertThatThrownBy(() -> support.payload(message))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void ack_usesSourceStreamGroupAndDelete() {
        MapRecord<String, String, String> message = message("grade-test:ml-to-be", "1-0", "{}");
        when(redisTemplate.<String, String>opsForStream()).thenReturn(streams);
        when(properties.getConsumerGroup()).thenReturn("ml-backend");

        support.ack(message);

        verify(streams).acknowledgeAndDelete(eq("grade-test:ml-to-be"), eq("ml-backend"),
                any(XDelOptions.class), eq(RecordId.of("1-0")));
    }

    @SuppressWarnings("unchecked")
    private MapRecord<String, String, String> message(String channel, String id, String payload) {
        MapRecord<String, String, String> message = mock(MapRecord.class);
        org.mockito.Mockito.lenient().when(message.getValue()).thenReturn(Map.of("payload", payload));
        org.mockito.Mockito.lenient().when(message.getStream()).thenReturn(channel);
        org.mockito.Mockito.lenient().when(message.getId()).thenReturn(RecordId.of(id));
        return message;
    }
}
