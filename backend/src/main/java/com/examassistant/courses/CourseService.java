package com.examassistant.courses;

import java.util.UUID;

public interface CourseService {
    CourseDTO getDTOById(UUID id, UUID userId);
}
