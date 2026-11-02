package com.examassistant.tests.controller;

import com.examassistant.common.DTO.ApiError;
import com.examassistant.security.model.CustomUserDetails;
import com.examassistant.tests.TestDTO;
import com.examassistant.tests.DTO.CreateTestRequest;
import com.examassistant.tests.DTO.TestFilter;
import com.examassistant.tests.DTO.TestsResponse;
import com.examassistant.tests.mapper.TestMapper;
import com.examassistant.tests.service.TestsService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@Tag(name = "Tests", description = "Endpoints for managing tests")
@RestController
@Validated
@RequiredArgsConstructor
@RequestMapping("/api/tests")
public class TestsController {

    private final TestsService testsService;
    private final TestMapper testMapper;

    @Operation(summary = "Create a test", description = "Creates a new test linked to a course.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "201", description = "Test successfully created"),
            @ApiResponse(responseCode = "400", description = "Invalid input data",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "403", description = "Forbidden - course is not yours",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "Course not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @PostMapping
    public ResponseEntity<TestsResponse> create(
            @Valid @RequestBody CreateTestRequest request,
            @AuthenticationPrincipal CustomUserDetails user
    ) {
        TestsResponse createdTest = testMapper.toResponse(testsService.create(request, user.getUserId()));
        return ResponseEntity.status(HttpStatus.CREATED).body(createdTest);
    }

    @Operation(summary = "Get test by ID", description = "Retrieves test details by its UUID.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Test found"),
            @ApiResponse(responseCode = "403", description = "Forbidden - access denied",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "Test not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @GetMapping("/{id}")
    public ResponseEntity<TestDTO> getById(
            @PathVariable UUID id,
            @AuthenticationPrincipal CustomUserDetails user
    ) {
        TestDTO testDTO = testsService.getDTOById(id, user.getUserId());
        return ResponseEntity.ok(testDTO);
    }

    @Operation(summary = "Search and filter tests", description = "Returns filtered list of tests with pagination and sorting.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Page of tests retrieved successfully"),
            @ApiResponse(responseCode = "400", description = "Invalid pagination parameters",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @GetMapping
    public ResponseEntity<Page<TestsResponse>> search(
            @Valid @ModelAttribute TestFilter filter,
            @RequestParam(name = "page", defaultValue = "0") @Min(0) int page,
            @RequestParam(name = "size", defaultValue = "10") @Min(1) @Max(100) int size,
            Pageable pageable,
            @AuthenticationPrincipal CustomUserDetails user
    ) {
        Pageable validatedPageable = PageRequest.of(page, size, pageable.getSort());

        Page<TestsResponse> tests = testsService.search(filter, validatedPageable, user.getUserId())
                .map(testMapper::toResponse);
        return ResponseEntity.ok(tests);
    }

    @Operation(summary = "Delete test", description = "Deletes a test by its UUID.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "204", description = "Test successfully deleted"),
            @ApiResponse(responseCode = "401", description = "Unauthorized",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "403", description = "Forbidden - access denied",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "Test not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> deleteById(
            @PathVariable UUID id,
            @AuthenticationPrincipal CustomUserDetails user
    ) {
        testsService.delete(id, user.getUserId());
        return ResponseEntity.noContent().build();
    }
}