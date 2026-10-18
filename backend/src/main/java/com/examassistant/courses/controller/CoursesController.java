package com.examassistant.courses.controller;

import com.examassistant.common.DTO.ApiError;
import com.examassistant.courses.mapper.CourseMapper;
import com.examassistant.courses.DTO.CourseFilter;
import com.examassistant.courses.DTO.CoursesResponse;
import com.examassistant.courses.DTO.CreateCourseRequest;
import com.examassistant.courses.DTO.UpdateCourseRequest;
import com.examassistant.courses.service.CoursesService;
import com.examassistant.security.model.CustomUserDetails;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@Tag(name = "Courses", description = "Endpoints for managing courses")
@RestController
@Validated
@RequiredArgsConstructor
@RequestMapping("/api/courses")
public class CoursesController {

    private final CoursesService coursesService;
    private final CourseMapper courseMapper;

    @Operation(summary = "Create a new course", description = "Creates a course assigned to a specific owner.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "201", description = "Course created successfully"),
            @ApiResponse(responseCode = "400", description = "Invalid request data or course title already exists for this user",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "500", description = "Internal server error",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @PostMapping
    public ResponseEntity<CoursesResponse> create(
            @Valid @RequestBody CreateCourseRequest create,
            @AuthenticationPrincipal CustomUserDetails user
            ) {
        CoursesResponse course = courseMapper.toResponse(coursesService.create(create, user.getUserId()));
        return ResponseEntity.status(HttpStatus.CREATED).body(course);
    }

    @Operation(summary = "Get course by ID", description = "Retrieves a single course by its unique identifier.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Course found"),
            @ApiResponse(responseCode = "400", description = "Invalid ID format",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "Course not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "500", description = "Internal server error",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @GetMapping("/{id}")
    public ResponseEntity<CoursesResponse> getById(
            @PathVariable @NotNull UUID id,
            @AuthenticationPrincipal CustomUserDetails user) {
        CoursesResponse course = courseMapper.toResponse(coursesService.getById(id, user.getUserId()));
        return ResponseEntity.ok(course);
    }

    @Operation(summary = "Search courses", description = "Searches courses using filters and pagination.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Page of courses retrieved successfully"),
            @ApiResponse(responseCode = "400", description = "Invalid filter or pagination parameters",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "500", description = "Internal server error",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @GetMapping
    public ResponseEntity<Page<CoursesResponse>> search(
            @Valid @ModelAttribute CourseFilter filter,
            Pageable pageable,
            @AuthenticationPrincipal CustomUserDetails user
    ) {
        Page<CoursesResponse> courses = coursesService.search(filter, pageable, user.getUserId()).map(courseMapper::toResponse);
        return ResponseEntity.ok(courses);
    }

    @Operation(summary = "Update course", description = "Updates an existing course details completely.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Course updated successfully"),
            @ApiResponse(responseCode = "400", description = "Invalid request data or title duplicate",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "Course not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "500", description = "Internal server error",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @PutMapping("/{id}")
    public ResponseEntity<CoursesResponse> update(
            @PathVariable @NotNull UUID id,
            @Valid @RequestBody UpdateCourseRequest request,
            @AuthenticationPrincipal CustomUserDetails user
    ) {
        CoursesResponse updated = courseMapper.toResponse(coursesService.update(id, request, user.getUserId()));
        return ResponseEntity.ok(updated);
    }

    @Operation(summary = "Delete course", description = "Deletes a course by its unique ID.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "204", description = "Course deleted successfully"),
            @ApiResponse(responseCode = "404", description = "Course not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "500", description = "Internal server error",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(
            @PathVariable @NotNull UUID id,
            @AuthenticationPrincipal CustomUserDetails user) {
        coursesService.delete(id, user.getUserId());
    }
}