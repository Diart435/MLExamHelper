package com.examassistant.tests.controller;

import com.examassistant.common.DTO.ApiError;
import com.examassistant.security.model.CustomUserDetails;
import com.examassistant.tests.DTO.AttemptResponse;
import com.examassistant.tests.DTO.SubmitAttemptRequest;
import com.examassistant.tests.service.AttemptsService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@Tag(name = "Attempts", description = "Endpoints for taking tests and reading results")
@RestController
@RequiredArgsConstructor
@RequestMapping("/api")
public class AttemptsController {

    private final AttemptsService attemptsService;

    @Operation(summary = "Submit an attempt",
            description = "Saves the answers and sends the attempt to ML for grading. Grading is asynchronous: "
                    + "the attempt comes back with status \"processing\" until the result arrives.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "202", description = "Attempt accepted and sent for grading"),
            @ApiResponse(responseCode = "400", description = "Invalid input data",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "Test not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @PostMapping("/tests/{testId}/attempts")
    public ResponseEntity<AttemptResponse> submit(
            @PathVariable UUID testId,
            @Valid @RequestBody SubmitAttemptRequest request,
            @AuthenticationPrincipal CustomUserDetails user
    ) {
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(attemptsService.submit(testId, request, user.getUserId()));
    }

    @Operation(summary = "Get attempt by ID",
            description = "Returns the attempt with the per-question breakdown. Available to the student "
                    + "who submitted it and to the owner of the test's course.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Attempt found"),
            @ApiResponse(responseCode = "403", description = "Forbidden - access denied",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "Attempt not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @GetMapping("/attempts/{attemptId}")
    public ResponseEntity<AttemptResponse> getById(
            @PathVariable UUID attemptId,
            @AuthenticationPrincipal CustomUserDetails user
    ) {
        return ResponseEntity.ok(attemptsService.getById(attemptId, user.getUserId()));
    }
}
