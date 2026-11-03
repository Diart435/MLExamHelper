package com.examassistant.tests.mapper;

import com.examassistant.tests.DTO.TestsResponse;
import com.examassistant.tests.TestDTO;
import com.examassistant.tests.entity.Test;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper(componentModel = "spring")
public interface TestMapper {

    @Mapping(source = "testId", target = "testId")
    @Mapping(source = "title", target = "title")
    @Mapping(source = "statusTest", target = "statusTest")
    @Mapping(source = "difficulty", target = "difficulty")
    @Mapping(source = "numQuestions", target = "numQuestions")
    TestsResponse toResponse(Test test);

    @Mapping(source = "testId", target = "testId")
    @Mapping(source = "title", target = "title")
    @Mapping(source = "statusTest", target = "statusTest")
    @Mapping(source = "difficulty", target = "difficulty")
    @Mapping(source = "numQuestions", target = "numQuestions")
    TestDTO toDTO(Test test);
}