package com.examassistant.auth.controller;

import com.examassistant.auth.DTO.PasswordChangeRequest;
import com.examassistant.auth.DTO.PersonalChangeRequest;
import com.examassistant.auth.DTO.UserDTO;
import com.examassistant.auth.service.UserService;
import com.examassistant.common.DTO.ApiError;
import com.examassistant.security.model.CustomUserDetails;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@Tag(name = "User", description = "Endpoints for managing account")
@RestController
@RequestMapping("/api/user")
@RequiredArgsConstructor
public class UserController {
    private final UserService userService;

    @Operation(summary = "Update a personal data",
            description = "Returns a void")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "204", description = "Personal data updated"),
            @ApiResponse(responseCode = "400", description = "Bad request",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "401", description = "Unauthorized",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "User not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "409", description = "Email already exists",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @PutMapping("/change/personal")
    public ResponseEntity<?> changePersonal(@Valid @RequestBody PersonalChangeRequest request, @AuthenticationPrincipal CustomUserDetails userDetails){
        userService.changePersonal(request.getEmail(), request.getFirstName(), request.getLastName(), userDetails.getUserId());
        return ResponseEntity.noContent().build();
    }
    @Operation(summary = "Update a password",
              description = "Returns a void")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "204", description = "Password updated"),
            @ApiResponse(responseCode = "400", description = "Bad request",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "401", description = "Unauthorized",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "User not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @PutMapping("/change/password")
    public ResponseEntity<?> changePassword(@Valid @RequestBody PasswordChangeRequest request, @AuthenticationPrincipal CustomUserDetails userDetails){
        userService.changePassword(request.getLastPassword(), request.getNewPassword(), userDetails.getUserId());
        return ResponseEntity.noContent().build();
    }
    @Operation(summary = "Get auth",
            description = "Returns a void")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Get auth data"),
            @ApiResponse(responseCode = "401", description = "Unauthorized",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "User not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @GetMapping("/me")
    public ResponseEntity<UserDTO> getMe(@AuthenticationPrincipal CustomUserDetails userDetails){
        return ResponseEntity.ok(userService.getUserInfo(userDetails.getUserId()));
    }

}
