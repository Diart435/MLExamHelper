package com.examassistant.materials.controller;

import com.examassistant.common.DTO.ApiError;
import com.examassistant.common.exception.FileUploadException;
import com.examassistant.materials.DTO.ChangeFileNameRequest;
import com.examassistant.materials.DTO.MaterialResponse;
import com.examassistant.materials.mapper.MaterialMapper;
import com.examassistant.materials.service.MaterialService;
import com.examassistant.security.model.CustomUserDetails;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.UUID;

@Tag(name = "Materials", description = "Endpoints for managing materials")
@RestController
@RequiredArgsConstructor
@RequestMapping("/api/materials")
public class MaterialController {
    private final MaterialService materialService;
    private final MaterialMapper materialMapper;

    @Operation(summary = "Upload material", description = "Upload material for course.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "201", description = "Material uploaded"),
            @ApiResponse(responseCode = "400", description = "Material not validated",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "401", description = "Unauthorized",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @PostMapping(path = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<MaterialResponse> addMaterial(
            @RequestParam UUID courseId,
            @RequestPart("file")MultipartFile file,
            @AuthenticationPrincipal CustomUserDetails user
            ) throws IOException {
        if(file.isEmpty()){
            throw new FileUploadException("File is empty");
        }
        if(file.getSize() > 50 * 1024 * 1024){
            throw new FileUploadException("File is too large");
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(materialService.save(courseId, file, user.getUserId()));
    }

    @Operation(summary = "Get materials by course", description = "Returns a page of materials.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Materials found"),
            @ApiResponse(responseCode = "400", description = "Bad Request",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "401", description = "Unauthorized",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @GetMapping
    public ResponseEntity<Page<MaterialResponse>> getByCourse(
            @RequestParam UUID courseId,
            Pageable pageable,
            @AuthenticationPrincipal CustomUserDetails user
    ) {
        return ResponseEntity.ok(materialService.findByCourseId(courseId, pageable, user.getUserId()).map(materialMapper::toDTO));
    }

    @Operation(summary = "Get material by id", description = "Returns a material with download link.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Material found"),
            @ApiResponse(responseCode = "401", description = "Unauthorized",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "403", description = "Forbidden",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "Not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @GetMapping("/{id}")
    public ResponseEntity<MaterialResponse> getById(
            @PathVariable UUID id,
            @AuthenticationPrincipal CustomUserDetails user
    ) {
        return ResponseEntity.ok(materialService.toResponse(materialService.findById(id, user.getUserId())));
    }

    @Operation(summary = "Change filename of material", description = "Returns a material.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Material's name changed"),
            @ApiResponse(responseCode = "401", description = "Unauthorized",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "403", description = "Forbidden",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "Not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @PutMapping("/change/{id}")
    public ResponseEntity<MaterialResponse> changeFileName(
            @PathVariable UUID id,
            @Valid ChangeFileNameRequest request,
            @AuthenticationPrincipal CustomUserDetails user){
        return ResponseEntity.ok(materialService.toResponse(materialService.changeFileName(id, request.getTitle(), user.getUserId())));
    }

    @Operation(summary = "Delete a material", description = "Returns a void.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "204", description = "Material deleted"),
            @ApiResponse(responseCode = "401", description = "Unauthorized",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "403", description = "Forbidden",
                    content = @Content(schema = @Schema(implementation = ApiError.class))),
            @ApiResponse(responseCode = "404", description = "Not found",
                    content = @Content(schema = @Schema(implementation = ApiError.class)))
    })
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> deleteById(
            @PathVariable UUID id,
            @AuthenticationPrincipal CustomUserDetails user
            ){
        materialService.delete(id, user.getUserId());
        return ResponseEntity.noContent().build();
    }
}
