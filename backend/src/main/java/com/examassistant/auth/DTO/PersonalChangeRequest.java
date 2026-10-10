package com.examassistant.auth.DTO;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class PersonalChangeRequest {
    @NotBlank(message = "First name is required")
    @Size(max = 100)
    private String firstName;
    @NotBlank(message = "Last name is required")
    @Size(max = 100)
    private String lastName;
}
