package com.examassistant.materials.DTO;

import lombok.Data;

import java.time.OffsetDateTime;
import java.util.UUID;

@Data
public class MaterialResponse {
    private UUID materialId;
    private UUID courseId;
    private String title;
    private String typeMaterial;
    private String statusMaterial;
    private String sourceUri;
    private long materialSize;
    private OffsetDateTime createdAt;
}
