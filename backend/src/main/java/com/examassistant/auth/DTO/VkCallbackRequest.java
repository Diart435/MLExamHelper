package com.examassistant.auth.DTO;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class VkCallbackRequest {
    private String code;
    private String codeVerifier;
    private String state;
    private String deviceId;
}
