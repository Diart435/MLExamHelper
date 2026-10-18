package com.examassistant.auth.service;

import com.examassistant.auth.DTO.UserDTO;
import com.examassistant.auth.entity.User;
import com.examassistant.auth.repository.UserRepository;
import com.examassistant.common.exception.InvalidCredentialsException;
import com.examassistant.common.exception.InvalidTokenException;
import com.examassistant.common.exception.UserAlreadyExistException;
import com.examassistant.common.exception.UserNotFoundException;
import com.examassistant.auth.mapper.UserMapper;
import com.examassistant.security.service.JwtService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
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
    public void changePersonal(String email, String firstName, String lastName, UUID id){
        User user = userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(id.toString()));
        if(userRepository.existsByEmail(email)){
            throw new UserAlreadyExistException("User already exists");
        }
        user.setEmail(email);
        user.setFirstName(firstName);
        user.setLastName(lastName);
    }

    @Transactional
    public void changePassword(String lastPassword, String newPassword, UUID id){
        User user = userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(id.toString()));
        if(!passwordEncoder.matches(lastPassword, user.getPasswordHash())){
            throw new InvalidCredentialsException("Old password is incorrect");
        }

        if(lastPassword.equals(newPassword)){
            throw new InvalidCredentialsException("Both passwords is equals");
        }

        user.setPasswordHash(passwordEncoder.encode(newPassword));
        user.setUpdatedAt(OffsetDateTime.now());
    }
}
