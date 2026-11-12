package com.examassistant.tests.entity;

import jakarta.persistence.*;
import lombok.*;

import java.util.UUID;

@Entity
@NoArgsConstructor
@Setter
@Getter
@Builder
@AllArgsConstructor
@Table(name = "materials_test")
public class MaterialsTest {
    @EmbeddedId
    private MaterialsTestId id;
}
