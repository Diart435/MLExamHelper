package com.examassistant.jobs.listener;

import com.examassistant.messaging.TaskService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.UUID;

@Component
@RequiredArgsConstructor
@Slf4j
public class CreateTestListener implements StreamListener<String, MapRecord<String, String, String>> {
    private final StringRedisTemplate redisTemplate;
    private static final String STREAM_KEY = "tests:create-test-response";
    private static final String GROUP_NAME = "test-handlers";
    private final TaskService taskService;

    //TODO: сделать создание теста
    @Override
    public void onMessage(MapRecord<String, String, String> message) {
        log.info("Обработка теста: {}", message.getValue());
        Map<String, String> fields = message.getValue();

        String taskIdStr = fields.get("task_id");
        UUID taskId = UUID.fromString(taskIdStr);
        taskService.changeStatus(taskId);

        String numQuestionsStr = fields.get("num_questions");
        int numQuestions = Integer.parseInt(numQuestionsStr);
        redisTemplate.opsForStream().acknowledge(STREAM_KEY, GROUP_NAME, message.getId());
    }
}
