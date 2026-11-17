package com.examassistant.jobs.listener;

import com.examassistant.messaging.TaskService;
import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.ml.MlChannels;
import com.examassistant.ml.payload.MlCreateTestResult;
import com.examassistant.support.TestFixtures;
import com.examassistant.tests.TestService;
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

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CreateTestListenerTest {

    private static final String CHANNEL = "ml-results:create_test";
    private static final String GROUP = "ml-backend";

    @Mock
    private StringRedisTemplate redisTemplate;
    @Mock
    private StreamOperations<String, Object, Object> streamOperations;
    @Mock
    private MlChannels channels;
    @Mock
    private TestService testService;
    @Mock
    private TaskService taskService;
    @Mock
    private ObjectMapper objectMapper;

    @InjectMocks
    private CreateTestListener listener;

    @Test
    void onMessage_ok_appliesTestAndFinishesTask() {
        MlCreateTestResult result = TestFixtures.mlCreateTestResult();
        when(objectMapper.readValue(anyString(), eq(MlCreateTestResult.class))).thenReturn(result);
        MapRecord<String, String, String> message = message(Map.of("payload", "{}"));
        stubAcknowledgement(message);

        listener.onMessage(message);

        verify(testService).applyGeneratedTest(result);
        verify(testService, never()).markGenerationFailed(any());
        verify(taskService).changeStatus(TestFixtures.TASK_ID, StatusTask.FINISHED);
        verify(streamOperations).acknowledge(CHANNEL, GROUP, RecordId.of("1-0"));
    }

    @Test
    void onMessage_error_marksTestAndTaskFailed() {
        MlCreateTestResult result = new MlCreateTestResult(
                TestFixtures.TASK_ID.toString(), "error", TestFixtures.TEST_ID.toString(), null, "no material");
        when(objectMapper.readValue(anyString(), eq(MlCreateTestResult.class))).thenReturn(result);
        MapRecord<String, String, String> message = message(Map.of("payload", "{}"));
        stubAcknowledgement(message);

        listener.onMessage(message);

        verify(testService).markGenerationFailed(result);
        verify(testService, never()).applyGeneratedTest(any());
        verify(taskService).changeStatus(TestFixtures.TASK_ID, StatusTask.ERROR);
        verify(streamOperations).acknowledge(CHANNEL, GROUP, RecordId.of("1-0"));
    }

    @Test
    void onMessage_malformedPayload_doesNotAcknowledge() {
        when(objectMapper.readValue(anyString(), eq(MlCreateTestResult.class)))
                .thenThrow(new IllegalStateException("broken json"));
        MapRecord<String, String, String> message = message(Map.of("payload", "{"));

        listener.onMessage(message);

        verifyNoInteractions(testService, taskService, streamOperations);
    }

    @Test
    void onMessage_withoutPayload_doesNotAcknowledge() {
        MapRecord<String, String, String> message = message(Map.of());

        listener.onMessage(message);

        verifyNoInteractions(testService, taskService, streamOperations);
    }

    private void stubAcknowledgement(MapRecord<String, String, String> message) {
        when(message.getId()).thenReturn(RecordId.of("1-0"));
        when(redisTemplate.<Object, Object>opsForStream()).thenReturn(streamOperations);
        when(channels.consumerGroup()).thenReturn(GROUP);
    }

    @SuppressWarnings("unchecked")
    private MapRecord<String, String, String> message(Map<String, String> fields) {
        MapRecord<String, String, String> message = mock(MapRecord.class);
        when(message.getValue()).thenReturn(fields);
        when(message.getStream()).thenReturn(CHANNEL);
        return message;
    }
}
