package com.examassistant.materials.DTO;

import jakarta.validation.constraints.NotEmpty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.UUID;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class BulkDeleteMaterialsRequest {

    @NotEmpty(message = "Material IDs list must not be empty")
    private List<UUID> materialIds;
}