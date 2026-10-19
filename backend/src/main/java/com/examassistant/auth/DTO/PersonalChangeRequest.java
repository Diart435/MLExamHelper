package com.examassistant.auth.DTO;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class PersonalChangeRequest {
    @Email
    private String email;
    @Size(max = 100)
    private String firstName;
    @Size(max = 100)
    private String lastName;
}
