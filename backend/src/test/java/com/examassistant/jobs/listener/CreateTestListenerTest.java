package com.examassistant.jobs.listener;

import com.examassistant.jobs.DTO.TestResultResponse;
import com.examassistant.messaging.TaskService;
import com.examassistant.support.TestFixtures;
import com.examassistant.tests.QuestionService;
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

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CreateTestListenerTest {

    private static final String TEST_JSON =
            "{\"task_id\":\"77777777-7777-7777-7777-777777777777\",\"status\":\"finished\"}";

    @Mock
    private StringRedisTemplate redisTemplate;
    @Mock
    private StreamOperations<String, Object, Object> streamOperations;
    @Mock
    private TaskService taskService;
    @Mock
    private QuestionService questionService;
    @Mock
    private ObjectMapper objectMapper;

    @InjectMocks
    private CreateTestListener listener;

    @Test
    void onMessage_validMessage_changesTaskStatusAndAcknowledges() {
        Map<String, String> fields = Map.of(
                "task_id", TestFixtures.TASK_ID.toString(),
                "amount_questions", "medium",
                "status", "finished",
                "test_id", TestFixtures.TEST_ID.toString(),
                "test", TEST_JSON
        );
        MapRecord<String, String, String> message = message(fields);
        RecordId recordId = RecordId.of("1-0");
        when(message.getId()).thenReturn(recordId);
        when(redisTemplate.<Object, Object>opsForStream()).thenReturn(streamOperations);

        listener.onMessage(message);

        verify(taskService).changeStatus(TestFixtures.TASK_ID);
        verify(objectMapper).readValue(TEST_JSON, TestResultResponse.class);
        verify(streamOperations).acknowledge(
                "tests:create-test-response", "test-handlers", recordId);
    }

    @Test
    void onMessage_missingTaskId_throwsAndDoesNotAcknowledge() {
        MapRecord<String, String, String> message = message(Map.of(
                "test_id", TestFixtures.TEST_ID.toString()
        ));

        assertThatThrownBy(() -> listener.onMessage(message))
                .isInstanceOf(NullPointerException.class);

        verifyNoInteractions(taskService, questionService, streamOperations, redisTemplate, objectMapper);
    }

    @Test
    void onMessage_malformedTaskId_throwsAndDoesNotAcknowledge() {
        MapRecord<String, String, String> message = message(Map.of(
                "task_id", "not-a-uuid",
                "test_id", TestFixtures.TEST_ID.toString()
        ));

        assertThatThrownBy(() -> listener.onMessage(message))
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(taskService, questionService, streamOperations, redisTemplate, objectMapper);
    }

    @SuppressWarnings("unchecked")
    private MapRecord<String, String, String> message(Map<String, String> fields) {
        MapRecord<String, String, String> message = mock(MapRecord.class);
        when(message.getValue()).thenReturn(fields);
        return message;
    }
}
