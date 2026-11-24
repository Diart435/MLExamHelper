package com.examassistant.jobs.listener;

import com.examassistant.jobs.DTO.IngestResultMessage;
import com.examassistant.jobs.service.MlResultAckSupport;
import com.examassistant.materials.MaterialService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

@Component
@RequiredArgsConstructor
@Slf4j
public class ProcessingMaterialListener implements StreamListener<String, MapRecord<String, String, String>> {
    private static final String STATUS_READY = "ready";
    private static final String STATUS_ERROR = "error";

    private final MaterialService materialService;
    private final ObjectMapper objectMapper;
    private final MlResultAckSupport ackSupport;

    @Override
    public void onMessage(MapRecord<String, String, String> message) {
        IngestResultMessage result;
        try {
            result = objectMapper.readValue(ackSupport.payload(message), IngestResultMessage.class);
        } catch (RuntimeException e) {
            ackSupport.ackPoison(message, e);
            return;
        }

        if (result.getMaterialId() == null) {
            ackSupport.ackPoison(message, new IllegalArgumentException("material_id is required"));
            return;
        }

        String status = STATUS_ERROR.equals(result.getStatus()) ? STATUS_ERROR : STATUS_READY;
        try {
            materialService.changeStatus(result.getMaterialId(), status);
        } catch (RuntimeException e) {
            log.error("Failed to apply ingest result channel={} msg_id={} material_id={}",
                    message.getStream(), message.getId(), result.getMaterialId(), e);
            return;
        }
        ackSupport.ack(message);
    }
}
