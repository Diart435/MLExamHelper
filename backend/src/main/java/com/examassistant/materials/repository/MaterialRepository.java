package com.examassistant.materials.repository;

import com.examassistant.materials.entity.Material;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface MaterialRepository extends JpaRepository<Material, UUID> {
    Page<Material> findAllByCourseId(UUID courseId, Pageable pageable);
    Optional<Material> findById(UUID id);
}
