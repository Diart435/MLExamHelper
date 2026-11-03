package com.examassistant.materials;

import lombok.Data;

import java.util.UUID;

@Data
public class ChangeStatusDTO {
    private UUID materialId;
    private String status;
}
