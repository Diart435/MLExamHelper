package com.examassistant.messaging.producer;

import com.examassistant.common.enums.TestAmountQuestions;
import com.examassistant.messaging.CreateTestRedisRequest;
import com.examassistant.messaging.GradeTestRedisRequest;
import com.examassistant.messaging.ProcessMaterialRedisRequest;
import com.examassistant.messaging.StudentAnswerPayload;
import com.examassistant.messaging.TaskDTO;
import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.messaging.service.TasksService;
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

    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void setUp() {
        when(redisTemplate.<Object, Object>opsForStream()).thenReturn(streamOperations);
        redisProducer = new RedisProducer(redisTemplate, taskService, objectMapper);
    }

    @Test
    void publishCreateTest_writesContractEnvelopeToChannel() {
        CreateTestRedisRequest request = TestFixtures.createTestRedisRequest();
        RecordId recordId = RecordId.of("1-0");
        when(streamOperations.add(eq("create-test:be-to-ml"), anyMap())).thenReturn(recordId);

        RecordId result = redisProducer.publishCreateTest(request);

        assertThat(result).isSameAs(recordId);

        Map<String, Object> payload = capturedPayload("create-test:be-to-ml");
        assertThat(payload)
                .containsEntry("task_id", TestFixtures.TASK_ID.toString())
                .containsEntry("test_id", TestFixtures.TEST_ID.toString())
                .containsEntry("title", "Math test")
                .containsEntry("difficulty", "medium");
    }

    @Test
    void publishCreateTest_payloadHasExactlyFiveContractKeys() {
        when(streamOperations.add(anyString(), anyMap())).thenReturn(RecordId.of("1-0"));

        redisProducer.publishCreateTest(TestFixtures.createTestRedisRequest());

        Map<String, Object> payload = capturedPayload("create-test:be-to-ml");
        // Контракт v4.2: ровно пять полей, amount_questions больше нет —
        // размер теста целиком выбирает ML-планировщик.
        assertThat(payload)
                .containsOnlyKeys("task_id", "test_id", "material_ids", "title", "difficulty")
                .hasSize(5)
                .doesNotContainKey("amount_questions")
                .doesNotContainKey("amountQuestions")
                .doesNotContainKey("course_id")
                .doesNotContainKey("type");
    }

    @Test
    void publishCreateTest_materialIdsIsJsonArray() {
        when(streamOperations.add(anyString(), anyMap())).thenReturn(RecordId.of("1-0"));

        redisProducer.publishCreateTest(TestFixtures.createTestRedisRequest());

        Map<String, Object> payload = capturedPayload("create-test:be-to-ml");
        assertThat(payload.get("material_ids")).isInstanceOf(List.class);
        assertThat((List<String>) payload.get("material_ids"))
                .containsExactly(TestFixtures.MATERIAL_ID.toString(), TestFixtures.OTHER_MATERIAL_ID.toString());
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
    void publishMaterialProcess_writesContractEnvelopeToChannel() {
        ProcessMaterialRedisRequest request = TestFixtures.processMaterialRedisRequest();
        RecordId recordId = RecordId.of("2-0");
        when(streamOperations.add(eq("ingest:be-to-ml"), anyMap())).thenReturn(recordId);

        RecordId result = redisProducer.publishMaterialProcess(request);

        assertThat(result).isSameAs(recordId);

        Map<String, Object> payload = capturedPayload("ingest:be-to-ml");
        assertThat(payload)
                .containsEntry("material_id", TestFixtures.MATERIAL_ID.toString())
                .containsEntry("storage_key", "materials/key.pdf")
                // У ingest в контракте ровно два поля.
                .doesNotContainKey("task_id")
                .doesNotContainKey("type")
                .hasSize(2);
    }

    @Test
    void publishMaterialProcess_doesNotCreateTask() {
        when(streamOperations.add(anyString(), anyMap())).thenReturn(RecordId.of("3-0"));

        redisProducer.publishMaterialProcess(TestFixtures.processMaterialRedisRequest());

        verifyNoInteractions(taskService);
    }

    @Test
    void publishGradeTest_writesAnswersWithTypedStudentAnswer() {
        when(streamOperations.add(anyString(), anyMap())).thenReturn(RecordId.of("4-0"));

        redisProducer.publishGradeTest(new GradeTestRedisRequest(
                TestFixtures.TASK_ID,
                TestFixtures.ATTEMPT_ID,
                TestFixtures.TEST_ID,
                List.of(
                        new GradeTestRedisRequest.Answer(TestFixtures.QUESTION_ID, StudentAnswerPayload.single(1)),
                        new GradeTestRedisRequest.Answer(TestFixtures.OTHER_MATERIAL_ID, StudentAnswerPayload.open("four"))
                )
        ));

        Map<String, Object> payload = capturedPayload("grade-test:be-to-ml");
        assertThat(payload)
                .containsEntry("task_id", TestFixtures.TASK_ID.toString())
                .containsEntry("attempt_id", TestFixtures.ATTEMPT_ID.toString())
                .containsEntry("test_id", TestFixtures.TEST_ID.toString());

        List<?> answers = (List<?>) payload.get("answers");
        assertThat(answers).hasSize(2);

        Map<String, Object> first = toMap(answers.get(0));
        assertThat(first).containsEntry("question_id", TestFixtures.QUESTION_ID.toString());
        assertThat(toMap(first.get("student_answer"))).containsExactly(Map.entry("index", 1));

        Map<String, Object> second = toMap(answers.get(1));
        assertThat(toMap(second.get("student_answer"))).containsExactly(Map.entry("text", "four"));
    }

    /**
     * Достаёт payload из конверта {@code XADD <канал> * payload '<JSON>'}:
     * в стриме ровно одно поле — payload, внутри JSON-объект задачи.
     */
    @SuppressWarnings("rawtypes")
    private Map<String, Object> capturedPayload(String channel) {
        ArgumentCaptor<Map> captor = ArgumentCaptor.forClass(Map.class);
        verify(streamOperations).add(eq(channel), captor.capture());
        Map<String, String> envelope = (Map<String, String>) captor.getValue();
        assertThat(envelope).hasSize(1).containsKey("payload");
        return objectMapper.readValue(envelope.get("payload"), Map.class);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> toMap(Object value) {
        return (Map<String, Object>) value;
    }
}
