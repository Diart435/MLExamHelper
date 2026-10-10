package com.examassistant.auth.DTO;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.util.UUID;

@Data
@AllArgsConstructor
public class AuthResponse {
    private String userId;
    private String email;
    private String firstName;
    private String lastName;
    private String accessToken;
}
