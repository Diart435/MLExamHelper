package com.examassistant.security.service;

import com.examassistant.support.TestFixtures;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.ExpiredJwtException;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.security.WeakKeyException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class JwtServiceTest {

    private static final String OTHER_SECRET =
            "another-secret-key-at-least-32-bytes-long-0000000000";

    private JwtService jwtService;

    @BeforeEach
    void setUp() {
        jwtService = new JwtService(TestFixtures.JWT_SECRET, 60);
    }

    @Test
    void generate_and_parse_roundTrip() {
        Instant before = Instant.now();
        String token = jwtService.generate(TestFixtures.USER_ID, TestFixtures.EMAIL);
        Instant after = Instant.now();

        Claims claims = jwtService.parse(token);

        assertThat(claims.getSubject()).isEqualTo(TestFixtures.USER_ID.toString());
        assertThat(claims.get("email", String.class)).isEqualTo(TestFixtures.EMAIL);
        assertThat(claims.getIssuedAt()).isNotNull();
        assertThat(claims.getExpiration()).isNotNull();
        assertThat(claims.getExpiration().toInstant())
                .isBetween(before.plusSeconds(59 * 60), after.plusSeconds(61 * 60));
    }

    @Test
    void parse_tokenSignedWithAnotherSecret_throws() {
        JwtService other = new JwtService(OTHER_SECRET, 60);
        String token = other.generate(TestFixtures.USER_ID, TestFixtures.EMAIL);

        assertThatThrownBy(() -> jwtService.parse(token))
                .isInstanceOf(JwtException.class);
    }

    @Test
    void parse_expiredToken_throwsExpiredJwtException() {
        JwtService expiredService = new JwtService(TestFixtures.JWT_SECRET, -1);
        String token = expiredService.generate(TestFixtures.USER_ID, TestFixtures.EMAIL);

        assertThatThrownBy(() -> jwtService.parse(token))
                .isInstanceOf(ExpiredJwtException.class);
    }

    @Test
    void parse_malformedToken_throwsJwtException() {
        assertThatThrownBy(() -> jwtService.parse("not-a-jwt-token"))
                .isInstanceOf(JwtException.class);
    }

    @Test
    void constructor_shortSecret_throwsWeakKeyException() {
        assertThatThrownBy(() -> new JwtService("short-secret", 60))
                .isInstanceOf(WeakKeyException.class);
    }
}
