package com.examassistant.architecture;

import com.examassistant.ExamAssistantApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

public class ArchUnit {
    static final ApplicationModules MODULES =
            ApplicationModules.of(ExamAssistantApplication.class);

    @Test
    void verifiesModularStructure() {
        MODULES.verify();
    }

    @Test
    void writesDocumentation() {
        new Documenter(MODULES)
                .writeDocumentation();
    }
}
