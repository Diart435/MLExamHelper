package com.examassistant.auth.DTO;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class IssuedTokens {
    private String accessToken;
    private String refreshToken;
}
