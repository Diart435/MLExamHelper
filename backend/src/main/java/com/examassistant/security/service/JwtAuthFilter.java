package com.examassistant.security.service;

import com.examassistant.security.model.CustomUserDetails;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;
import java.util.UUID;

@RequiredArgsConstructor
@Slf4j
public class JwtAuthFilter extends OncePerRequestFilter {
    private final JwtService jwtService;

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain) throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        if(header == null || !header.startsWith("Bearer ")){
            chain.doFilter(request,response);
            return;
        }

        String token = header.substring(7);
        try {
            Claims claims = jwtService.parse(token);
            String subject = claims.getSubject();
            if (subject == null) {
                throw new JwtException("subject is null");
            }
            UUID userId = UUID.fromString(subject);
            String email = claims.get("email", String.class);

            CustomUserDetails userDetails = new CustomUserDetails(
                    userId,
                    email,
                    List.of(new SimpleGrantedAuthority("ROLE_USER"))
            );
            UsernamePasswordAuthenticationToken auth = new UsernamePasswordAuthenticationToken(
                    userDetails,
                    null,
                    userDetails.getAuthorities()
            );
            auth.setDetails(email);
            SecurityContextHolder.getContext().setAuthentication(auth);
        }
        catch (JwtException e) {
            SecurityContextHolder.clearContext();
            log.warn("JWT validation failed: {}", e.getMessage());
        } catch (IllegalArgumentException e) {
            SecurityContextHolder.clearContext();
            log.warn("Invalid JWT subject format: {}", e.getMessage());
        }

        chain.doFilter(request, response);
    }
}
