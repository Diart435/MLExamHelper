package com.examassistant.auth.service;

import com.examassistant.auth.entity.RefreshToken;
import com.examassistant.auth.repository.RefreshTokenRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.UUID;

@Service
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
    public RefreshToken validate(String token) {
        RefreshToken entity = repository.findByToken(token)
                .orElseThrow(() -> new IllegalArgumentException("Refresh token not found"));

        if (entity.isRevoked()) {
            repository.deleteByUserId(entity.getUserId());
            throw new IllegalStateException("Refresh token was already used");
        }

        if (entity.getExpiresAt().isBefore(OffsetDateTime.now())) {
            repository.delete(entity);
            throw new IllegalArgumentException("Refresh token expired");
        }

        return entity;
    }

    @Transactional
    public void revoke(RefreshToken token) {
        token.setRevoked(true);
        repository.save(token);
    }

    @Transactional
    public void revokeAllForUser(UUID userId) {
        repository.deleteByUserId(userId);
    }
}
