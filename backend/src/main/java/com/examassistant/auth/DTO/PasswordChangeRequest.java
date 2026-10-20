package com.examassistant.auth.DTO;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class PasswordChangeRequest {
    @NotBlank(message = "Password is required")
    @Size(min = 8, max = 20, message = "Password can be bigger than 8 and less than 20")
    private String lastPassword;

    @NotBlank(message = "Password is required")
    @Size(min = 8, max = 20, message = "Password can be bigger than 8 and less than 20")
    private String newPassword;
}
