package com.examassistant.auth.service;

import com.examassistant.auth.DTO.AuthResponse;
import com.examassistant.auth.DTO.LoginRequest;
import com.examassistant.auth.DTO.RefreshRequest;
import com.examassistant.auth.DTO.RegisterRequest;
import com.examassistant.auth.entity.RefreshToken;
import com.examassistant.auth.entity.User;
import com.examassistant.auth.repository.UserRepository;
import com.examassistant.security.service.JwtService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class AuthService {
    private final UserRepository userRepository;
    private final RefreshTokenService refreshTokenService;
    private final JwtService jwtService;
    private final PasswordEncoder passwordEncoder;

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
        userRepository.save(user);

        return issueTokens(user);
    }
    @Transactional
    public AuthResponse login(LoginRequest req) {
        User user = userRepository.findByEmail(req.getEmail())
                .orElseThrow(() -> new IllegalArgumentException("Invalid credentials"));

        if (!passwordEncoder.matches(req.getPassword(), user.getPasswordHash())) {
            throw new IllegalArgumentException("Invalid credentials");
        }

        return issueTokens(user);
    }

    @Transactional
    public AuthResponse refresh(RefreshRequest req) {
        RefreshToken old = refreshTokenService.validate(req.getRefreshToken());
        refreshTokenService.revoke(old);

        User user = userRepository.findById(old.getUserId())
                .orElseThrow(() -> new IllegalStateException("User not found"));

        return issueTokens(user);
    }
    @Transactional
    public void logout(RefreshRequest req) {
        RefreshToken token = refreshTokenService.validate(req.getRefreshToken());
        refreshTokenService.revoke(token);
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
