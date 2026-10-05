package com.examassistant.auth.service;

import com.examassistant.auth.DTO.AuthResponse;
import com.examassistant.auth.DTO.LoginRequest;
import com.examassistant.auth.DTO.RefreshRequest;
import com.examassistant.auth.DTO.RegisterRequest;
import com.examassistant.auth.entity.RefreshToken;
import com.examassistant.auth.entity.User;
import com.examassistant.auth.repository.RefreshTokenRepository;
import com.examassistant.auth.repository.UserRepository;
import com.examassistant.common.exception.UserNotFoundException;
import com.examassistant.security.service.JwtService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;

@Service
@Slf4j
@RequiredArgsConstructor
public class AuthService {
    private final UserRepository userRepository;
    private final RefreshTokenService refreshTokenService;
    private final JwtService jwtService;
    private final PasswordEncoder passwordEncoder;
    private final RefreshTokenRepository repository;

    @Transactional
    public AuthResponse register(RegisterRequest req) {
        if (userRepository.existsByEmail(req.getEmail())) {
            throw new IllegalArgumentException("Email already registered");
        }

        User user = new User();
        user.setEmail(req.getEmail());
        user.setPasswordHash(passwordEncoder.encode(req.getPassword()));
        user.setFirstName(req.getFirstName());
        user.setLastName(req.getLastName());
        user.setCreatedAt(OffsetDateTime.now());
        user.setUpdatedAt(OffsetDateTime.now());
        userRepository.save(user);

        return issueTokens(user);
    }
    @Transactional
    public AuthResponse login(LoginRequest req) {
        log.info("Login attempt: email={}", req.getEmail());

        User user = userRepository.findByEmail(req.getEmail())
                .orElseThrow(() -> new IllegalArgumentException("Invalid credentials"));

        if (!passwordEncoder.matches(req.getPassword(), user.getPasswordHash())) {
            throw new IllegalArgumentException("Invalid credentials");
        }

        refreshTokenService.revokeAllByUserId(user.getUserId());

        return issueTokens(user);
    }

    @Transactional
    public AuthResponse refresh(String oldRefreshToken) {
        log.info("Refresh attempt");

        RefreshToken stored = refreshTokenService.validate(oldRefreshToken);

        stored.setRevoked(true);
        repository.save(stored);

        User user = userRepository.findById(stored.getUserId())
                .orElseThrow(() -> new UserNotFoundException(stored.getUserId().toString()));

        return issueTokens(user);
    }
    @Transactional
    public void logout(String refreshToken) {
        refreshTokenService.revokeByToken(refreshToken);
    }

    private AuthResponse issueTokens(User user) {
        String access = jwtService.generate(user.getUserId(), user.getEmail());
        String refresh = refreshTokenService.create(user.getUserId());
        return new AuthResponse(
                user.getUserId(),
                user.getEmail(),
                user.getFirstName(),
                user.getLastName(),
                access,
                refresh
        );
    }
}
