package com.examassistant.auth.service;

import lombok.RequiredArgsConstructor;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
public class RefreshTokenCleanupJob {

    private final RefreshTokenService refreshTokenService;

    @Scheduled(cron = "0 0 12 * * *")
    public void cleanup() {
        refreshTokenService.deleteExpired();
    }
}
