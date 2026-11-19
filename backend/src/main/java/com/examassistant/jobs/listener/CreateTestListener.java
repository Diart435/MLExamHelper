package com.examassistant.jobs.listener;

import com.examassistant.jobs.DTO.TestResultResponse;
import com.examassistant.messaging.TaskService;
import com.examassistant.tests.QuestionService;
import com.examassistant.common.enums.TestAmountQuestions;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

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
    private final QuestionService questionService;
    private final ObjectMapper objectMapper;

    //TODO: сделать создание теста
    @Override
    public void onMessage(MapRecord<String, String, String> message) {
        log.info("Обработка теста: {}", message.getValue());
        Map<String, String> fields = message.getValue();

        String taskIdStr = fields.get("task_id");
        UUID taskId = UUID.fromString(taskIdStr);
        taskService.changeStatus(taskId);

        String amountQuestionsStr = fields.get("amount_questions");
        TestAmountQuestions amountQuestionsQuestions = TestAmountQuestions.fromValue(amountQuestionsStr);

        String statusStr = fields.get("status");

        String testIdStr = fields.get("test_id");
        UUID testId = UUID.fromString(testIdStr);

        String testStr = fields.get("test");
        TestResultResponse response = objectMapper.readValue(testStr, TestResultResponse.class);

        // TODO: определиться с посылкой Redis response.getTestData().getQuestions().stream().map(x -> new QuestionDTO(testId, x.getQuestionType(), x.getText(), x.getOptions(), x.));
        redisTemplate.opsForStream().acknowledge(STREAM_KEY, GROUP_NAME, message.getId());
    }
}
