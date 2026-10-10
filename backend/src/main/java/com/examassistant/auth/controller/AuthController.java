package com.examassistant.auth.controller;

import com.examassistant.auth.DTO.*;
import com.examassistant.auth.service.AuthService;
import com.examassistant.auth.service.RefreshTokenService;
import com.examassistant.common.exception.InvalidTokenException;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.Duration;
import java.util.UUID;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/auth")
public class AuthController {
    private final AuthService authService;
    private final RefreshTokenService refreshTokenService;

    @Operation(
            summary = "Register an user",
            description = "Returns auth response"
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "201", description = "User registered"),
            @ApiResponse(responseCode = "400", description = "Bad request"),
            @ApiResponse(responseCode = "401", description = "Unauthorized"),
            @ApiResponse(responseCode = "409", description = "Conflict")
    })
    @PostMapping("/register")
    public ResponseEntity<AuthResponse> register(@Valid @RequestBody RegisterRequest register, HttpServletResponse response){
        AuthResponse auth = authService.register(register);
        String token = refreshTokenService.getToken(UUID.fromString(auth.getUserId()));

        ResponseCookie refreshCookie = ResponseCookie.from("refresh_token", token)
                .httpOnly(true)
                .secure(true)
                .path("/api/auth")
                .maxAge(Duration.ofDays(7))
                .sameSite("Strict")
                .build();
        response.addHeader(HttpHeaders.SET_COOKIE, refreshCookie.toString());

        return ResponseEntity.status(HttpStatus.CREATED).body(auth);
    }

    @Operation(
            summary = "Login an user",
            description = "Returns auth response"
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "User logged in"),
            @ApiResponse(responseCode = "400", description = "Bad request"),
            @ApiResponse(responseCode = "401", description = "Unauthorized"),
            @ApiResponse(responseCode = "409", description = "Conflict")
    })
    @PostMapping("/login")
    public ResponseEntity<AuthResponse> login(@Valid @RequestBody LoginRequest login, HttpServletResponse response){
        AuthResponse auth = authService.login(login);
        String token = refreshTokenService.getToken(UUID.fromString(auth.getUserId()));

        ResponseCookie refreshCookie = ResponseCookie.from("refresh_token", token)
                .httpOnly(true)
                .secure(true)
                .path("/api/auth")
                .maxAge(Duration.ofDays(7))
                .sameSite("Strict")
                .build();
        response.addHeader(HttpHeaders.SET_COOKIE, refreshCookie.toString());

        return ResponseEntity.ok(auth);

    }

    @Operation(
            summary = "Update a refresh token",
            description = "Returns auth response"
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Token refreshed"),
            @ApiResponse(responseCode = "400", description = "Bad request"),
            @ApiResponse(responseCode = "401", description = "Unauthorized"),
            @ApiResponse(responseCode = "404", description = "Not found")
    })
    @PostMapping("/refresh")
    public ResponseEntity<AuthResult> refresh(@CookieValue(name = "refresh_token", required = false) String refreshToken,
                                     HttpServletResponse response){
        if(refreshToken == null){
            throw new InvalidTokenException("Refresh token is null");
        }
       IssuedTokens tokens = authService.refresh(refreshToken);


        ResponseCookie newCookie = ResponseCookie.from("refresh_token", tokens.getRefreshToken())
                .httpOnly(true)
                .secure(true)
                .path("/api/auth")
                .maxAge(Duration.ofDays(7))
                .sameSite("Strict")
                .build();
        response.addHeader(HttpHeaders.SET_COOKIE, newCookie.toString());

        return ResponseEntity.ok(new AuthResult(tokens.getAccessToken()));
    }

    @Operation(
            summary = "Logout an user",
            description = "Returns auth response"
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "204", description = "User logged out"),
            @ApiResponse(responseCode = "400", description = "Bad request"),
            @ApiResponse(responseCode = "401", description = "Unauthorized")
    })
    @PostMapping("/logout")
    public ResponseEntity<Void> logout(@CookieValue(name = "refresh_token", required = false) String refreshToken) {
        if(refreshToken == null){
            throw new InvalidTokenException("Refresh token is null");
        }
        authService.logout(refreshToken);
        return ResponseEntity.noContent().build();
    }
}
