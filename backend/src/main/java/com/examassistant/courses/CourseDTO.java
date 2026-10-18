package com.examassistant.courses;

import jakarta.persistence.Column;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import lombok.Data;

import java.time.OffsetDateTime;
import java.util.UUID;

@Data
public class CourseDTO {
    private UUID courseId;
    private String title;
    private String courseDescription;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
    private UUID ownerId;
}
