package com.examassistant.security.model;

import com.examassistant.support.TestFixtures;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class CustomUserDetailsTest {

    private final List<GrantedAuthority> authorities =
            List.of(new SimpleGrantedAuthority("ROLE_USER"));

    private final CustomUserDetails details =
            new CustomUserDetails(TestFixtures.USER_ID, TestFixtures.EMAIL, authorities);

    @Test
    void getters_returnConstructorValues() {
        assertThat(details.getUserId()).isEqualTo(TestFixtures.USER_ID);
        assertThat(details.getUsername()).isEqualTo(TestFixtures.EMAIL);
        assertThat(details.getPassword()).isNull();
        assertThat(details.getAuthorities())
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly("ROLE_USER");
    }

    @Test
    void accountFlags_areAllTrue() {
        assertThat(details.isAccountNonExpired()).isTrue();
        assertThat(details.isAccountNonLocked()).isTrue();
        assertThat(details.isCredentialsNonExpired()).isTrue();
        assertThat(details.isEnabled()).isTrue();
    }
}
