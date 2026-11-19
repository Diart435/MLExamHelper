package com.examassistant.materials.service;

import com.examassistant.common.exception.FileForbiddenException;
import com.examassistant.common.exception.FileNotFoundException;
import com.examassistant.common.exception.FileUploadException;
import com.examassistant.courses.CourseDTO;
import com.examassistant.courses.CourseService;
import com.examassistant.materials.DTO.MaterialResponse;
import com.examassistant.materials.entity.Material;
import com.examassistant.materials.mapper.MaterialMapper;
import com.examassistant.materials.repository.MaterialRepository;
import com.examassistant.messaging.Producer;
import com.examassistant.support.TestFixtures;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.web.multipart.MultipartFile;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.same;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MaterialServiceTest {

    @Mock
    private S3Service s3Service;
    @Mock
    private MaterialRepository materialRepository;
    @Mock
    private MaterialMapper materialMapper;
    @Mock
    private CourseService courseService;
    @Mock
    private Producer redisProducer;

    @InjectMocks
    private MaterialsService materialService;

    @Test
    void save_pdf_uploadsFileAndReturnsResponse() throws IOException {
        MockMultipartFile file = multipart("lecture.pdf", pdfBytes(), "application/pdf");
        stubOwnedCourse();
        when(s3Service.upload(any(UUID.class), same(file))).thenReturn("materials/key.pdf");
        when(materialRepository.save(any(Material.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));
        when(materialMapper.toDTO(any(Material.class))).thenAnswer(invocation -> toResponse(invocation.getArgument(0)));
        when(s3Service.generateDownloadUrl("materials/key.pdf", Duration.ofMinutes(15)))
                .thenReturn("https://signed.example/lecture.pdf");

        MaterialResponse response = materialService.save(TestFixtures.COURSE_ID, file, TestFixtures.USER_ID);

        assertThat(response.getMaterialId()).isNotNull();
        assertThat(response.getCourseId()).isEqualTo(TestFixtures.COURSE_ID);
        assertThat(response.getTitle()).isEqualTo("lecture.pdf");
        assertThat(response.getTypeMaterial()).isEqualTo("PDF");
        assertThat(response.getStatusMaterial()).isEqualTo("PROCESSING");
        assertThat(response.getMaterialSize()).isEqualTo(file.getSize());
        assertThat(response.getCreatedAt()).isNotNull();
        assertThat(response.getSourceUri()).isEqualTo("https://signed.example/lecture.pdf");

        ArgumentCaptor<Material> captor = ArgumentCaptor.forClass(Material.class);
        verify(materialRepository).save(captor.capture());
        Material saved = captor.getValue();
        assertThat(saved.getCourseId()).isEqualTo(TestFixtures.COURSE_ID);
        assertThat(saved.getSourceUri()).isEqualTo("materials/key.pdf");
        assertThat(saved.getTypeMaterial().name()).isEqualTo("PDF");
        assertThat(saved.getStatusMaterial().name()).isEqualTo("PROCESSING");
    }

    @Test
    void save_docx_detectsDocxType() throws IOException {
        MockMultipartFile file = multipart("lecture.docx", docxBytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
        stubOwnedCourse();
        when(s3Service.upload(any(UUID.class), same(file))).thenReturn("materials/key.docx");
        when(materialRepository.save(any(Material.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));
        when(materialMapper.toDTO(any(Material.class))).thenAnswer(invocation -> toResponse(invocation.getArgument(0)));
        when(s3Service.generateDownloadUrl("materials/key.docx", Duration.ofMinutes(15)))
                .thenReturn("https://signed.example/lecture.docx");

        MaterialResponse response = materialService.save(TestFixtures.COURSE_ID, file, TestFixtures.USER_ID);

        assertThat(response.getTypeMaterial()).isEqualTo("DOCX");
    }

    @Test
    void save_courseOfAnotherUser_throwsAndDoesNotTouchStorage() {
        MockMultipartFile file = multipart("lecture.pdf", pdfBytes(), "application/pdf");
        CourseDTO course = TestFixtures.courseDto(TestFixtures.COURSE_ID, TestFixtures.OTHER_USER_ID);
        when(courseService.getDTOById(TestFixtures.COURSE_ID, TestFixtures.USER_ID)).thenReturn(course);

        assertThatThrownBy(() -> materialService.save(TestFixtures.COURSE_ID, file, TestFixtures.USER_ID))
                .isInstanceOf(FileForbiddenException.class)
                .hasMessage("This course is not yours");

        verifyNoInteractions(s3Service, materialRepository, materialMapper);
    }

    @Test
    void save_fileShorterThanFourBytes_throws() {
        MockMultipartFile file = multipart("small.pdf", new byte[]{0x25, 0x50, 0x44}, "application/pdf");
        stubOwnedCourse();

        assertThatThrownBy(() -> materialService.save(TestFixtures.COURSE_ID, file, TestFixtures.USER_ID))
                .isInstanceOf(FileUploadException.class)
                .hasMessage("File is too small to be valid");

        verifyNoInteractions(s3Service, materialRepository, materialMapper);
    }

    @Test
    void save_unsupportedFileType_throws() {
        MockMultipartFile file = multipart("image.gif", "GIF8".getBytes(StandardCharsets.UTF_8), "image/gif");
        stubOwnedCourse();

        assertThatThrownBy(() -> materialService.save(TestFixtures.COURSE_ID, file, TestFixtures.USER_ID))
                .isInstanceOf(FileUploadException.class)
                .hasMessage("The type of file can be DOCX or PDF");

        verifyNoInteractions(s3Service, materialRepository, materialMapper);
    }

    @Test
    void save_nullFilename_throws() throws IOException {
        MultipartFile file = mock(MultipartFile.class);
        when(file.getInputStream()).thenReturn(new ByteArrayInputStream(pdfBytes()));
        when(file.getOriginalFilename()).thenReturn(null);
        stubOwnedCourse();

        assertThatThrownBy(() -> materialService.save(TestFixtures.COURSE_ID, file, TestFixtures.USER_ID))
                .isInstanceOf(FileUploadException.class)
                .hasMessage("filename is null");

        verifyNoInteractions(s3Service, materialRepository, materialMapper);
    }

    @Test
    void save_inputStreamFails_propagatesIOException() throws IOException {
        MultipartFile file = mock(MultipartFile.class);
        when(file.getInputStream()).thenThrow(new IOException("boom"));
        stubOwnedCourse();

        assertThatThrownBy(() -> materialService.save(TestFixtures.COURSE_ID, file, TestFixtures.USER_ID))
                .isInstanceOf(IOException.class)
                .hasMessage("boom");

        verifyNoInteractions(s3Service, materialRepository, materialMapper);
    }

    @Test
    void toResponse_setsPresignedUrl() {
        Material material = TestFixtures.material();
        MaterialResponse mapped = new MaterialResponse();
        when(materialMapper.toDTO(material)).thenReturn(mapped);
        when(s3Service.generateDownloadUrl(material.getSourceUri(), Duration.ofMinutes(15)))
                .thenReturn("https://signed.example/key.pdf");

        MaterialResponse response = materialService.toResponse(material);

        assertThat(response).isSameAs(mapped);
        assertThat(response.getSourceUri()).isEqualTo("https://signed.example/key.pdf");
        verify(materialMapper).toDTO(material);
    }

    @Test
    void findByCourseId_owner_returnsPage() {
        Pageable pageable = PageRequest.of(0, 10);
        Page<Material> page = new PageImpl<>(List.of(TestFixtures.material()), pageable, 1);
        stubOwnedCourse();
        when(materialRepository.findAllByCourseId(TestFixtures.COURSE_ID, pageable)).thenReturn(page);

        Page<Material> result = materialService.findByCourseId(
                TestFixtures.COURSE_ID, pageable, TestFixtures.USER_ID);

        assertThat(result).isSameAs(page);
        verify(materialRepository).findAllByCourseId(TestFixtures.COURSE_ID, pageable);
    }

    @Test
    void findByCourseId_notOwner_throws() {
        Pageable pageable = PageRequest.of(0, 10);
        CourseDTO course = TestFixtures.courseDto(TestFixtures.COURSE_ID, TestFixtures.OTHER_USER_ID);
        when(courseService.getDTOById(TestFixtures.COURSE_ID, TestFixtures.USER_ID)).thenReturn(course);

        assertThatThrownBy(() -> materialService.findByCourseId(
                TestFixtures.COURSE_ID, pageable, TestFixtures.USER_ID))
                .isInstanceOf(FileForbiddenException.class)
                .hasMessage("This course is not yours");

        verifyNoInteractions(materialRepository);
    }

    @Test
    void findById_owner_returnsMaterial() {
        Material material = TestFixtures.material();
        when(materialRepository.findById(TestFixtures.MATERIAL_ID)).thenReturn(Optional.of(material));
        stubOwnedCourse();

        Material result = materialService.findById(TestFixtures.MATERIAL_ID, TestFixtures.USER_ID);

        assertThat(result).isSameAs(material);
    }

    @Test
    void findById_missing_throws() {
        when(materialRepository.findById(TestFixtures.MATERIAL_ID)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> materialService.findById(TestFixtures.MATERIAL_ID, TestFixtures.USER_ID))
                .isInstanceOf(FileNotFoundException.class)
                .hasMessage("Invalid file id");

        verifyNoInteractions(courseService);
    }

    @Test
    void findById_notOwner_throws() {
        Material material = TestFixtures.material();
        CourseDTO course = TestFixtures.courseDto(TestFixtures.COURSE_ID, TestFixtures.OTHER_USER_ID);
        when(materialRepository.findById(TestFixtures.MATERIAL_ID)).thenReturn(Optional.of(material));
        when(courseService.getDTOById(TestFixtures.COURSE_ID, TestFixtures.USER_ID)).thenReturn(course);

        assertThatThrownBy(() -> materialService.findById(TestFixtures.MATERIAL_ID, TestFixtures.USER_ID))
                .isInstanceOf(FileForbiddenException.class)
                .hasMessage("This file is not yours");
    }

    @Test
    void changeFileName_updatesTitleAndSaves() {
        Material material = TestFixtures.material();
        when(materialRepository.findById(TestFixtures.MATERIAL_ID)).thenReturn(Optional.of(material));
        stubOwnedCourse();
        when(materialRepository.save(material)).thenReturn(material);

        Material result = materialService.changeFileName(
                TestFixtures.MATERIAL_ID, "renamed.pdf", TestFixtures.USER_ID);

        assertThat(result.getTitle()).isEqualTo("renamed.pdf");
        verify(materialRepository).save(material);
    }

    @Test
    void delete_owner_deletesFileFromStorageAndDatabase() {
        Material material = TestFixtures.material();
        when(materialRepository.findById(TestFixtures.MATERIAL_ID)).thenReturn(Optional.of(material));
        stubOwnedCourse();

        materialService.delete(TestFixtures.MATERIAL_ID, TestFixtures.USER_ID);

        verify(s3Service).delete(material.getSourceUri());
        verify(materialRepository).delete(material);
    }

    @Test
    void delete_missing_throwsAndDoesNotTouchStorage() {
        when(materialRepository.findById(TestFixtures.MATERIAL_ID)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> materialService.delete(TestFixtures.MATERIAL_ID, TestFixtures.USER_ID))
                .isInstanceOf(FileNotFoundException.class)
                .hasMessage("Invalid file id");

        verifyNoInteractions(s3Service);
    }

    @Test
    void delete_notOwner_throwsAndDoesNotTouchStorage() {
        Material material = TestFixtures.material();
        CourseDTO course = TestFixtures.courseDto(TestFixtures.COURSE_ID, TestFixtures.OTHER_USER_ID);
        when(materialRepository.findById(TestFixtures.MATERIAL_ID)).thenReturn(Optional.of(material));
        when(courseService.getDTOById(TestFixtures.COURSE_ID, TestFixtures.USER_ID)).thenReturn(course);

        assertThatThrownBy(() -> materialService.delete(TestFixtures.MATERIAL_ID, TestFixtures.USER_ID))
                .isInstanceOf(FileForbiddenException.class)
                .hasMessage("This course is not yours");

        verifyNoInteractions(s3Service);
    }

    private void stubOwnedCourse() {
        when(courseService.getDTOById(TestFixtures.COURSE_ID, TestFixtures.USER_ID))
                .thenReturn(TestFixtures.courseDto(TestFixtures.COURSE_ID, TestFixtures.USER_ID));
    }

    private MockMultipartFile multipart(String filename, byte[] content, String contentType) {
        return new MockMultipartFile("file", filename, contentType, content);
    }

    private byte[] pdfBytes() {
        return "%PDF-1.4 test".getBytes(StandardCharsets.UTF_8);
    }

    private byte[] docxBytes() {
        return new byte[]{0x50, 0x4B, 0x03, 0x04, 0x01, 0x02, 0x03};
    }

    private MaterialResponse toResponse(Material material) {
        MaterialResponse response = new MaterialResponse();
        response.setMaterialId(material.getMaterialId());
        response.setCourseId(material.getCourseId());
        response.setTitle(material.getTitle());
        response.setTypeMaterial(material.getTypeMaterial().name());
        response.setStatusMaterial(material.getStatusMaterial().name());
        response.setMaterialSize(material.getMaterialSize());
        response.setCreatedAt(material.getCreatedAt());
        return response;
    }
}
