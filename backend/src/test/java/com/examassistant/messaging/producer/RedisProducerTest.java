package com.examassistant.messaging.producer;

import com.examassistant.common.enums.TestAmountQuestions;
import com.examassistant.messaging.CreateTestRedisRequest;
import com.examassistant.messaging.GradeAttemptRedisRequest;
import com.examassistant.messaging.ProcessMaterialRedisRequest;
import com.examassistant.messaging.TaskDTO;
import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.messaging.service.TasksService;
import com.examassistant.ml.MlChannels;
import com.examassistant.support.TestFixtures;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StreamOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import tools.jackson.databind.ObjectMapper;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class RedisProducerTest {

    @Mock
    private StringRedisTemplate redisTemplate;
    @Mock
    private StreamOperations<String, Object, Object> streamOperations;
    @Mock
    private TasksService taskService;

    private RedisProducer redisProducer;
    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() {
        when(redisTemplate.<Object, Object>opsForStream()).thenReturn(streamOperations);
        objectMapper = new ObjectMapper();
        redisProducer = new RedisProducer(
                redisTemplate,
                new MlChannels("ml-tasks", "ml-results", "ml-backend", "backend-1"),
                taskService,
                objectMapper);
    }

    @Test
    void publishCreateTest_writesPayloadToTaskChannel() {
        CreateTestRedisRequest request = TestFixtures.createTestRedisRequest();
        RecordId recordId = RecordId.of("1-0");
        when(streamOperations.add(eq("ml-tasks:create_test"), anyMap())).thenReturn(recordId);

        RecordId result = redisProducer.publishCreateTest(request);

        assertThat(result).isSameAs(recordId);

        Map<String, Object> payload = payloadOf("ml-tasks:create_test");
        assertThat(payload)
                .containsEntry("task_id", TestFixtures.TASK_ID.toString())
                .containsEntry("test_id", TestFixtures.TEST_ID.toString())
                .containsEntry("title", "Math test")
                .containsEntry("amountQuestions", 10)
                .containsEntry("difficulty", "medium")
                .containsEntry("course_id", TestFixtures.COURSE_ID.toString());
        assertThat(payload.get("material_ids"))
                .isEqualTo(List.of(TestFixtures.MATERIAL_ID.toString(), TestFixtures.OTHER_MATERIAL_ID.toString()));
    }

    @Test
    void publishCreateTest_createsProcessingTask() {
        when(streamOperations.add(anyString(), anyMap())).thenReturn(RecordId.of("1-0"));

        redisProducer.publishCreateTest(TestFixtures.createTestRedisRequest());

        ArgumentCaptor<TaskDTO> captor = ArgumentCaptor.forClass(TaskDTO.class);
        verify(taskService).create(eq(TestFixtures.TASK_ID), captor.capture());
        TaskDTO task = captor.getValue();

        assertThat(task.getTestId()).isEqualTo(TestFixtures.TEST_ID);
        assertThat(task.getCourseId()).isEqualTo(TestFixtures.COURSE_ID);
        assertThat(task.getTitle()).isEqualTo("Math test");
        assertThat(task.getStatusTask()).isEqualTo(StatusTask.PROCESSING);
        assertThat(task.getAmountQuestions()).isEqualTo(TestAmountQuestions.MEDIUM);
        assertThat(task.getDifficulty()).isEqualTo("medium");
        assertThat(task.getCreatedAt()).isNotNull();
        assertThat(task.getFinishedAt()).isNull();
    }

    @Test
    void publishMaterialProcess_writesPayloadToTaskChannel() {
        ProcessMaterialRedisRequest request = TestFixtures.processMaterialRedisRequest();
        RecordId recordId = RecordId.of("2-0");
        when(streamOperations.add(eq("ml-tasks:ingest"), anyMap())).thenReturn(recordId);

        RecordId result = redisProducer.publishMaterialProcess(request);

        assertThat(result).isSameAs(recordId);

        Map<String, Object> payload = payloadOf("ml-tasks:ingest");
        assertThat(payload)
                .containsEntry("task_id", TestFixtures.TASK_ID.toString())
                .containsEntry("material_id", TestFixtures.MATERIAL_ID.toString())
                .containsEntry("storage_key", "materials/key.pdf");
    }

    @Test
    void publishMaterialProcess_doesNotCreateTask() {
        when(streamOperations.add(anyString(), anyMap())).thenReturn(RecordId.of("3-0"));

        redisProducer.publishMaterialProcess(TestFixtures.processMaterialRedisRequest());

        verifyNoInteractions(taskService);
    }

    @Test
    void publishGradeAttempt_writesAnswersToTaskChannel() {
        GradeAttemptRedisRequest request = TestFixtures.gradeAttemptRedisRequest();
        RecordId recordId = RecordId.of("4-0");
        when(streamOperations.add(eq("ml-tasks:grade_attempt"), anyMap())).thenReturn(recordId);

        RecordId result = redisProducer.publishGradeAttempt(request);

        assertThat(result).isSameAs(recordId);

        Map<String, Object> payload = payloadOf("ml-tasks:grade_attempt");
        assertThat(payload)
                .containsEntry("task_id", TestFixtures.TASK_ID.toString())
                .containsEntry("attempt_id", TestFixtures.ATTEMPT_ID.toString())
                .containsEntry("test_id", TestFixtures.TEST_ID.toString())
                .containsEntry("user_id", TestFixtures.USER_ID.toString());

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> answers = (List<Map<String, Object>>) payload.get("answers");
        assertThat(answers).hasSize(1);
        assertThat(answers.get(0)).containsEntry("question_id", TestFixtures.QUESTION_ID.toString());
        assertThat(answers.get(0).get("student_answer")).isEqualTo(Map.of("index", 1));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> payloadOf(String channel) {
        ArgumentCaptor<Map> captor = ArgumentCaptor.forClass(Map.class);
        verify(streamOperations).add(eq(channel), captor.capture());
        String json = (String) captor.getValue().get("payload");
        return objectMapper.readValue(json, Map.class);
    }
}
