package com.examassistant.tests.DTO;

import com.examassistant.tests.TestAmountQuestions;
import com.examassistant.tests.TestDifficulty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CreateTestRequest {

    @NotNull(message = "Course ID must not be null")
    private UUID courseId;

    @NotBlank(message = "Title must not be blank")
    @Size(max = 255, message = "Title must be up to 255 characters")
    private String title;

    private TestDifficulty difficulty;

    private TestAmountQuestions amountQuestions;
}