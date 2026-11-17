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
import com.examassistant.messaging.GradeAttemptRedisRequest;
import com.examassistant.messaging.ProcessMaterialRedisRequest;
import com.examassistant.messaging.TaskDTO;
import com.examassistant.messaging.entity.QueryTask;
import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.ml.payload.MlCreateTestResult;
import com.examassistant.ml.payload.MlGradedItem;
import com.examassistant.ml.payload.MlGradeAttemptResult;
import com.examassistant.ml.payload.MlIngestResult;
import com.examassistant.ml.payload.MlQuestionData;
import com.examassistant.ml.payload.MlTestData;
import com.examassistant.security.model.CustomUserDetails;
import com.examassistant.tests.DTO.CreateTestRequest;
import com.examassistant.tests.entity.Question;
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
    public static final UUID ATTEMPT_ID = UUID.fromString("99999999-9999-9999-9999-999999999999");
    public static final UUID QUESTION_ID = UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");

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

    public static Test readyTest() {
        Test test = test();
        test.setStatusTest(TestStatus.READY);
        return test;
    }

    public static Question question() {
        return Question.builder()
                .questionId(QUESTION_ID)
                .testId(TEST_ID)
                .questionOrder(0)
                .typeQuestion(QuestionType.SINGLE_CHOICE)
                .textQuestion("What is 2+2?")
                .options(List.of("3", "4"))
                .answerKey(Map.of("correct_index", 1, "explanation", "2+2=4"))
                .keyPoints(List.of())
                .sourceChunkId(SOURCE_CHUNK_ID)
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

    public static MlQuestionData mlQuestionData() {
        return new MlQuestionData(
                1,
                "single_choice",
                "What is 2+2?",
                List.of("3", "4"),
                Map.of("correct_index", 1, "explanation", "2+2=4"),
                List.of(),
                SOURCE_CHUNK_ID.toString()
        );
    }

    public static MlCreateTestResult mlCreateTestResult() {
        return new MlCreateTestResult(
                TASK_ID.toString(),
                "ok",
                TEST_ID.toString(),
                new MlTestData("Math test", List.of(mlQuestionData())),
                null
        );
    }

    public static MlIngestResult mlIngestResult(String status) {
        return new MlIngestResult(TASK_ID.toString(), status, MATERIAL_ID.toString(), 3, null);
    }

    public static MlGradeAttemptResult mlGradeAttemptResult() {
        return new MlGradeAttemptResult(
                TASK_ID.toString(),
                "ok",
                ATTEMPT_ID.toString(),
                TEST_ID.toString(),
                50.0,
                3,
                List.of(new MlGradedItem(
                        QUESTION_ID.toString(), true, 1.0, "Верно", "4", "4")),
                null
        );
    }

    public static GradeAttemptRedisRequest gradeAttemptRedisRequest() {
        return new GradeAttemptRedisRequest(
                TASK_ID,
                ATTEMPT_ID,
                TEST_ID,
                USER_ID,
                List.of(Map.of(
                        "question_id", QUESTION_ID.toString(),
                        "student_answer", Map.of("index", 1)))
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
