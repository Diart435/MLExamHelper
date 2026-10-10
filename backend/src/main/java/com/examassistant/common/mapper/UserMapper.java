package com.examassistant.common.mapper;

import com.examassistant.auth.DTO.UserDTO;
import com.examassistant.auth.entity.User;
import org.mapstruct.Mapper;

@Mapper(componentModel = "spring")
public interface UserMapper {
    UserDTO toUserDTO(User user);
}
