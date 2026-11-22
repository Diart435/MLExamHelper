package com.examassistant.jobs.listener;

import com.examassistant.jobs.DTO.GradeTestResultMessage;
import com.examassistant.jobs.service.GradeTestResultService;
import com.examassistant.jobs.service.MlResultAckSupport;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

@Component
@RequiredArgsConstructor
@Slf4j
public class GradeTestListener implements StreamListener<String, MapRecord<String, String, String>> {
    private final GradeTestResultService resultService;
    private final ObjectMapper objectMapper;
    private final MlResultAckSupport ackSupport;

    @Override
    public void onMessage(MapRecord<String, String, String> message) {
        GradeTestResultMessage result;
        try {
            result = objectMapper.readValue(ackSupport.payload(message), GradeTestResultMessage.class);
        } catch (RuntimeException e) {
            ackSupport.ackPoison(message, e);
            return;
        }

        if (result.getError() != null) {
            log.error("ML grade-test failed task_id={} attempt_id={}: {}",
                    result.getTaskId(), result.getAttemptId(), result.getError());
            ackSupport.ack(message);
            return;
        }

        try {
            resultService.apply(result);
        } catch (RuntimeException e) {
            log.error("Failed to apply grade-test result channel={} msg_id={} task_id={}",
                    message.getStream(), message.getId(), result.getTaskId(), e);
            return;
        }
        ackSupport.ack(message);
    }
}
