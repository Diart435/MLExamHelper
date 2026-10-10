package com.examassistant.auth.DTO;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class AuthResult {
    private String accessToken;
}
