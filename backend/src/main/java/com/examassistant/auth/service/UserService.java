package com.examassistant.auth.service;

import com.examassistant.auth.DTO.UserDTO;
import com.examassistant.auth.DTO.VkUserInfoResponse;
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
import java.util.Optional;
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
        if(id == null){
            throw new InvalidCredentialsException("Id is null");
        }
        User user = userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(id.toString()));
        return userMapper.toUserDTO(user);
    }

    @Transactional
    public void changePersonal(String email, String firstName, String lastName, UUID id){
        if(id == null){
            throw new InvalidCredentialsException("Id is null");
        }
        User user = userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(id.toString()));
        if (!user.getEmail().equals(email) && userRepository.existsByEmail(email)) {
            throw new UserAlreadyExistException("User already exists");
        }
        user.setEmail(email);
        user.setFirstName(firstName);
        user.setLastName(lastName);
        user.setUpdatedAt(OffsetDateTime.now());
    }

    @Transactional
    public void changePassword(String lastPassword, String newPassword, UUID id){
        if(id == null){
            throw new InvalidCredentialsException("Id is null");
        }
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

    @Transactional
    public User findOrCreateByVk(VkUserInfoResponse.VkUser vk) {
        String vkId = String.valueOf(vk.getUserId());

        Optional<User> byVk = userRepository.findByVkId(vkId);
        if (byVk.isPresent()) return byVk.get();

        if (vk.getEmail() != null && !vk.getEmail().isBlank()) {
            Optional<User> byEmail = userRepository.findByEmail(vk.getEmail());
            if (byEmail.isPresent()) {
                User u = byEmail.get();
                u.setVkId(vkId);
                return userRepository.save(u);
            }
        }

        User u = new User();
        u.setVkId(vkId);
        u.setEmail(vk.getEmail() != null && !vk.getEmail().isBlank()
                ? vk.getEmail()
                : "vk_" + vkId + "@vk.local");
        u.setFirstName(vk.getFirstName() != null ? vk.getFirstName() : "Пользователь");
        u.setLastName(vk.getLastName()  != null ? vk.getLastName()  : "");
        u.setPasswordHash(passwordEncoder.encode(UUID.randomUUID().toString()));
        return userRepository.save(u);
    }
}
