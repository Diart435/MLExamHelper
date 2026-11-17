package com.examassistant.jobs.listener;

import com.examassistant.ml.MlChannels;
import com.examassistant.ml.payload.MlGradeAttemptResult;
import com.examassistant.tests.AttemptService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * Результат проверки попытки (ml-results:grade_attempt): записываем баллы,
 * фидбэк и итог в попытку.
 */
@Component
@Slf4j
public class GradeAttemptListener extends MlResultListener<MlGradeAttemptResult> {

    private final AttemptService attemptService;

    public GradeAttemptListener(StringRedisTemplate redisTemplate,
                                 MlChannels channels,
                                 ObjectMapper objectMapper,
                                 AttemptService attemptService) {
        super(redisTemplate, channels, objectMapper, MlGradeAttemptResult.class);
        this.attemptService = attemptService;
    }

    @Override
    protected void handle(MlGradeAttemptResult result) {
        attemptService.applyGrade(result);
        log.info("Попытка {} проверена ML: {}%", result.attemptId(), result.scorePct());
    }
}
