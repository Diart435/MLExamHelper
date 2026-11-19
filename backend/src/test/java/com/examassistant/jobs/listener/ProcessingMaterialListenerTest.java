package com.examassistant.jobs.listener;

import com.examassistant.materials.MaterialService;
import com.examassistant.support.TestFixtures;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StreamOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ProcessingMaterialListenerTest {

    @Mock
    private StringRedisTemplate redisTemplate;
    @Mock
    private StreamOperations<String, Object, Object> streamOperations;
    @Mock
    private MaterialService materialService;

    @InjectMocks
    private ProcessingMaterialListener listener;

    @Test
    void onMessage_validMessage_changesStatusAndAcknowledges() {
        MapRecord<String, String, String> message = message(Map.of(
                "material_id", TestFixtures.MATERIAL_ID.toString(),
                "status", "ready"
        ));
        RecordId recordId = RecordId.of("1-0");
        when(message.getId()).thenReturn(recordId);
        when(redisTemplate.<Object, Object>opsForStream()).thenReturn(streamOperations);

        listener.onMessage(message);

        verify(materialService).changeStatus(TestFixtures.MATERIAL_ID, "ready");
        verify(streamOperations).acknowledge(
                "materials:process-response", "material-status-handlers", recordId);
    }

    @Test
    void onMessage_missingMaterialId_throwsAndDoesNotAcknowledge() {
        MapRecord<String, String, String> message = message(Map.of(
                "status", "ready"
        ));

        assertThatThrownBy(() -> listener.onMessage(message))
                .isInstanceOf(NullPointerException.class);

        verifyNoInteractions(materialService, streamOperations, redisTemplate);
    }

    @Test
    void onMessage_malformedMaterialId_throwsAndDoesNotAcknowledge() {
        MapRecord<String, String, String> message = message(Map.of(
                "material_id", "not-a-uuid",
                "status", "ready"
        ));

        assertThatThrownBy(() -> listener.onMessage(message))
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(materialService, streamOperations, redisTemplate);
    }

    @SuppressWarnings("unchecked")
    private MapRecord<String, String, String> message(Map<String, String> fields) {
        MapRecord<String, String, String> message = mock(MapRecord.class);
        when(message.getValue()).thenReturn(fields);
        return message;
    }
}
