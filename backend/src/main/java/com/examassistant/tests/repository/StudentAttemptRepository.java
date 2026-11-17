package com.examassistant.tests.repository;

import com.examassistant.tests.entity.StudentAttempt;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
public interface StudentAttemptRepository extends JpaRepository<StudentAttempt, UUID> {
}
