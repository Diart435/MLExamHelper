package com.examassistant.messaging.producer;

import com.examassistant.common.enums.TestAmountQuestions;
import com.examassistant.messaging.CreateTestRedisRequest;
import com.examassistant.messaging.ProcessMaterialRedisRequest;
import com.examassistant.messaging.TaskDTO;
import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.messaging.service.TasksService;
import com.examassistant.support.TestFixtures;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StreamOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

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

    @InjectMocks
    private RedisProducer redisProducer;

    @BeforeEach
    void setUp() {
        when(redisTemplate.<Object, Object>opsForStream()).thenReturn(streamOperations);
    }

    @Test
    void publishCreateTest_writesAllFieldsToStream() {
        CreateTestRedisRequest request = TestFixtures.createTestRedisRequest();
        RecordId recordId = RecordId.of("1-0");
        when(streamOperations.add(eq("tests:create-test-request"), anyMap()))
                .thenReturn(recordId);

        RecordId result = redisProducer.publishCreateTest(request);

        assertThat(result).isSameAs(recordId);

        @SuppressWarnings("rawtypes")
        ArgumentCaptor<Map> captor = ArgumentCaptor.forClass(Map.class);
        verify(streamOperations).add(eq("tests:create-test-request"), captor.capture());
        @SuppressWarnings("unchecked")
        Map<String, String> fields = (Map<String, String>) captor.getValue();

        assertThat(fields)
                .containsEntry("task_id", TestFixtures.TASK_ID.toString())
                .containsEntry("test_id", TestFixtures.TEST_ID.toString())
                .containsEntry("material_ids",
                        TestFixtures.MATERIAL_ID + "," + TestFixtures.OTHER_MATERIAL_ID)
                .containsEntry("title", "Math test")
                .containsEntry("amount_questions", "medium")
                .containsEntry("difficulty", "medium")
                .containsEntry("course_id", TestFixtures.COURSE_ID.toString());
    }

    @Test
    void publishCreateTest_createsProcessingTask() {
        CreateTestRedisRequest request = TestFixtures.createTestRedisRequest();
        when(streamOperations.add(anyString(), anyMap())).thenReturn(RecordId.of("1-0"));

        redisProducer.publishCreateTest(request);

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
    void publishMaterialProcess_writesAllFieldsToStream() {
        ProcessMaterialRedisRequest request = TestFixtures.processMaterialRedisRequest();
        RecordId recordId = RecordId.of("2-0");
        when(streamOperations.add(eq("materials:process-response"), anyMap()))
                .thenReturn(recordId);

        RecordId result = redisProducer.publishMaterialProcess(request);

        assertThat(result).isSameAs(recordId);

        @SuppressWarnings("rawtypes")
        ArgumentCaptor<Map> captor = ArgumentCaptor.forClass(Map.class);
        verify(streamOperations).add(eq("materials:process-response"), captor.capture());
        @SuppressWarnings("unchecked")
        Map<String, String> fields = (Map<String, String>) captor.getValue();

        assertThat(fields)
                .containsEntry("task_id", TestFixtures.TASK_ID.toString())
                .containsEntry("material_id", TestFixtures.MATERIAL_ID.toString())
                .containsEntry("storage_key", "materials/key.pdf");
    }

    @Test
    void publishMaterialProcess_doesNotCreateTask() {
        ProcessMaterialRedisRequest request = TestFixtures.processMaterialRedisRequest();
        when(streamOperations.add(anyString(), anyMap())).thenReturn(RecordId.of("3-0"));

        redisProducer.publishMaterialProcess(request);

        verifyNoInteractions(taskService);
    }
}
