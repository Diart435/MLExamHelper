package com.examassistant.support;

import com.examassistant.auth.entity.User;
import com.examassistant.courses.CourseDTO;
import com.examassistant.courses.entity.Course;
import com.examassistant.materials.entity.Material;
import com.examassistant.materials.enums.StatusMaterial;
import com.examassistant.materials.enums.TypeMaterial;
import com.examassistant.security.model.CustomUserDetails;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

public final class TestFixtures {

    public static final UUID USER_ID = UUID.fromString("11111111-1111-1111-1111-111111111111");
    public static final UUID OTHER_USER_ID = UUID.fromString("22222222-2222-2222-2222-222222222222");
    public static final UUID COURSE_ID = UUID.fromString("33333333-3333-3333-3333-333333333333");
    public static final UUID MATERIAL_ID = UUID.fromString("44444444-4444-4444-4444-444444444444");

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
}
