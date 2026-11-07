package com.examassistant.auth.service;

import com.examassistant.auth.DTO.VkTokenResponse;
import com.examassistant.auth.DTO.VkUserInfoResponse;
import com.examassistant.common.exception.InvalidCredentialsException;
import com.examassistant.common.exception.InvalidTokenException;
import lombok.AllArgsConstructor;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
@Slf4j
public class VkAuthService {

    @Value("${vk.client.id}")
    private String clientId;

    @Value("${vk.client.secret}")
    private String clientSecret;

    private final RestClient restClient;

    public VkAuthService(){
        this.restClient = RestClient.builder().baseUrl("https://id.vk.ru").build();
    }

    public VkUserInfoResponse authenticate(String code, String codeVerifier, String deviceId){
        VkTokenResponse tokens = restClient.post()
                .uri("/oauth2/auth")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body("grant_type=authorization_code" +
                        "&code=" + code +
                        "&code_verifier" + codeVerifier +
                        "&client_id" + clientId +
                        "&client_secret" + clientSecret +
                        "&deviceId=" + deviceId)
                .retrieve()
                .body(VkTokenResponse.class);

        if(tokens == null || tokens.getAccessToken() == null){
            log.info("Invalid enter; code:{}, codeVerifier:{}, deviceId:{}", code, codeVerifier, deviceId);
            throw new InvalidTokenException("Не удалось получить токены от VK");
        }

        return restClient.get()
                .uri(uriBuilder -> uriBuilder.path("/oauth2/user_info")
                        .queryParam("access_token", tokens.getAccessToken())
                        .queryParam("client_id", clientId)
                        .build())
                .retrieve()
                .body(VkUserInfoResponse.class);
    }
}
