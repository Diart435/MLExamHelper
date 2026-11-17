package com.examassistant.jobs.listener;

import com.examassistant.messaging.TaskService;
import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.ml.MlChannels;
import com.examassistant.ml.payload.MlCreateTestResult;
import com.examassistant.tests.TestService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

import java.util.UUID;

/**
 * Результат генерации теста (ml-results:create_test): сохраняем вопросы и
 * переводим тест в ready, либо помечаем тест и задачу ошибочными.
 */
@Component
@Slf4j
public class CreateTestListener extends MlResultListener<MlCreateTestResult> {

    private final TestService testService;
    private final TaskService taskService;

    public CreateTestListener(StringRedisTemplate redisTemplate,
                               MlChannels channels,
                               ObjectMapper objectMapper,
                               TestService testService,
                               TaskService taskService) {
        super(redisTemplate, channels, objectMapper, MlCreateTestResult.class);
        this.testService = testService;
        this.taskService = taskService;
    }

    @Override
    protected void handle(MlCreateTestResult result) {
        UUID taskId = UUID.fromString(result.taskId());

        if (result.isOk()) {
            testService.applyGeneratedTest(result);
            taskService.changeStatus(taskId, StatusTask.FINISHED);
            log.info("Тест {} сгенерирован ML", result.testId());
            return;
        }

        testService.markGenerationFailed(result);
        taskService.changeStatus(taskId, StatusTask.ERROR);
        log.error("ML не смог сгенерировать тест {}: {}", result.testId(), result.error());
    }
}
