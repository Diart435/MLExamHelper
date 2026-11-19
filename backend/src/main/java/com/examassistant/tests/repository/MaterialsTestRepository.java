package com.examassistant.tests.repository;

import com.examassistant.tests.entity.MaterialsTest;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface MaterialsTestRepository extends JpaRepository<MaterialsTest, UUID> {
}
