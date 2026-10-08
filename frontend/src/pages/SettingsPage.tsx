import { useState, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import './SettingsPage.css';

const SettingsPage = () => {
 
  // Получаем данные из store
  const email = useAuthStore((state) => state.email) || '';
  const firstName = useAuthStore((state) => state.firstName) || '';
  const lastName = useAuthStore((state) => state.lastName) || '';
  const updateUser = useAuthStore((state) => state.updateUser);

  // Локальные состояния (предзаполнены текущими данными)
  const [newFirstName, setNewFirstName] = useState(firstName);
  const [newLastName, setNewLastName] = useState(lastName);
  const [newEmail, setNewEmail] = useState(email);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [showOldPassword, setShowOldPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);

  // Обновляем локальные состояния, если данные в store изменились
  useEffect(() => {
    setNewFirstName(firstName);
    setNewLastName(lastName);
    setNewEmail(email);
  }, [firstName, lastName, email]);

  const handleApplyProfile = () => {
    const users = JSON.parse(localStorage.getItem('mock_users') || '[]');
    const userIndex = users.findIndex((u: any) => u.email === email);

    if (userIndex === -1) {
      alert('Пользователь не найден в системе. Войдите заново.');
      return;
    }

    // Если поле не пустое — обновляем, иначе оставляем старое
    const updatedUser = {
      ...users[userIndex],
      firstName: newFirstName.trim() || users[userIndex].firstName,
      lastName: newLastName.trim() || users[userIndex].lastName,
      email: newEmail.trim() || users[userIndex].email,
    };

    // Проверяем, не занят ли новый email другим пользователем
    if (newEmail.trim() && newEmail.trim() !== email) {
      const emailExists = users.some(
        (u: any) => u.email.toLowerCase() === newEmail.trim().toLowerCase()
      );
      if (emailExists) {
        alert('Эта почта уже используется другим пользователем!');
        return;
      }
    }

    users[userIndex] = updatedUser;
    localStorage.setItem('mock_users', JSON.stringify(users));

    // Обновляем store (если поле пустое — передаём undefined, чтобы оставить старое)
    updateUser(
      newFirstName.trim() || undefined,
      newLastName.trim() || undefined,
      newEmail.trim() || undefined
    );

    alert('Профиль успешно обновлён!');
  };

  const handleChangePassword = () => {
    if (!oldPassword.trim() || !newPassword.trim()) {
      alert('Заполните оба поля пароля!');
      return;
    }

    if (newPassword.length < 6) {
      alert('Новый пароль должен содержать минимум 6 символов!');
      return;
    }

    const users = JSON.parse(localStorage.getItem('mock_users') || '[]');
    const userIndex = users.findIndex((u: any) => u.email === email);

    if (userIndex === -1) {
      alert('Пользователь не найден. Войдите заново.');
      return;
    }

    // Проверяем старый пароль
    if (users[userIndex].password !== oldPassword) {
      alert('Старый пароль введён неверно!');
      return;
    }

    // Обновляем пароль
    users[userIndex].password = newPassword;
    localStorage.setItem('mock_users', JSON.stringify(users));

    // Очищаем поля
    setOldPassword('');
    setNewPassword('');

    alert('Пароль успешно изменён!');
  };

  return (
    <div className="settings-content-wrapper">
      {/* Шапка */}
      <div className="settings-section settings-header-section">
        <h1 className="settings-title">Настройки</h1>
        <p className="settings-subtitle">
          Управляйте данными профиля и безопасностью аккаунта
        </p>
      </div>

      {/* Профиль */}
      <div className="settings-section profile-section">
        <div className="section-title-wrapper">
          <h2 className="section-title">Профиль</h2>
        </div>

        <div className="inputs-row">
          <div className="input-group">
            <label className="input-label">Изменить имя</label>
            <div className="input-wrapper">
              <input
                type="text"
                className="custom-input"
                placeholder={firstName}
                value={newFirstName}
                onChange={(e) => setNewFirstName(e.target.value)}
              />
            </div>
          </div>

          <div className="input-group">
            <label className="input-label">Изменить фамилию</label>
            <div className="input-wrapper">
              <input
                type="text"
                className="custom-input"
                placeholder={lastName}
                value={newLastName}
                onChange={(e) => setNewLastName(e.target.value)}
              />
            </div>
          </div>

          <div className="input-group">
            <label className="input-label">Изменить почту</label>
            <div className="input-wrapper">
              <input
                type="email"
                className="custom-input"
                placeholder={email}
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
              />
            </div>
          </div>
        </div>

        <button className="apply-btn" onClick={handleApplyProfile}>
          Применить
        </button>
      </div>

      {/* Смена пароля */}
      <div className="settings-section password-section">
        <div className="section-title-wrapper">
          <h2 className="section-title">Смена пароля</h2>
        </div>

        <div className="password-row">
          <div className="input-group">
            <label className="input-label">Старый пароль</label>
            <div className="input-wrapper">
              <input
                type={showOldPassword ? 'text' : 'password'}
                className="custom-input"
                placeholder="Ваш старый пароль"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
              />
              <button
                type="button"
                className="eye-btn"
                onClick={() => setShowOldPassword(!showOldPassword)}
                aria-label={showOldPassword ? 'Скрыть пароль' : 'Показать пароль'}
              >
                👁
              </button>
            </div>
          </div>

          <div className="input-group">
            <label className="input-label">Новый пароль</label>
            <div className="input-wrapper">
              <input
                type={showNewPassword ? 'text' : 'password'}
                className="custom-input"
                placeholder="Ваш новый пароль"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
              <button
                type="button"
                className="eye-btn"
                onClick={() => setShowNewPassword(!showNewPassword)}
                aria-label={showNewPassword ? 'Скрыть пароль' : 'Показать пароль'}
              >
                👁
              </button>
            </div>
          </div>
        </div>

        <button className="change-btn" onClick={handleChangePassword}>
          Изменить
        </button>
      </div>
    </div>
  );
};

export default SettingsPage;