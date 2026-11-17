package com.examassistant.messaging.producer;

import com.examassistant.ml.MlChannels;
import com.examassistant.messaging.CreateTestRedisRequest;
import com.examassistant.messaging.GradeAttemptRedisRequest;
import com.examassistant.messaging.ProcessMaterialRedisRequest;
import com.examassistant.messaging.Producer;
import com.examassistant.messaging.TaskDTO;
import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.messaging.service.TasksService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Публикация задач для ML.
 *
 * Каждое сообщение — XADD &lt;канал&gt; * payload '&lt;JSON&gt;'. Тип задачи задаёт
 * имя канала, поля type в payload нет: так сообщение нельзя прочитать не тем
 * обработчиком.
 */
@Service
@RequiredArgsConstructor
public class RedisProducer implements Producer {

    private final StringRedisTemplate redisTemplate;
    private final MlChannels channels;
    private final TasksService taskService;
    private final ObjectMapper objectMapper;

    @Override
    public RecordId publishCreateTest(CreateTestRedisRequest test) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("task_id", test.getTaskId().toString());
        payload.put("test_id", test.getTestId().toString());
        payload.put("material_ids", test.getMaterialIds().stream().map(UUID::toString).toList());
        payload.put("title", test.getTitle());
        payload.put("amountQuestions", test.getAmountQuestions().toMlAmount());
        payload.put("difficulty", test.getDifficulty());
        payload.put("course_id", test.getCourseId().toString());

        TaskDTO taskDTO = new TaskDTO(test.getTestId(), test.getCourseId(), test.getTitle(),
                OffsetDateTime.now(), null, StatusTask.PROCESSING, test.getAmountQuestions(), test.getDifficulty());
        taskService.create(test.getTaskId(), taskDTO);

        return publish(channels.taskChannel(MlChannels.CREATE_TEST), payload);
    }

    @Override
    public RecordId publishMaterialProcess(ProcessMaterialRedisRequest material) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("task_id", material.getTaskId().toString());
        payload.put("material_id", material.getMaterialId().toString());
        payload.put("storage_key", material.getStorageKey());

        return publish(channels.taskChannel(MlChannels.INGEST), payload);
    }

    @Override
    public RecordId publishGradeAttempt(GradeAttemptRedisRequest attempt) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("task_id", attempt.getTaskId().toString());
        payload.put("attempt_id", attempt.getAttemptId().toString());
        payload.put("test_id", attempt.getTestId().toString());
        payload.put("user_id", attempt.getUserId().toString());
        payload.put("answers", attempt.getAnswers());

        return publish(channels.taskChannel(MlChannels.GRADE_ATTEMPT), payload);
    }

    private RecordId publish(String channel, Map<String, Object> payload) {
        try {
            String json = objectMapper.writeValueAsString(payload);
            return redisTemplate.opsForStream().add(channel, Map.of("payload", json));
        } catch (JacksonException e) {
            throw new IllegalStateException("Не удалось сериализовать задачу для ML: " + e.getMessage(), e);
        }
    }
}
