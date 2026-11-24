package com.examassistant.tests.controller;

import com.examassistant.security.model.CustomUserDetails;
import com.examassistant.tests.DTO.AttemptResponse;
import com.examassistant.tests.DTO.SubmitAttemptRequest;
import com.examassistant.tests.DTO.SubmitAttemptResponse;
import com.examassistant.tests.service.AttemptsService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequiredArgsConstructor
public class AttemptsController {
    private final AttemptsService attemptsService;

    @PostMapping("/api/tests/{testId}/attempts")
    public ResponseEntity<SubmitAttemptResponse> submit(
            @PathVariable UUID testId,
            @Valid @RequestBody SubmitAttemptRequest request,
            @AuthenticationPrincipal CustomUserDetails user
    ) {
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(attemptsService.submit(testId, request, user.getUserId()));
    }

    @GetMapping("/api/attempts/{attemptId}")
    public AttemptResponse get(
            @PathVariable UUID attemptId,
            @AuthenticationPrincipal CustomUserDetails user
    ) {
        return attemptsService.get(attemptId, user.getUserId());
    }
}
