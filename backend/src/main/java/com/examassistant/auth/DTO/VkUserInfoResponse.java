package com.examassistant.auth.DTO;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class VkUserInfoResponse {
    private String userId;
    private String firstName;
    private String lastName;
    private String email;
}
