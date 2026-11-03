package com.examassistant.auth.service;

import com.examassistant.auth.entity.RefreshToken;
import com.examassistant.auth.repository.RefreshTokenRepository;
import com.examassistant.common.exception.InvalidTokenException;
import com.examassistant.support.TestFixtures;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class RefreshTokenServiceTest {

    @Mock
    private RefreshTokenRepository repository;

    private RefreshTokenService service;

    @BeforeEach
    void setUp() {
        service = new RefreshTokenService(repository, 7);
    }

    @Test
    void create_savesActiveTokenWithConfiguredTtl() {
        when(repository.save(any(RefreshToken.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        OffsetDateTime before = OffsetDateTime.now();
        String token = service.create(TestFixtures.USER_ID);
        OffsetDateTime after = OffsetDateTime.now();

        assertThat(UUID.fromString(token)).isNotNull();

        ArgumentCaptor<RefreshToken> captor = ArgumentCaptor.forClass(RefreshToken.class);
        verify(repository).save(captor.capture());
        RefreshToken saved = captor.getValue();
        assertThat(saved.getToken()).isEqualTo(token);
        assertThat(saved.getUserId()).isEqualTo(TestFixtures.USER_ID);
        assertThat(saved.isRevoked()).isFalse();
        assertThat(saved.getExpiresAt()).isAfterOrEqualTo(before.plusDays(7));
        assertThat(saved.getExpiresAt()).isBeforeOrEqualTo(after.plusDays(7));
    }

    @Test
    void validate_validToken_returnsEntity() {
        RefreshToken token = activeToken("valid-token");
        when(repository.findByToken("valid-token")).thenReturn(Optional.of(token));

        RefreshToken result = service.validate("valid-token");

        assertThat(result).isSameAs(token);
    }

    @Test
    void validate_missingToken_throws() {
        when(repository.findByToken("missing")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.validate("missing"))
                .isInstanceOf(InvalidTokenException.class)
                .hasMessage("Token not found");
    }

    @Test
    void validate_revokedToken_throws() {
        RefreshToken token = activeToken("revoked-token");
        token.setRevoked(true);
        when(repository.findByToken("revoked-token")).thenReturn(Optional.of(token));

        assertThatThrownBy(() -> service.validate("revoked-token"))
                .isInstanceOf(InvalidTokenException.class)
                .hasMessage("Token revoked");
    }

    @Test
    void validate_expiredToken_throws() {
        RefreshToken token = activeToken("expired-token");
        token.setExpiresAt(OffsetDateTime.now().minusSeconds(1));
        when(repository.findByToken("expired-token")).thenReturn(Optional.of(token));

        assertThatThrownBy(() -> service.validate("expired-token"))
                .isInstanceOf(InvalidTokenException.class)
                .hasMessage("Token expired");
    }

    @Test
    void revokeByToken_marksTokenRevokedAndSaves() {
        RefreshToken token = activeToken("token");
        when(repository.findByToken("token")).thenReturn(Optional.of(token));

        service.revokeByToken("token");

        assertThat(token.isRevoked()).isTrue();
        verify(repository).save(token);
    }

    @Test
    void revokeByToken_missingToken_throws() {
        when(repository.findByToken("missing")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.revokeByToken("missing"))
                .isInstanceOf(InvalidTokenException.class)
                .hasMessage("Token not found");

        verify(repository, never()).save(any(RefreshToken.class));
    }

    @Test
    void revokeAllByUserId_delegatesToRepository() {
        when(repository.revokeAllByUserId(TestFixtures.USER_ID)).thenReturn(3);

        service.revokeAllByUserId(TestFixtures.USER_ID);

        verify(repository).revokeAllByUserId(TestFixtures.USER_ID);
    }

    @Test
    void getToken_existingActiveToken_returnsItWithoutCreatingNew() {
        when(repository.findFirstToken(eq(TestFixtures.USER_ID), any(OffsetDateTime.class)))
                .thenReturn(Optional.of("existing-token"));

        String token = service.getToken(TestFixtures.USER_ID);

        assertThat(token).isEqualTo("existing-token");
        verify(repository, never()).save(any(RefreshToken.class));
    }

    @Test
    void getToken_noActiveToken_createsNewToken() {
        when(repository.findFirstToken(eq(TestFixtures.USER_ID), any(OffsetDateTime.class)))
                .thenReturn(Optional.empty());
        when(repository.save(any(RefreshToken.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        String token = service.getToken(TestFixtures.USER_ID);

        assertThat(token).isNotBlank();
        assertThat(UUID.fromString(token)).isNotNull();
        verify(repository).save(any(RefreshToken.class));
    }

    @Test
    void deleteExpired_delegatesToRepository() {
        when(repository.deleteExpired(any(OffsetDateTime.class))).thenReturn(2);

        service.deleteExpired();

        verify(repository).deleteExpired(any(OffsetDateTime.class));
    }

    private RefreshToken activeToken(String value) {
        return RefreshToken.builder()
                .token(value)
                .userId(TestFixtures.USER_ID)
                .expiresAt(OffsetDateTime.now().plusDays(1))
                .revoked(false)
                .build();
    }
}
