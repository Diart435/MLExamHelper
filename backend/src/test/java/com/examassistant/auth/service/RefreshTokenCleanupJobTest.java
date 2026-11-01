package com.examassistant.auth.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class RefreshTokenCleanupJobTest {

    @Mock
    private RefreshTokenService refreshTokenService;

    @InjectMocks
    private RefreshTokenCleanupJob cleanupJob;

    @Test
    void cleanup_delegatesToRefreshTokenService() {
        cleanupJob.cleanup();

        verify(refreshTokenService).deleteExpired();
    }
}
