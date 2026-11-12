package com.examassistant.messaging.repository;

import com.examassistant.messaging.entity.QueryTask;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
public interface TaskRepository extends JpaRepository<QueryTask, UUID> {
}
