package com.examassistant.security.service;

import com.examassistant.security.model.CustomUserDetails;
import com.examassistant.support.TestFixtures;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import jakarta.servlet.FilterChain;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class JwtAuthFilterTest {

    private static final String OTHER_SECRET =
            "another-secret-key-at-least-32-bytes-long-0000000000";

    private JwtService jwtService;
    private JwtAuthFilter filter;

    @BeforeEach
    void setUp() {
        jwtService = new JwtService(TestFixtures.JWT_SECRET, 60);
        filter = new JwtAuthFilter(jwtService);
    }

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void noAuthorizationHeader_continuesWithoutAuthentication() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request, response, chain);

        verify(chain).doFilter(request, response);
        assertThat(SecurityContextHolder.getContext().getAuthentication()).isNull();
    }

    @Test
    void nonBearerHeader_continuesWithoutAuthentication() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("Authorization", "Basic dXNlcjpwYXNz");
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request, response, chain);

        verify(chain).doFilter(request, response);
        assertThat(SecurityContextHolder.getContext().getAuthentication()).isNull();
    }

    @Test
    void validToken_setsCustomUserDetailsAuthentication() throws Exception {
        String token = jwtService.generate(TestFixtures.USER_ID, TestFixtures.EMAIL);
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("Authorization", "Bearer " + token);
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request, response, chain);

        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        assertThat(authentication).isNotNull();
        assertThat(authentication.getPrincipal()).isInstanceOf(CustomUserDetails.class);
        CustomUserDetails details = (CustomUserDetails) authentication.getPrincipal();
        assertThat(details.getUserId()).isEqualTo(TestFixtures.USER_ID);
        assertThat(details.getUsername()).isEqualTo(TestFixtures.EMAIL);
        assertThat(authentication.getDetails()).isEqualTo(TestFixtures.EMAIL);
        assertThat(authentication.getAuthorities())
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly("ROLE_USER");
        verify(chain).doFilter(request, response);
    }

    @Test
    void tokenWithInvalidSignature_clearsContextAndContinues() throws Exception {
        JwtService other = new JwtService(OTHER_SECRET, 60);
        String token = other.generate(TestFixtures.USER_ID, TestFixtures.EMAIL);
        SecurityContextHolder.getContext().setAuthentication(existingAuthentication());
        MockHttpServletRequest request = requestWithToken(token);
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request, response, chain);

        assertThat(SecurityContextHolder.getContext().getAuthentication()).isNull();
        verify(chain).doFilter(request, response);
    }

    @Test
    void expiredToken_clearsContextAndContinues() throws Exception {
        JwtService expiredService = new JwtService(TestFixtures.JWT_SECRET, -1);
        String token = expiredService.generate(TestFixtures.USER_ID, TestFixtures.EMAIL);
        SecurityContextHolder.getContext().setAuthentication(existingAuthentication());
        MockHttpServletRequest request = requestWithToken(token);
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request, response, chain);

        assertThat(SecurityContextHolder.getContext().getAuthentication()).isNull();
        verify(chain).doFilter(request, response);
    }

    @Test
    void tokenWithoutSubject_clearsContextAndContinues() throws Exception {
        String token = tokenWithSubject(null);
        SecurityContextHolder.getContext().setAuthentication(existingAuthentication());
        MockHttpServletRequest request = requestWithToken(token);
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request, response, chain);

        assertThat(SecurityContextHolder.getContext().getAuthentication()).isNull();
        verify(chain).doFilter(request, response);
    }

    @Test
    void tokenWithMalformedSubject_clearsContextAndContinues() throws Exception {
        String token = tokenWithSubject("not-a-uuid");
        SecurityContextHolder.getContext().setAuthentication(existingAuthentication());
        MockHttpServletRequest request = requestWithToken(token);
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request, response, chain);

        assertThat(SecurityContextHolder.getContext().getAuthentication()).isNull();
        verify(chain).doFilter(request, response);
    }

    private MockHttpServletRequest requestWithToken(String token) {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("Authorization", "Bearer " + token);
        return request;
    }

    private UsernamePasswordAuthenticationToken existingAuthentication() {
        return new UsernamePasswordAuthenticationToken(
                "existing-user",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }

    private String tokenWithSubject(String subject) {
        SecretKey key = Keys.hmacShaKeyFor(
                TestFixtures.JWT_SECRET.getBytes(StandardCharsets.UTF_8));
        var builder = Jwts.builder()
                .claim("email", TestFixtures.EMAIL)
                .issuedAt(new Date())
                .expiration(new Date(System.currentTimeMillis() + 60_000))
                .signWith(key);
        if (subject != null) {
            builder.subject(subject);
        }
        return builder.compact();
    }
}
