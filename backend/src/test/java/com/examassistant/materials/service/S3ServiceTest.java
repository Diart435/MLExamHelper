package com.examassistant.materials.service;

import com.examassistant.common.exception.StorageException;
import com.examassistant.support.TestFixtures;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.multipart.MultipartFile;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.BucketAlreadyExistsException;
import software.amazon.awssdk.services.s3.model.BucketAlreadyOwnedByYouException;
import software.amazon.awssdk.services.s3.model.CreateBucketRequest;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;
import software.amazon.awssdk.services.s3.presigner.model.PresignedGetObjectRequest;

import java.io.IOException;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class S3ServiceTest {

    private static final String BUCKET = "materials";

    @Mock
    private S3Client s3Client;
    @Mock
    private S3Presigner presigner;

    private S3Service s3Service;

    @BeforeEach
    void setUp() {
        s3Service = new S3Service(s3Client, presigner);
        ReflectionTestUtils.setField(s3Service, "bucket", BUCKET);
    }

    @Test
    void upload_withExtension_putsObjectWithExpectedKey() {
        MockMultipartFile file = new MockMultipartFile(
                "file", "lecture.pdf", "application/pdf", "data".getBytes(StandardCharsets.UTF_8));

        String key = s3Service.upload(TestFixtures.MATERIAL_ID, file);

        assertThat(key).isEqualTo(TestFixtures.MATERIAL_ID + "/file.pdf");

        ArgumentCaptor<PutObjectRequest> captor = ArgumentCaptor.forClass(PutObjectRequest.class);
        verify(s3Client).putObject(captor.capture(), any(RequestBody.class));
        PutObjectRequest request = captor.getValue();
        assertThat(request.bucket()).isEqualTo(BUCKET);
        assertThat(request.key()).isEqualTo(TestFixtures.MATERIAL_ID + "/file.pdf");
        assertThat(request.contentType()).isEqualTo("application/pdf");
        assertThat(request.contentLength()).isEqualTo(file.getSize());
    }

    @Test
    void upload_withoutExtension_usesFilePathWithoutSuffix() {
        MockMultipartFile file = new MockMultipartFile(
                "file", "README", "text/plain", "text".getBytes(StandardCharsets.UTF_8));

        String key = s3Service.upload(TestFixtures.MATERIAL_ID, file);

        assertThat(key).isEqualTo(TestFixtures.MATERIAL_ID + "/file");
        ArgumentCaptor<PutObjectRequest> captor = ArgumentCaptor.forClass(PutObjectRequest.class);
        verify(s3Client).putObject(captor.capture(), any(RequestBody.class));
        assertThat(captor.getValue().key()).isEqualTo(TestFixtures.MATERIAL_ID + "/file");
    }

    @Test
    void upload_nullFilename_usesFilePathWithoutSuffix() throws IOException {
        MultipartFile file = mock(MultipartFile.class);
        byte[] content = "data".getBytes(StandardCharsets.UTF_8);
        when(file.getOriginalFilename()).thenReturn(null);
        when(file.getContentType()).thenReturn("application/pdf");
        when(file.getSize()).thenReturn((long) content.length);
        when(file.getInputStream()).thenReturn(new java.io.ByteArrayInputStream(content));

        String key = s3Service.upload(TestFixtures.MATERIAL_ID, file);

        assertThat(key).isEqualTo(TestFixtures.MATERIAL_ID + "/file");
    }

    @Test
    void upload_ioException_throwsStorageException() throws IOException {
        MultipartFile file = mock(MultipartFile.class);
        when(file.getOriginalFilename()).thenReturn("lecture.pdf");
        when(file.getInputStream()).thenThrow(new IOException("boom"));

        assertThatThrownBy(() -> s3Service.upload(TestFixtures.MATERIAL_ID, file))
                .isInstanceOf(StorageException.class)
                .hasMessage("Failed to upload file");

        verifyNoInteractions(s3Client);
    }

    @Test
    void generateDownloadUrl_returnsPresignedUrlAndUsesTtl() throws Exception {
        PresignedGetObjectRequest presigned = mock(PresignedGetObjectRequest.class);
        URL url = URI.create("https://signed.example/key.pdf").toURL();
        when(presigner.presignGetObject(any(GetObjectPresignRequest.class))).thenReturn(presigned);
        when(presigned.url()).thenReturn(url);

        String result = s3Service.generateDownloadUrl("materials/key.pdf", Duration.ofMinutes(15));

        assertThat(result).isEqualTo(url.toString());

        ArgumentCaptor<GetObjectPresignRequest> captor =
                ArgumentCaptor.forClass(GetObjectPresignRequest.class);
        verify(presigner).presignGetObject(captor.capture());
        GetObjectPresignRequest request = captor.getValue();
        assertThat(request.signatureDuration()).isEqualTo(Duration.ofMinutes(15));
        assertThat(request.getObjectRequest().bucket()).isEqualTo(BUCKET);
        assertThat(request.getObjectRequest().key()).isEqualTo("materials/key.pdf");
    }

    @Test
    void delete_removesObject() {
        s3Service.delete("materials/key.pdf");

        ArgumentCaptor<DeleteObjectRequest> captor = ArgumentCaptor.forClass(DeleteObjectRequest.class);
        verify(s3Client).deleteObject(captor.capture());
        assertThat(captor.getValue().bucket()).isEqualTo(BUCKET);
        assertThat(captor.getValue().key()).isEqualTo("materials/key.pdf");
    }

    @Test
    void init_createsBucket() {
        s3Service.init();

        ArgumentCaptor<CreateBucketRequest> captor = ArgumentCaptor.forClass(CreateBucketRequest.class);
        verify(s3Client).createBucket(captor.capture());
        assertThat(captor.getValue().bucket()).isEqualTo(BUCKET);
    }

    @Test
    void init_bucketAlreadyExists_doesNotThrow() {
        when(s3Client.createBucket(any(CreateBucketRequest.class)))
                .thenThrow(BucketAlreadyExistsException.builder().message("exists").build());

        assertThatCode(() -> s3Service.init()).doesNotThrowAnyException();
    }

    @Test
    void init_bucketAlreadyOwnedByYou_doesNotThrow() {
        when(s3Client.createBucket(any(CreateBucketRequest.class)))
                .thenThrow(BucketAlreadyOwnedByYouException.builder().message("exists").build());

        assertThatCode(() -> s3Service.init()).doesNotThrowAnyException();
    }

    @Test
    void init_otherS3Exception_doesNotThrow() {
        when(s3Client.createBucket(any(CreateBucketRequest.class)))
                .thenThrow(S3Exception.builder().message("boom").build());

        assertThatCode(() -> s3Service.init()).doesNotThrowAnyException();
    }
}
