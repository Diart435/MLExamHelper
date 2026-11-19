package com.examassistant.auth.service;

import com.examassistant.auth.DTO.VkTokenResponse;
import com.examassistant.auth.DTO.VkUserInfoResponse;
import com.examassistant.common.exception.InvalidTokenException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

@Service
@Slf4j
public class VkAuthService {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Value("${vk.client.id}")     private String clientId;
    @Value("${vk.service.token}") private String serviceToken;
    @Value("${vk.redirect.uri}")  private String redirectUri;

    private final RestClient restClient;

    public VkAuthService() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(5));
        factory.setReadTimeout(Duration.ofSeconds(10));

        this.restClient = RestClient.builder()
                .baseUrl("https://id.vk.ru")
                .requestFactory(factory)
                .build();
    }

    public VkUserInfoResponse authenticate(String code,
                                           String codeVerifier,
                                           String deviceId,
                                           String state) {

        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("grant_type",    "authorization_code");
        form.add("code_verifier", codeVerifier);
        form.add("redirect_uri",  redirectUri);
        form.add("code",          code);
        form.add("client_id",     clientId);
        form.add("device_id",     deviceId);
        form.add("state",         state);
        form.add("service_token", serviceToken);

        String rawTokens = post("/oauth2/auth", form);
        log.info("VK TOKEN RESPONSE: {}", rawTokens);

        VkTokenResponse tokens = parse(rawTokens, VkTokenResponse.class);
        if (tokens == null || tokens.getAccessToken() == null) {
            throw new InvalidTokenException("Не удалось получить токены от VK");
        }

        MultiValueMap<String, String> userForm = new LinkedMultiValueMap<>();
        userForm.add("client_id",    clientId);
        userForm.add("access_token", tokens.getAccessToken());

        String rawUser = post("/oauth2/user_info", userForm);
        log.info("VK USER RESPONSE: {}", rawUser);

        VkUserInfoResponse info = parse(rawUser, VkUserInfoResponse.class);
        if (info == null || info.getUser() == null) {
            throw new InvalidTokenException("VK не вернул данные пользователя");
        }
        return info;
    }

    private String post(String uri, MultiValueMap<String, String> form) {
        return restClient.post()
                .uri(uri)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(form)
                .exchange((request, response) -> {
                    String body = new String(response.getBody().readAllBytes(),
                            StandardCharsets.UTF_8);
                    if (response.getStatusCode().isError()) {
                        log.error("VK {} -> HTTP {} : {}", uri, response.getStatusCode(), body);
                        throw new InvalidTokenException("VK ID вернул ошибку: " + body);
                    }
                    return body;
                });
    }

    private <T> T parse(String raw, Class<T> type) {
        try {
            return MAPPER.readValue(raw, type);
        } catch (Exception e) {
            log.error("Не удалось распарсить ответ VK: {}", raw, e);
            throw new InvalidTokenException("Некорректный ответ от VK");
        }
    }
}