package com.examassistant.security.service;

import com.examassistant.support.TestFixtures;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CurrentUserTest {

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void id_withUuidPrincipal_returnsUserId() {
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        TestFixtures.USER_ID,
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_USER"))
                )
        );

        assertThat(CurrentUser.id()).isEqualTo(TestFixtures.USER_ID);
    }

    @Test
    void id_withoutAuthentication_throws() {
        SecurityContextHolder.clearContext();

        assertThatThrownBy(CurrentUser::id)
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("No authenticated user");
    }

    @Test
    void id_withNonUuidPrincipal_throws() {
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        "user",
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_USER"))
                )
        );

        assertThatThrownBy(CurrentUser::id)
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("No authenticated user");
    }
}
