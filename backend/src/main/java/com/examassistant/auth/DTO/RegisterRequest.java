package com.examassistant.auth.DTO;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class RegisterRequest {
    @Email
    @NotBlank(message = "Email is required")
    private String email;
    @NotBlank(message = "Password is required")
    @Size(min = 8, max = 20, message = "Password can be bigger than 8 and less than 20")
    private String password;
    @NotBlank(message = "First name is required")
    @Size(max = 100)
    private String firstName;
    @NotBlank(message = "Last name is required")
    @Size(max = 100)
    private String lastName;
}
