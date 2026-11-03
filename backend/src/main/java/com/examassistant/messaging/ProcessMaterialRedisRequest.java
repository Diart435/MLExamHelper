package com.examassistant.messaging;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class ProcessMaterialRedisRequest {
    private UUID taskId;
    private UUID materialId;
    private String storageKey;
}
