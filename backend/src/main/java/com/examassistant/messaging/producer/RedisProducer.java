package com.examassistant.messaging.producer;

import com.examassistant.common.enums.TestAmountQuestions;
import com.examassistant.common.redis.MlChannels;
import com.examassistant.messaging.CreateTestRedisRequest;
import com.examassistant.messaging.GradeTestRedisRequest;
import com.examassistant.messaging.ProcessMaterialRedisRequest;
import com.examassistant.messaging.Producer;
import com.examassistant.messaging.TaskDTO;
import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.messaging.service.TasksService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class RedisProducer implements Producer {

    private final StringRedisTemplate redisTemplate;
    private final TasksService taskService;
    private final ObjectMapper objectMapper;

    @Override
    public RecordId publishCreateTest(CreateTestRedisRequest test) {
        TaskDTO taskDTO = new TaskDTO(test.getTestId(), test.getCourseId(), test.getTitle(), OffsetDateTime.now(),
                null, StatusTask.PROCESSING, TestAmountQuestions.MEDIUM, test.getDifficulty());
        taskService.create(test.getTaskId(), taskDTO);

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("task_id", test.getTaskId().toString());
        payload.put("test_id", test.getTestId().toString());
        payload.put("material_ids", test.getMaterialIds().stream().map(UUID -> UUID.toString()).toList());
        payload.put("title", test.getTitle());
        payload.put("difficulty", test.getDifficulty());

        return add(MlChannels.taskChannel(MlChannels.CREATE_TEST), payload);
    }

    @Override
    public RecordId publishMaterialProcess(ProcessMaterialRedisRequest material) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("material_id", material.getMaterialId().toString());
        payload.put("storage_key", material.getStorageKey());

        return add(MlChannels.taskChannel(MlChannels.INGEST), payload);
    }

    @Override
    public RecordId publishGradeTest(GradeTestRedisRequest request) {
        List<Map<String, Object>> answers = new ArrayList<>();
        for (GradeTestRedisRequest.Answer answer : request.getAnswers() == null ? List.<GradeTestRedisRequest.Answer>of() : request.getAnswers()) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("question_id", answer.getQuestionId().toString());
            item.put("student_answer", answer.getStudentAnswer().toMap());
            answers.add(item);
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("task_id", request.getTaskId().toString());
        payload.put("attempt_id", request.getAttemptId().toString());
        payload.put("test_id", request.getTestId().toString());
        payload.put("answers", answers);

        return add(MlChannels.taskChannel(MlChannels.GRADE_TEST), payload);
    }

    private RecordId add(String channel, Map<String, Object> payload) {
        String json = objectMapper.writeValueAsString(payload);
        return redisTemplate.opsForStream().add(channel, Map.of("payload", json));
    }
}
