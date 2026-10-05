package com.examassistant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableScheduling
@SpringBootApplication
public class ExamAssistantApplication {

	public static void main(String[] args) {
		SpringApplication.run(ExamAssistantApplication.class, args);
	}

}
