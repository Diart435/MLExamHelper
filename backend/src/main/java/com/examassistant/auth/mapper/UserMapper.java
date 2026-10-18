package com.examassistant.auth.mapper;

import com.examassistant.auth.DTO.UserDTO;
import com.examassistant.auth.entity.User;
import org.mapstruct.Mapper;

import java.util.UUID;

@Mapper(componentModel = "spring")
public interface UserMapper {
    UserDTO toUserDTO(User user);

    default String toStringUUID(UUID id) {
        return id.toString();
    }
}
