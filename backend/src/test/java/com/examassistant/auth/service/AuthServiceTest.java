package com.examassistant.auth.service;

import com.examassistant.auth.DTO.AuthResponse;
import com.examassistant.auth.DTO.IssuedTokens;
import com.examassistant.auth.DTO.LoginRequest;
import com.examassistant.auth.DTO.RegisterRequest;
import com.examassistant.auth.entity.RefreshToken;
import com.examassistant.auth.entity.User;
import com.examassistant.auth.repository.RefreshTokenRepository;
import com.examassistant.auth.repository.UserRepository;
import com.examassistant.common.exception.InvalidCredentialsException;
import com.examassistant.common.exception.UserAlreadyExistException;
import com.examassistant.common.exception.UserNotFoundException;
import com.examassistant.security.service.JwtService;
import com.examassistant.support.TestFixtures;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.time.OffsetDateTime;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AuthServiceTest {

    @Mock
    private UserRepository userRepository;
    @Mock
    private RefreshTokenService refreshTokenService;
    @Mock
    private JwtService jwtService;
    @Mock
    private PasswordEncoder passwordEncoder;
    @Mock
    private RefreshTokenRepository refreshTokenRepository;

    @InjectMocks
    private AuthService authService;

    @Test
    void register_newEmail_savesUserAndReturnsAuthResponse() {
        RegisterRequest request = new RegisterRequest();
        request.setEmail(TestFixtures.EMAIL);
        request.setPassword("password123");
        request.setFirstName("Ivan");
        request.setLastName("Ivanov");

        when(userRepository.existsByEmail(TestFixtures.EMAIL)).thenReturn(false);
        when(passwordEncoder.encode("password123")).thenReturn("encoded-password");
        when(userRepository.save(any(User.class))).thenAnswer(invocation -> {
            User user = invocation.getArgument(0);
            user.setUserId(TestFixtures.USER_ID);
            return user;
        });
        when(jwtService.generate(TestFixtures.USER_ID, TestFixtures.EMAIL)).thenReturn("access-token");

        AuthResponse response = authService.register(request);

        assertThat(response.getUserId()).isEqualTo(TestFixtures.USER_ID.toString());
        assertThat(response.getEmail()).isEqualTo(TestFixtures.EMAIL);
        assertThat(response.getFirstName()).isEqualTo("Ivan");
        assertThat(response.getLastName()).isEqualTo("Ivanov");
        assertThat(response.getAccessToken()).isEqualTo("access-token");

        ArgumentCaptor<User> userCaptor = ArgumentCaptor.forClass(User.class);
        verify(userRepository).save(userCaptor.capture());
        User saved = userCaptor.getValue();
        assertThat(saved.getEmail()).isEqualTo(TestFixtures.EMAIL);
        assertThat(saved.getPasswordHash()).isEqualTo("encoded-password");
        assertThat(saved.getFirstName()).isEqualTo("Ivan");
        assertThat(saved.getLastName()).isEqualTo("Ivanov");
        assertThat(saved.getCreatedAt()).isNotNull();
        assertThat(saved.getUpdatedAt()).isNotNull();
    }

    @Test
    void register_existingEmail_throwsAndDoesNotSave() {
        RegisterRequest request = new RegisterRequest();
        request.setEmail(TestFixtures.EMAIL);
        request.setPassword("password123");
        request.setFirstName("Ivan");
        request.setLastName("Ivanov");

        when(userRepository.existsByEmail(TestFixtures.EMAIL)).thenReturn(true);

        assertThatThrownBy(() -> authService.register(request))
                .isInstanceOf(UserAlreadyExistException.class)
                .hasMessage("Email already registered");

        verify(userRepository, never()).save(any(User.class));
        verifyNoInteractions(passwordEncoder, jwtService);
    }

    @Test
    void login_validCredentials_revokesTokensAndReturnsAuthResponse() {
        LoginRequest request = new LoginRequest();
        request.setEmail(TestFixtures.EMAIL);
        request.setPassword("password123");

        User user = TestFixtures.user();
        when(userRepository.findByEmail(TestFixtures.EMAIL)).thenReturn(Optional.of(user));
        when(passwordEncoder.matches("password123", TestFixtures.PASSWORD_HASH)).thenReturn(true);
        when(jwtService.generate(TestFixtures.USER_ID, TestFixtures.EMAIL)).thenReturn("access-token");

        AuthResponse response = authService.login(request);

        assertThat(response.getUserId()).isEqualTo(TestFixtures.USER_ID.toString());
        assertThat(response.getEmail()).isEqualTo(TestFixtures.EMAIL);
        assertThat(response.getAccessToken()).isEqualTo("access-token");
        verify(refreshTokenService).revokeAllByUserId(TestFixtures.USER_ID);
    }

    @Test
    void login_unknownEmail_throws() {
        LoginRequest request = new LoginRequest();
        request.setEmail(TestFixtures.EMAIL);
        request.setPassword("password123");

        when(userRepository.findByEmail(TestFixtures.EMAIL)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> authService.login(request))
                .isInstanceOf(InvalidCredentialsException.class)
                .hasMessage("This email doesn't exist");

        verifyNoInteractions(passwordEncoder);
        verify(refreshTokenService, never()).revokeAllByUserId(any());
    }

    @Test
    void login_wrongPassword_throwsAndDoesNotRevokeTokens() {
        LoginRequest request = new LoginRequest();
        request.setEmail(TestFixtures.EMAIL);
        request.setPassword("wrong-password");

        User user = TestFixtures.user();
        when(userRepository.findByEmail(TestFixtures.EMAIL)).thenReturn(Optional.of(user));
        when(passwordEncoder.matches("wrong-password", TestFixtures.PASSWORD_HASH)).thenReturn(false);

        assertThatThrownBy(() -> authService.login(request))
                .isInstanceOf(InvalidCredentialsException.class)
                .hasMessage("Password is incorrect");

        verify(refreshTokenService, never()).revokeAllByUserId(any());
        verify(jwtService, never()).generate(any(), any());
    }

    @Test
    void refresh_validToken_revokesOldTokenAndIssuesNewTokens() {
        RefreshToken stored = RefreshToken.builder()
                .token("old-refresh-token")
                .userId(TestFixtures.USER_ID)
                .expiresAt(OffsetDateTime.now().plusDays(1))
                .revoked(false)
                .build();
        User user = TestFixtures.user();

        when(refreshTokenService.validate("old-refresh-token")).thenReturn(stored);
        when(userRepository.findById(TestFixtures.USER_ID)).thenReturn(Optional.of(user));
        when(jwtService.generate(TestFixtures.USER_ID, TestFixtures.EMAIL)).thenReturn("new-access-token");
        when(refreshTokenService.create(TestFixtures.USER_ID)).thenReturn("new-refresh-token");

        IssuedTokens tokens = authService.refresh("old-refresh-token");

        assertThat(tokens.getAccessToken()).isEqualTo("new-access-token");
        assertThat(tokens.getRefreshToken()).isEqualTo("new-refresh-token");
        assertThat(stored.isRevoked()).isTrue();
        verify(refreshTokenRepository).save(stored);
        verify(refreshTokenService).create(TestFixtures.USER_ID);
    }

    @Test
    void refresh_userNotFound_throwsAfterOldTokenIsRevoked() {
        RefreshToken stored = RefreshToken.builder()
                .token("old-refresh-token")
                .userId(TestFixtures.USER_ID)
                .expiresAt(OffsetDateTime.now().plusDays(1))
                .revoked(false)
                .build();

        when(refreshTokenService.validate("old-refresh-token")).thenReturn(stored);
        when(userRepository.findById(TestFixtures.USER_ID)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> authService.refresh("old-refresh-token"))
                .isInstanceOf(UserNotFoundException.class)
                .hasMessage(TestFixtures.USER_ID.toString());

        assertThat(stored.isRevoked()).isTrue();
        verify(refreshTokenRepository).save(stored);
        verify(refreshTokenService, never()).create(any());
    }

    @Test
    void logout_revokesRefreshToken() {
        authService.logout("refresh-token");

        verify(refreshTokenService).revokeByToken("refresh-token");
    }
}
