package com.examassistant.jobs.listener;

import com.examassistant.jobs.DTO.CreateTestResultMessage;
import com.examassistant.jobs.service.CreateTestResultService;
import com.examassistant.jobs.service.MlResultAckSupport;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * Результат генерации теста с канала {@code create-test:ml-to-be}.
 *
 * XACK делается только после успешного применения результата: при исключении
 * сообщение остаётся в pending, его заберёт reclaim. Битый JSON — poison,
 * его подтверждаем и удаляем, чтобы он не крутился по кругу.
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class CreateTestListener implements StreamListener<String, MapRecord<String, String, String>> {
    private final CreateTestResultService resultService;
    private final ObjectMapper objectMapper;
    private final MlResultAckSupport ackSupport;

    @Override
    public void onMessage(MapRecord<String, String, String> message) {
        CreateTestResultMessage result;
        try {
            result = objectMapper.readValue(ackSupport.payload(message), CreateTestResultMessage.class);
        } catch (RuntimeException e) {
            ackSupport.ackPoison(message, e);
            return;
        }

        if (isError(result)) {
            log.error("ML create-test failed task_id={} test_id={}: {}",
                    result.getTaskId(), result.getTestId(), result.getError());
            try {
                resultService.applyError(result);
            } catch (RuntimeException e) {
                log.error("Failed to apply create-test error channel={} msg_id={} task_id={}",
                        message.getStream(), message.getId(), result.getTaskId(), e);
                return;
            }
            ackSupport.ack(message);
            return;
        }

        try {
            resultService.apply(result);
        } catch (RuntimeException e) {
            log.error("Failed to apply create-test result channel={} msg_id={} task_id={}",
                    message.getStream(), message.getId(), result.getTaskId(), e);
            return;
        }
        ackSupport.ack(message);
    }

    // Признак ошибки — status == "error" либо непустое поле error.
    private boolean isError(CreateTestResultMessage result) {
        return "error".equals(result.getStatus()) || (result.getError() != null && !result.getError().isBlank());
    }
}
