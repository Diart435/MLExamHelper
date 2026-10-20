package com.examassistant.courses;

import com.examassistant.courses.DTO.CourseFilter;
import com.examassistant.courses.DTO.CreateCourseRequest;
import com.examassistant.courses.DTO.UpdateCourseRequest;
import com.examassistant.courses.entity.Course;
import jakarta.validation.Valid;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

import java.util.UUID;

public interface CourseService {
    CourseDTO getDTOById(UUID id, UUID userId);
}
