package com.examassistant.materials.service;

import com.examassistant.common.exception.FileForbiddenException;
import com.examassistant.common.exception.FileNotFoundException;
import com.examassistant.common.exception.FileUploadException;
import com.examassistant.courses.CourseService;
import com.examassistant.messaging.ProcessMaterialRedisRequest;
import com.examassistant.messaging.Producer;
import com.examassistant.materials.DTO.MaterialResponse;
import com.examassistant.materials.MaterialService;
import com.examassistant.materials.entity.Material;
import com.examassistant.materials.enums.StatusMaterial;
import com.examassistant.materials.enums.TypeMaterial;
import com.examassistant.materials.mapper.MaterialMapper;
import com.examassistant.materials.repository.MaterialRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class MaterialsService implements MaterialService {
    private final S3Service s3Service;
    private final MaterialRepository materialRepository;
    private final MaterialMapper materialMapper;
    private final CourseService courseService;
    private final Producer redisProducer;

    @Transactional
    public MaterialResponse save(UUID courseId, MultipartFile file, UUID userId) throws IOException {
        if(!courseService.getDTOById(courseId, userId).getOwnerId().equals(userId)){
            throw new FileForbiddenException("This course is not yours");
        }
        UUID materialId = UUID.randomUUID();

        TypeMaterial typeMaterial = getTypeMaterial(file);

        Material material = new Material();
        material.setTypeMaterial(typeMaterial);
        material.setUserId(userId);
        material.setMaterialId(materialId);
        material.setCourseId(courseId);
        material.setStatusMaterial(StatusMaterial.PROCESSING);
        String filename = file.getOriginalFilename();
        if(filename == null) {
            throw new FileUploadException("filename is null");
        }
        material.setTitle(filename);
        material.setMaterialSize(file.getSize());

        String uri = s3Service.upload(materialId, file);
        material.setSourceUri(uri);
        material.setCreatedAt(OffsetDateTime.now());

        Material saved = materialRepository.save(material);
        sendProcessMaterial(saved);
        return toResponse(saved);
    }

    private TypeMaterial getTypeMaterial(MultipartFile file) throws IOException {
        byte[] header = new byte[4];
        try (InputStream is = file.getInputStream()) {
            if (is.read(header) != 4) {
                throw new FileUploadException("File is too small to be valid");
            }
        }

        TypeMaterial typeMaterial = null;

        if (header[0] == 0x25 && header[1] == 0x50 && header[2] == 0x44 && header[3] == 0x46) {
            typeMaterial = TypeMaterial.PDF;
        }
        else if (header[0] == 0x50 && header[1] == 0x4B && header[2] == 0x03 && header[3] == 0x04) {
            typeMaterial = TypeMaterial.DOCX;
        }
        else{
            throw new FileUploadException("The type of file can be DOCX or PDF");
        }
        return typeMaterial;
    }

    public MaterialResponse toResponse(Material material){
        MaterialResponse response = materialMapper.toDTO(material);
        response.setSourceUri(s3Service.generateDownloadUrl(material.getSourceUri(), Duration.ofMinutes(15)));
        return response;
    }

    @Transactional(readOnly = true)
    public Page<Material> findByCourseId(UUID courseId, Pageable pageable, UUID userId){
        if(courseService.getDTOById(courseId, userId).getOwnerId().equals(userId)){
            return materialRepository.findAllByCourseId(courseId, pageable);
        }
        else{
            throw new FileForbiddenException("This course is not yours");
        }
    }

    @Transactional(readOnly = true)
    public Material findById(UUID materialId, UUID userId){
        Material material = materialRepository.findById(materialId)
                .orElseThrow(() -> new FileNotFoundException("Invalid file id"));
        if(courseService.getDTOById(material.getCourseId(), userId).getOwnerId().equals(userId)){
            return material;
        }
        else{
            throw new FileForbiddenException("This file is not yours");
        }
    }

    @Transactional
    public Material changeFileName(UUID materialId, String title, UUID userId){
        Material material = findById(materialId, userId);
        material.setTitle(title);
        return materialRepository.save(material);
    }

    @Transactional
    public void delete(UUID materialId, UUID userId){
        Material material = materialRepository.findById(materialId)
                .orElseThrow(() -> new FileNotFoundException("Invalid file id"));
        if(!courseService.getDTOById(material.getCourseId(), userId).getOwnerId().equals(userId)){
            throw new FileForbiddenException("This course is not yours");
        }
        s3Service.delete(material.getSourceUri());
        materialRepository.delete(material);
    }

    @Transactional
    @Override
    public void changeStatus(UUID materialId, String status) {
        Material material = materialRepository.findById(materialId)
                .orElseThrow(() -> new FileNotFoundException("Invalid file id"));

        material.setStatusMaterial(StatusMaterial.fromValue(status));
    }

    public void sendProcessMaterial(Material material){
        UUID taskId = UUID.randomUUID();
        ProcessMaterialRedisRequest req = new ProcessMaterialRedisRequest(taskId, material.getMaterialId(), material.getSourceUri());
        redisProducer.publishMaterialProcess(req);
    }

    @Transactional
    public void deleteAll(List<UUID> materialIds, UUID userId) {
        List<UUID> distinctIds = List.copyOf(new LinkedHashSet<>(materialIds));
        List<Material> materials = materialRepository.findAllById(distinctIds);

        if (materials.size() != distinctIds.size()) {
            Set<UUID> foundIds = materials.stream()
                    .map(Material::getMaterialId)
                    .collect(java.util.stream.Collectors.toSet());
            List<UUID> missingIds = distinctIds.stream()
                    .filter(id -> !foundIds.contains(id))
                    .toList();
            throw new FileNotFoundException("Materials not found: " + missingIds);
        }

        Set<UUID> checkedCourseIds = new LinkedHashSet<>();
        for (Material material : materials) {
            UUID courseId = material.getCourseId();
            if (checkedCourseIds.add(courseId)) {
                if (!courseService.getDTOById(courseId, userId).getOwnerId().equals(userId)) {
                    throw new FileForbiddenException("This course is not yours");
                }
            }
        }

        for (Material material : materials) {
            s3Service.delete(material.getSourceUri());
        }
        materialRepository.deleteAll(materials);
    }

    @Transactional
    public List<MaterialResponse> move(List<UUID> materialIds, UUID targetCourseId, UUID userId) {
        if (!courseService.getDTOById(targetCourseId, userId).getOwnerId().equals(userId)) {
            throw new FileForbiddenException("Target course is not yours");
        }

        List<UUID> distinctIds = List.copyOf(new LinkedHashSet<>(materialIds));
        List<Material> materials = materialRepository.findAllById(distinctIds);

        if (materials.size() != distinctIds.size()) {
            Set<UUID> foundIds = materials.stream()
                    .map(Material::getMaterialId)
                    .collect(java.util.stream.Collectors.toSet());
            List<UUID> missingIds = distinctIds.stream()
                    .filter(id -> !foundIds.contains(id))
                    .toList();
            throw new FileNotFoundException("Materials not found: " + missingIds);
        }

        Set<UUID> checkedSourceCourseIds = new LinkedHashSet<>();
        for (Material material : materials) {
            UUID sourceCourseId = material.getCourseId();
            if (checkedSourceCourseIds.add(sourceCourseId)) {
                if (!courseService.getDTOById(sourceCourseId, userId).getOwnerId().equals(userId)) {
                    throw new FileForbiddenException("Source course is not yours");
                }
            }
        }

        for (Material material : materials) {
            if (!targetCourseId.equals(material.getCourseId())) {
                material.setCourseId(targetCourseId);
            }
        }

        return materialRepository.saveAll(materials).stream()
                .map(this::toResponse)
                .toList();
    }
}
