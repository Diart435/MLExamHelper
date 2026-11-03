package com.examassistant.messaging.producer;

import com.examassistant.messaging.CreateTestRedisRequest;
import com.examassistant.messaging.ProcessMaterialRedisRequest;
import com.examassistant.messaging.Producer;
import com.examassistant.messaging.TaskDTO;
import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.messaging.service.TasksService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class RedisProducer implements Producer {

    private final StringRedisTemplate redisTemplate;
    private static final String STREAM_KEY_TESTS = "tests:create-test-request";
    private static final String STREAM_KEY_MATERIALS = "materials:process-response";
    private final TasksService taskService;

    public RecordId publishCreateTest(CreateTestRedisRequest test) {
        Map<String, String> fields = new HashMap<>();
        fields.put("task_id", test.getTaskId().toString());
        fields.put("test_id", test.getTestId().toString());
        fields.put("material_ids", test.getMaterialIds().stream()
                .map(UUID::toString)
                .collect(Collectors.joining(",")));
        fields.put("title", test.getTitle());
        fields.put("num_questions", String.valueOf(test.getNumQuestions()));
        fields.put("difficulty", test.getDifficulty());
        fields.put("course_id", test.getCourseId().toString());
        TaskDTO taskDTO = new TaskDTO(test.getTestId(), test.getCourseId(), test.getTitle(), OffsetDateTime.now(), null, StatusTask.PROCESSING, test.getNumQuestions(), test.getDifficulty());
        taskService.create(test.getTaskId(), taskDTO);

        return redisTemplate.opsForStream().add(STREAM_KEY_TESTS, fields);
    }

    public RecordId publishMaterialProcess(ProcessMaterialRedisRequest material) {
        Map<String, String> fields = new HashMap<>();
        fields.put("task_id", material.getTaskId().toString());
        fields.put("material_id", material.getMaterialId().toString());
        fields.put("storage_key", material.getStorageKey());

        return redisTemplate.opsForStream().add(STREAM_KEY_MATERIALS, fields);
    }
}