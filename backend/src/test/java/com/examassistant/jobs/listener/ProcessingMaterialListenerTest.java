package com.examassistant.jobs.listener;

import com.examassistant.materials.MaterialService;
import com.examassistant.ml.MlChannels;
import com.examassistant.ml.payload.MlIngestResult;
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
import tools.jackson.databind.ObjectMapper;

import java.util.Map;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ProcessingMaterialListenerTest {

    private static final String CHANNEL = "ml-results:ingest";
    private static final String GROUP = "ml-backend";

    @Mock
    private StringRedisTemplate redisTemplate;
    @Mock
    private StreamOperations<String, Object, Object> streamOperations;
    @Mock
    private MlChannels channels;
    @Mock
    private MaterialService materialService;
    @Mock
    private ObjectMapper objectMapper;

    @InjectMocks
    private ProcessingMaterialListener listener;

    @Test
    void onMessage_ready_changesStatusAndAcknowledges() {
        when(objectMapper.readValue(anyString(), eq(MlIngestResult.class)))
                .thenReturn(TestFixtures.mlIngestResult("ready"));
        MapRecord<String, String, String> message = message();
        stubAcknowledgement(message);

        listener.onMessage(message);

        verify(materialService).changeStatus(TestFixtures.MATERIAL_ID, "ready");
        verify(streamOperations).acknowledge(CHANNEL, GROUP, RecordId.of("1-0"));
    }

    @Test
    void onMessage_error_changesStatusToError() {
        when(objectMapper.readValue(anyString(), eq(MlIngestResult.class)))
                .thenReturn(TestFixtures.mlIngestResult("error"));
        MapRecord<String, String, String> message = message();
        stubAcknowledgement(message);

        listener.onMessage(message);

        verify(materialService).changeStatus(TestFixtures.MATERIAL_ID, "error");
        verify(streamOperations).acknowledge(CHANNEL, GROUP, RecordId.of("1-0"));
    }

    @Test
    void onMessage_withoutPayload_doesNotAcknowledge() {
        MapRecord<String, String, String> message = message(Map.of());

        listener.onMessage(message);

        verifyNoInteractions(materialService, streamOperations);
    }

    private void stubAcknowledgement(MapRecord<String, String, String> message) {
        when(message.getId()).thenReturn(RecordId.of("1-0"));
        when(redisTemplate.<Object, Object>opsForStream()).thenReturn(streamOperations);
        when(channels.consumerGroup()).thenReturn(GROUP);
    }

    @SuppressWarnings("unchecked")
    private MapRecord<String, String, String> message() {
        return message(Map.of("payload", "{}"));
    }

    @SuppressWarnings("unchecked")
    private MapRecord<String, String, String> message(Map<String, String> fields) {
        MapRecord<String, String, String> message = mock(MapRecord.class);
        when(message.getValue()).thenReturn(fields);
        when(message.getStream()).thenReturn(CHANNEL);
        return message;
    }
}
