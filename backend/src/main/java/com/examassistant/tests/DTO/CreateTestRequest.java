package com.examassistant.tests.DTO;

import com.examassistant.common.enums.TestAmountQuestions;
import com.examassistant.common.enums.TestDifficulty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
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

    @NotNull(message = "Difficulty must not be null")
    private TestDifficulty difficulty;

    @NotNull(message = "Amount must not be blank")
    private TestAmountQuestions amountQuestions;

    @NotEmpty
    private List<UUID> materialIds;
}