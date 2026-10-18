package com.examassistant.common.mapper;

import com.examassistant.courses.DTO.CoursesResponse;
import com.examassistant.courses.entity.Course;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper(componentModel = "spring")
public interface CourseMapper {

    @Mapping(source = "courseId", target = "courseId")
    @Mapping(source = "title", target = "title")
    @Mapping(source = "courseDescription", target = "courseDescription")
    CoursesResponse toResponse(Course course);
}