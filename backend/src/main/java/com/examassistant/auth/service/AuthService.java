package com.examassistant.auth.service;

import com.examassistant.auth.DTO.*;
import com.examassistant.auth.entity.RefreshToken;
import com.examassistant.auth.entity.User;
import com.examassistant.auth.repository.RefreshTokenRepository;
import com.examassistant.auth.repository.UserRepository;
import com.examassistant.common.exception.InvalidCredentialsException;
import com.examassistant.common.exception.UserAlreadyExistException;
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
            throw new UserAlreadyExistException("Email already registered");
        }

        User user = new User();
        user.setEmail(req.getEmail());
        user.setPasswordHash(passwordEncoder.encode(req.getPassword()));
        user.setFirstName(req.getFirstName());
        user.setLastName(req.getLastName());
        user.setCreatedAt(OffsetDateTime.now());
        user.setUpdatedAt(OffsetDateTime.now());
        User saved = userRepository.save(user);

        return getAuth(saved);
    }
    @Transactional
    public AuthResponse login(LoginRequest req) {
        log.info("Login attempt: email={}", req.getEmail());

        User user = userRepository.findByEmail(req.getEmail())
                .orElseThrow(() -> new InvalidCredentialsException("This email doesn't exist"));

        if (!passwordEncoder.matches(req.getPassword(), user.getPasswordHash())) {
            throw new InvalidCredentialsException("Password is incorrect");
        }

        refreshTokenService.revokeAllByUserId(user.getUserId());

        return getAuth(user);
    }

    @Transactional
    public IssuedTokens refresh(String refreshToken) {
        log.info("Refresh attempt");

        RefreshToken stored = refreshTokenService.validate(refreshToken);

        stored.setRevoked(true);
        repository.save(stored);

        User user = userRepository.findById(stored.getUserId())
                .orElseThrow(() -> new UserNotFoundException(stored.getUserId().toString()));

        String access = jwtService.generate(user.getUserId(), user.getEmail());
        String refresh = refreshTokenService.create(user.getUserId());

        return new IssuedTokens(access, refresh);
    }
    @Transactional
    public void logout(String refreshToken) {
        refreshTokenService.revokeByToken(refreshToken);
    }

    private AuthResponse getAuth(User user){
        return new AuthResponse(
                user.getUserId().toString(),
                user.getEmail(),
                user.getFirstName(),
                user.getLastName(),
                jwtService.generate(user.getUserId(), user.getEmail())
        );
    }
}