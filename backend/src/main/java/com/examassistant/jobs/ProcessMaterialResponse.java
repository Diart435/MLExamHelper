package com.examassistant.jobs;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class ProcessMaterialResponse {
    private UUID taskId;
    private UUID materialId;
    private String status;
}
