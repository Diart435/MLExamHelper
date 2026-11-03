package com.examassistant.jobs.listener;

import com.examassistant.materials.MaterialService;
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
public class ProcessingMaterialListener implements StreamListener<String, MapRecord<String, String, String>> {
    private final StringRedisTemplate redisTemplate;
    private static final String STREAM_KEY = "materials:process-response";
    private static final String GROUP_NAME = "material-status-handlers";
    private final MaterialService materialService;

    @Override
    public void onMessage(MapRecord<String, String, String> message) {
        log.info("Обработка статуса материала: {}", message.getValue());
        Map<String, String> fields = message.getValue();

        String taskIdStr = fields.get("task_id");
        UUID taskId = UUID.fromString(taskIdStr);
        String materialIdStr = fields.get("material_id");
        UUID materialId = UUID.fromString(materialIdStr);

        String statusStr = fields.get("status");
        materialService.changeStatus(materialId, statusStr);
        redisTemplate.opsForStream().acknowledge(STREAM_KEY, GROUP_NAME, message.getId());
    }
}
