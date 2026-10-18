package com.examassistant.materials.DTO;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class ChangeFileNameRequest {
    @NotBlank
    private String title;
}
