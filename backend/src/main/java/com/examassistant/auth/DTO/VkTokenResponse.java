package com.examassistant.auth.DTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class VkTokenResponse {
    @JsonProperty("access_token")  private String accessToken;
    @JsonProperty("refresh_token") private String refreshToken;
    @JsonProperty("id_token")      private String idToken;
    @JsonProperty("token_type")    private String tokenType;
    @JsonProperty("expires_in")    private Long   expiresIn;
    @JsonProperty("user_id")       private Long   userId;
    @JsonProperty("scope")         private String scope;
    @JsonProperty("state")         private String state;
}
