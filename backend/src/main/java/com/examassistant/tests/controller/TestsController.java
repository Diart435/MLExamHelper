package com.examassistant.tests.controller;

import com.examassistant.common.DTO.ApiError;
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
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
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

    @Operation(summary = "Create a test", description = "Creates a new test linked to a course with validation.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "201", description = "Test successfully created"),
            @ApiResponse(responseCode = "400", description = "Invalid input data or validation error",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "Course not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @PostMapping
    public ResponseEntity<TestsResponse> create(
            @Valid @RequestBody CreateTestRequest request
    ) {
        TestsResponse createdTest = testsService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(createdTest);
    }

    @Operation(summary = "Get test by ID", description = "Retrieves test details by its UUID.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Test found"),
            @ApiResponse(responseCode = "400", description = "Invalid UUID format or null value",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "Test not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @GetMapping("/{id}")
    public ResponseEntity<TestsResponse> getById(
            @PathVariable @NotNull UUID id,
            @RequestParam @NotNull UUID courseId
    ) {
        TestsResponse test = testMapper.toResponse(testsService.getById(id, courseId));
        return ResponseEntity.ok(test);
    }

    @Operation(summary = "Search and filter tests", description = "Returns filtered list of tests by course and status with pagination and sorting.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Page of tests retrieved successfully"),
            @ApiResponse(responseCode = "400", description = "Invalid filter or pagination parameters",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @GetMapping
    public ResponseEntity<Page<TestsResponse>> search(
            @Valid @ModelAttribute TestFilter filter,
            @RequestParam(name = "page", defaultValue = "0") @Min(value = 0, message = "Page index must not be less than zero") int page,
            @RequestParam(name = "size", defaultValue = "10") @Min(value = 1, message = "Page size must be greater than zero") int size,
            Pageable pageable
    ) {
        Pageable validatedPageable = PageRequest.of(page, size, pageable.getSort());

        Page<TestsResponse> tests = testsService.search(filter, validatedPageable);
        return ResponseEntity.ok(tests);
    }

    @Operation(summary = "Delete test", description = "Deletes a test by its UUID.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "204", description = "Test successfully deleted"),
            @ApiResponse(responseCode = "400", description = "Invalid UUID format",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "Test not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(
            @PathVariable @NotNull(message = "Test ID must not be null") UUID id
    ) {
        testsService.delete(id);
    }
}