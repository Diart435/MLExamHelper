package com.examassistant.jobs.listener;

import com.examassistant.materials.MaterialService;
import com.examassistant.materials.enums.StatusMaterial;
import com.examassistant.ml.MlChannels;
import com.examassistant.ml.payload.MlIngestResult;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

import java.util.UUID;

/**
 * Результат индексации материала (ml-results:ingest): переводим материал в
 * ready или error.
 */
@Component
@Slf4j
public class ProcessingMaterialListener extends MlResultListener<MlIngestResult> {

    private final MaterialService materialService;

    public ProcessingMaterialListener(StringRedisTemplate redisTemplate,
                                      MlChannels channels,
                                      ObjectMapper objectMapper,
                                      MaterialService materialService) {
        super(redisTemplate, channels, objectMapper, MlIngestResult.class);
        this.materialService = materialService;
    }

    @Override
    protected void handle(MlIngestResult result) {
        UUID materialId = UUID.fromString(result.materialId());
        StatusMaterial status = result.isReady() ? StatusMaterial.READY : StatusMaterial.ERROR;
        log.info("Материал {} проиндексирован ML: {}", materialId, status.getValue());
        materialService.changeStatus(materialId, status.getValue());
    }
}
