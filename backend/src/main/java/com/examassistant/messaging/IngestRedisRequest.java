package com.examassistant.messaging;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class IngestRedisRequest {
    @JsonProperty("material_id")
    private UUID materialId;

    @JsonProperty("storage_key")
    private String storageKey;
}
