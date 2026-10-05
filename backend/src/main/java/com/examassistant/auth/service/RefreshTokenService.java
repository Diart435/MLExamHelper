package com.examassistant.auth.service;

import com.examassistant.auth.entity.RefreshToken;
import com.examassistant.auth.repository.RefreshTokenRepository;
import com.examassistant.common.exception.InvalidTokenException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.UUID;

@Service
@Slf4j
public class RefreshTokenService {

    private final RefreshTokenRepository repository;
    private final long refreshTtlDays;

    public RefreshTokenService(
            RefreshTokenRepository repository,
            @Value("${app.jwt.refresh-ttl-days:7}") long refreshTtlDays
    ) {
        this.repository = repository;
        this.refreshTtlDays = refreshTtlDays;
    }

    @Transactional
    public String create(UUID userId) {
        String token = UUID.randomUUID().toString();

        RefreshToken entity = new RefreshToken();
        entity.setToken(token);
        entity.setUserId(userId);
        entity.setExpiresAt(OffsetDateTime.now().plusDays(refreshTtlDays));
        entity.setRevoked(false);

        repository.save(entity);
        return token;
    }

    @Transactional
    public void revokeAllByUserId(UUID userId) {
        log.info("Cleaned {} tokens", repository.revokeAllByUserId(userId));
    }

    @Transactional
    public void revokeByToken(String token) {
        RefreshToken stored = repository.findByToken(token)
                .orElseThrow(() -> new InvalidTokenException("Token not found"));
        stored.setRevoked(true);
        repository.save(stored);
    }

    @Transactional(readOnly = true)
    public RefreshToken validate(String token) {
        RefreshToken stored = repository.findByToken(token)
                .orElseThrow(() -> new InvalidTokenException("Token not found"));

        if (stored.isRevoked()) {
            throw new InvalidTokenException("Token revoked");
        }

        if (stored.getExpiresAt().isBefore(OffsetDateTime.now())) {
            throw new InvalidTokenException("Token expired");
        }

        return stored;
    }

    @Transactional
    public void deleteExpired() {
        log.info("Deleted {} expired tokens",repository.deleteExpired(OffsetDateTime.now()));
    }
}
