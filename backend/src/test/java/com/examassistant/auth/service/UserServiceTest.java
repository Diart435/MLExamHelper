package com.examassistant.auth.service;

import com.examassistant.auth.DTO.UserDTO;
import com.examassistant.auth.entity.User;
import com.examassistant.auth.mapper.UserMapper;
import com.examassistant.auth.repository.UserRepository;
import com.examassistant.common.exception.InvalidCredentialsException;
import com.examassistant.common.exception.UserAlreadyExistException;
import com.examassistant.common.exception.UserNotFoundException;
import com.examassistant.security.service.JwtService;
import com.examassistant.support.TestFixtures;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.time.OffsetDateTime;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class UserServiceTest {

    @Mock
    private UserRepository userRepository;
    @Mock
    private RefreshTokenService refreshTokenService;
    @Mock
    private JwtService jwtService;
    @Mock
    private PasswordEncoder passwordEncoder;
    @Mock
    private UserMapper userMapper;

    @InjectMocks
    private UserService userService;

    @Test
    void getUserInfo_nullId_throws() {
        assertThatThrownBy(() -> userService.getUserInfo(null))
                .isInstanceOf(InvalidCredentialsException.class)
                .hasMessage("Id is null");

        verifyNoInteractions(userRepository);
    }

    @Test
    void getUserInfo_userNotFound_throws() {
        when(userRepository.findById(TestFixtures.USER_ID)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> userService.getUserInfo(TestFixtures.USER_ID))
                .isInstanceOf(UserNotFoundException.class)
                .hasMessage(TestFixtures.USER_ID.toString());
    }

    @Test
    void getUserInfo_success_returnsMappedDto() {
        User user = TestFixtures.user();
        UserDTO dto = new UserDTO(
                TestFixtures.USER_ID.toString(),
                TestFixtures.EMAIL,
                "Ivan",
                "Ivanov"
        );
        when(userRepository.findById(TestFixtures.USER_ID)).thenReturn(Optional.of(user));
        when(userMapper.toUserDTO(user)).thenReturn(dto);

        UserDTO result = userService.getUserInfo(TestFixtures.USER_ID);

        assertThat(result).isSameAs(dto);
        verify(userMapper).toUserDTO(user);
    }

    @Test
    void changePersonal_sameEmail_updatesNamesWithoutDuplicateCheck() {
        User user = TestFixtures.user();
        when(userRepository.findById(TestFixtures.USER_ID)).thenReturn(Optional.of(user));

        OffsetDateTime before = OffsetDateTime.now().minusSeconds(1);
        userService.changePersonal(TestFixtures.EMAIL, "Petr", "Petrov", TestFixtures.USER_ID);

        assertThat(user.getEmail()).isEqualTo(TestFixtures.EMAIL);
        assertThat(user.getFirstName()).isEqualTo("Petr");
        assertThat(user.getLastName()).isEqualTo("Petrov");
        assertThat(user.getUpdatedAt()).isAfter(before);
        verify(userRepository, never()).existsByEmail(anyString());
    }

    @Test
    void changePersonal_newEmail_updatesAllFields() {
        User user = TestFixtures.user();
        String newEmail = "new@example.com";
        when(userRepository.findById(TestFixtures.USER_ID)).thenReturn(Optional.of(user));
        when(userRepository.existsByEmail(newEmail)).thenReturn(false);

        userService.changePersonal(newEmail, "Petr", "Petrov", TestFixtures.USER_ID);

        assertThat(user.getEmail()).isEqualTo(newEmail);
        assertThat(user.getFirstName()).isEqualTo("Petr");
        assertThat(user.getLastName()).isEqualTo("Petrov");
        verify(userRepository).existsByEmail(newEmail);
    }

    @Test
    void changePersonal_duplicateEmail_throwsAndKeepsUserUnchanged() {
        User user = TestFixtures.user();
        String newEmail = "taken@example.com";
        when(userRepository.findById(TestFixtures.USER_ID)).thenReturn(Optional.of(user));
        when(userRepository.existsByEmail(newEmail)).thenReturn(true);

        assertThatThrownBy(() -> userService.changePersonal(newEmail, "Petr", "Petrov", TestFixtures.USER_ID))
                .isInstanceOf(UserAlreadyExistException.class)
                .hasMessage("User already exists");

        assertThat(user.getEmail()).isEqualTo(TestFixtures.EMAIL);
        assertThat(user.getFirstName()).isEqualTo("Ivan");
        assertThat(user.getLastName()).isEqualTo("Ivanov");
    }

    @Test
    void changePersonal_nullId_throws() {
        assertThatThrownBy(() -> userService.changePersonal(TestFixtures.EMAIL, "Petr", "Petrov", null))
                .isInstanceOf(InvalidCredentialsException.class)
                .hasMessage("Id is null");

        verifyNoInteractions(userRepository);
    }

    @Test
    void changePersonal_userNotFound_throws() {
        when(userRepository.findById(TestFixtures.USER_ID)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> userService.changePersonal(
                TestFixtures.EMAIL, "Petr", "Petrov", TestFixtures.USER_ID))
                .isInstanceOf(UserNotFoundException.class)
                .hasMessage(TestFixtures.USER_ID.toString());
    }

    @Test
    void changePassword_success_updatesHashAndTimestamp() {
        User user = TestFixtures.user();
        when(userRepository.findById(TestFixtures.USER_ID)).thenReturn(Optional.of(user));
        when(passwordEncoder.matches("oldPassword1", TestFixtures.PASSWORD_HASH)).thenReturn(true);
        when(passwordEncoder.encode("newPassword1")).thenReturn("encoded-new-password");

        OffsetDateTime before = OffsetDateTime.now().minusSeconds(1);
        userService.changePassword("oldPassword1", "newPassword1", TestFixtures.USER_ID);

        assertThat(user.getPasswordHash()).isEqualTo("encoded-new-password");
        assertThat(user.getUpdatedAt()).isAfter(before);
        verify(passwordEncoder).encode("newPassword1");
    }

    @Test
    void changePassword_wrongOldPassword_throwsAndDoesNotEncode() {
        User user = TestFixtures.user();
        when(userRepository.findById(TestFixtures.USER_ID)).thenReturn(Optional.of(user));
        when(passwordEncoder.matches("wrongOld1", TestFixtures.PASSWORD_HASH)).thenReturn(false);

        assertThatThrownBy(() -> userService.changePassword("wrongOld1", "newPassword1", TestFixtures.USER_ID))
                .isInstanceOf(InvalidCredentialsException.class)
                .hasMessage("Old password is incorrect");

        assertThat(user.getPasswordHash()).isEqualTo(TestFixtures.PASSWORD_HASH);
        verify(passwordEncoder, never()).encode(anyString());
    }

    @Test
    void changePassword_samePassword_throwsAndDoesNotEncode() {
        User user = TestFixtures.user();
        when(userRepository.findById(TestFixtures.USER_ID)).thenReturn(Optional.of(user));
        when(passwordEncoder.matches("samePassword1", TestFixtures.PASSWORD_HASH)).thenReturn(true);

        assertThatThrownBy(() -> userService.changePassword("samePassword1", "samePassword1", TestFixtures.USER_ID))
                .isInstanceOf(InvalidCredentialsException.class)
                .hasMessage("Both passwords is equals");

        assertThat(user.getPasswordHash()).isEqualTo(TestFixtures.PASSWORD_HASH);
        verify(passwordEncoder, never()).encode(anyString());
    }

    @Test
    void changePassword_nullId_throws() {
        assertThatThrownBy(() -> userService.changePassword("oldPassword1", "newPassword1", null))
                .isInstanceOf(InvalidCredentialsException.class)
                .hasMessage("Id is null");

        verifyNoInteractions(userRepository);
    }

    @Test
    void changePassword_userNotFound_throws() {
        when(userRepository.findById(TestFixtures.USER_ID)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> userService.changePassword(
                "oldPassword1", "newPassword1", TestFixtures.USER_ID))
                .isInstanceOf(UserNotFoundException.class)
                .hasMessage(TestFixtures.USER_ID.toString());
    }
}
