package com.examassistant.support;

import com.examassistant.auth.entity.User;
import com.examassistant.common.enums.TestAmountQuestions;
import com.examassistant.common.enums.TestDifficulty;
import com.examassistant.courses.CourseDTO;
import com.examassistant.courses.entity.Course;
import com.examassistant.materials.entity.Material;
import com.examassistant.materials.enums.StatusMaterial;
import com.examassistant.materials.enums.TypeMaterial;
import com.examassistant.messaging.CreateTestRedisRequest;
import com.examassistant.messaging.ProcessMaterialRedisRequest;
import com.examassistant.messaging.TaskDTO;
import com.examassistant.messaging.entity.QueryTask;
import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.security.model.CustomUserDetails;
import com.examassistant.tests.DTO.CreateTestRequest;
import com.examassistant.tests.QuestionDTO;
import com.examassistant.tests.entity.Test;
import com.examassistant.tests.enums.QuestionType;
import com.examassistant.tests.enums.TestStatus;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class TestFixtures {

    public static final UUID USER_ID = UUID.fromString("11111111-1111-1111-1111-111111111111");
    public static final UUID OTHER_USER_ID = UUID.fromString("22222222-2222-2222-2222-222222222222");
    public static final UUID COURSE_ID = UUID.fromString("33333333-3333-3333-3333-333333333333");
    public static final UUID MATERIAL_ID = UUID.fromString("44444444-4444-4444-4444-444444444444");
    public static final UUID OTHER_MATERIAL_ID = UUID.fromString("55555555-5555-5555-5555-555555555555");
    public static final UUID TEST_ID = UUID.fromString("66666666-6666-6666-6666-666666666666");
    public static final UUID TASK_ID = UUID.fromString("77777777-7777-7777-7777-777777777777");
    public static final UUID SOURCE_CHUNK_ID = UUID.fromString("88888888-8888-8888-8888-888888888888");

    public static final String EMAIL = "student@example.com";
    public static final String OTHER_EMAIL = "other@example.com";
    public static final String PASSWORD_HASH = "encoded-old-password";
    public static final String JWT_SECRET = "test-secret-key-at-least-32-bytes-long-1234567890";
    public static final OffsetDateTime CREATED_AT = OffsetDateTime.parse("2026-01-01T10:00:00Z");

    private TestFixtures() {
    }

    public static User user() {
        return user(USER_ID, EMAIL);
    }

    public static User user(UUID id, String email) {
        return User.builder()
                .userId(id)
                .email(email)
                .passwordHash(PASSWORD_HASH)
                .firstName("Ivan")
                .lastName("Ivanov")
                .createdAt(CREATED_AT)
                .updatedAt(CREATED_AT)
                .build();
    }

    public static Course course() {
        return course(COURSE_ID, USER_ID, "Math");
    }

    public static Course course(UUID id, UUID ownerId, String title) {
        return Course.builder()
                .courseId(id)
                .ownerId(ownerId)
                .title(title)
                .courseDescription("Course description")
                .createdAt(CREATED_AT)
                .updatedAt(CREATED_AT)
                .build();
    }

    public static CourseDTO courseDto(UUID courseId, UUID ownerId) {
        CourseDTO dto = new CourseDTO();
        dto.setCourseId(courseId);
        dto.setOwnerId(ownerId);
        dto.setTitle("Math");
        dto.setCourseDescription("Course description");
        dto.setCreatedAt(CREATED_AT);
        dto.setUpdatedAt(CREATED_AT);
        return dto;
    }

    public static Material material() {
        return Material.builder()
                .materialId(MATERIAL_ID)
                .courseId(COURSE_ID)
                .typeMaterial(TypeMaterial.PDF)
                .title("lecture.pdf")
                .sourceUri("materials/key.pdf")
                .statusMaterial(StatusMaterial.READY)
                .materialSize(1024L)
                .createdAt(CREATED_AT)
                .build();
    }

    public static CustomUserDetails userDetails() {
        return new CustomUserDetails(
                USER_ID,
                EMAIL,
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }

    public static Test test() {
        return Test.builder()
                .testId(TEST_ID)
                .courseId(COURSE_ID)
                .title("Math test")
                .amountQuestions(TestAmountQuestions.MEDIUM)
                .statusTest(TestStatus.CREATED)
                .difficulty(TestDifficulty.MEDIUM)
                .createdAt(CREATED_AT)
                .build();
    }

    public static CreateTestRequest createTestRequest() {
        return CreateTestRequest.builder()
                .courseId(COURSE_ID)
                .title("Math test")
                .difficulty(TestDifficulty.MEDIUM)
                .amountQuestions(TestAmountQuestions.MEDIUM)
                .materialIds(List.of(MATERIAL_ID))
                .build();
    }

    public static QuestionDTO questionDto() {
        return new QuestionDTO(
                TEST_ID,
                QuestionType.SINGLE_CHOICE,
                "What is 2+2?",
                List.of("3", "4"),
                Map.of("correct", List.of("4")),
                SOURCE_CHUNK_ID
        );
    }

    public static TaskDTO taskDto() {
        return new TaskDTO(
                TEST_ID,
                COURSE_ID,
                "Math test",
                CREATED_AT,
                null,
                StatusTask.PROCESSING,
                TestAmountQuestions.MEDIUM,
                "medium"
        );
    }

    public static QueryTask queryTask() {
        return QueryTask.builder()
                .taskId(TASK_ID)
                .testId(TEST_ID)
                .title("Math test")
                .amountQuestions(TestAmountQuestions.MEDIUM)
                .difficulty(TestDifficulty.MEDIUM)
                .courseId(COURSE_ID)
                .createdAt(CREATED_AT)
                .statusTask(StatusTask.PROCESSING)
                .build();
    }

    public static CreateTestRedisRequest createTestRedisRequest() {
        return new CreateTestRedisRequest(
                TASK_ID,
                TEST_ID,
                List.of(MATERIAL_ID, OTHER_MATERIAL_ID),
                "Math test",
                TestAmountQuestions.MEDIUM,
                "medium",
                COURSE_ID
        );
    }

    public static ProcessMaterialRedisRequest processMaterialRedisRequest() {
        return new ProcessMaterialRedisRequest(TASK_ID, MATERIAL_ID, "materials/key.pdf");
    }
}
