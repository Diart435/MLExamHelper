package com.examassistant.courses.DTO;

import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;
import java.util.UUID;

@Getter
@Setter
public class CourseFilter {
    @Size(max = 255, message = "Search title query is too long")
    private String title;
}