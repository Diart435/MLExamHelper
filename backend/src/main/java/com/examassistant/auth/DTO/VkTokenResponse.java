package com.examassistant.auth.DTO;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class VkTokenResponse {
    private String accessToken;
    private String refreshToken;
    private String idToken;
}
