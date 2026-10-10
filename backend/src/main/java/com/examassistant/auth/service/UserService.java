package com.examassistant.auth.service;

import com.examassistant.auth.DTO.UserDTO;
import com.examassistant.auth.entity.User;
import com.examassistant.auth.repository.UserRepository;
import com.examassistant.common.exception.UserNotFoundException;
import com.examassistant.common.mapper.UserMapper;
import com.examassistant.security.service.JwtService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
@RequiredArgsConstructor
public class UserService {
    private final UserRepository userRepository;
    private final RefreshTokenService refreshTokenService;
    private final JwtService jwtService;
    private final PasswordEncoder passwordEncoder;
    private final UserMapper userMapper;

    @Transactional(readOnly = true)
    public UserDTO getUserInfo(UUID id){
        User user = userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(id.toString()));
        return userMapper.toUserDTO(user);
    }

    @Transactional
    public void changePersonal(String firstName, String lastName, UUID id){
        User user = userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(id.toString()));;
        user.setFirstName(firstName);
        user.setLastName(lastName);
    }

    @Transactional
    public void changePassword(String password, UUID id){
        User user = userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(id.toString()));
        user.setPasswordHash(passwordEncoder.encode(password));
    }
}
