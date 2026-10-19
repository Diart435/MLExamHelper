import { useState, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { changePersonal, changePassword } from '../api/user';
import './SettingsPage.css';

const SettingsPage = () => {
  // Получаем данные и функцию обновления из store
  const email = useAuthStore((state) => state.email) || '';
  const firstName = useAuthStore((state) => state.firstName) || '';
  const lastName = useAuthStore((state) => state.lastName) || '';
  const updateUser = useAuthStore((state) => state.updateUser);

  // Локальные состояния
  const [newFirstName, setNewFirstName] = useState(firstName);
  const [newLastName, setNewLastName] = useState(lastName);
  const [newEmail, setNewEmail] = useState(email);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [showOldPassword, setShowOldPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // Синхронизируем локальные состояния, если данные в store изменились
  useEffect(() => {
    setNewFirstName(firstName);
    setNewLastName(lastName);
    setNewEmail(email);
  }, [firstName, lastName, email]);

  const handleApplyProfile = async () => {
    if (!newFirstName.trim() || !newLastName.trim() || !newEmail.trim()) {
      alert('Все поля профиля должны быть заполнены!');
      return;
    }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(newEmail.trim())) {
      alert('Пожалуйста, введите корректный адрес электронной почты!');
      return;
    }
    setIsLoading(true);
    try {
      // 1. Реальный запрос к API
      await changePersonal({
        email: newEmail.trim(),
        firstName: newFirstName.trim(),
        lastName: newLastName.trim(),
      });
      
      // 2. Обновляем store, чтобы сайдбар мгновенно отобразил новые данные
      updateUser(newFirstName.trim(), newLastName.trim(), newEmail.trim());
      
      alert('Профиль успешно обновлён!');
    } catch (error: any) {
      console.error('Ошибка обновления профиля:', error);
      const errorMsg = error.response?.data?.message || 'Ошибка при обновлении профиля. Возможно, эта почта уже занята.';
      alert(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

 const handleChangePassword = async () => {
    if (!oldPassword.trim()) {
      alert('Введите старый пароль!');
      return;
    }
    if (!newPassword.trim()) {
      alert('Введите новый пароль!');
      return;
    }
    if (newPassword.length < 6) {
      alert('Новый пароль должен содержать минимум 6 символов!');
      return;
    }

    setIsLoading(true);
    try {
      await changePassword({ 
        oldPassword: oldPassword, 
        newPassword: newPassword 
      });
      
      setOldPassword('');
      setNewPassword('');
      alert('Пароль успешно изменён!');
    } catch (error: any) {
      console.error('Ошибка смены пароля:', error);
      const errorMsg = error.response?.data?.message || 'Старый пароль указан неверно!';
      alert(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="settings-content-wrapper">
      <div className="settings-section settings-header-section">
        <h1 className="settings-title">Настройки</h1>
        <p className="settings-subtitle">
          Управляйте данными профиля и безопасностью аккаунта
        </p>
      </div>

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
                disabled={isLoading}
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
                disabled={isLoading}
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
                disabled={isLoading}
              />
            </div>
          </div>
        </div>

        <button className="apply-btn" onClick={handleApplyProfile} disabled={isLoading}>
          {isLoading ? 'Сохранение...' : 'Применить'}
        </button>
      </div>

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
                disabled={isLoading}
              />
              <button
                type="button"
                className="eye-btn"
                onClick={() => setShowOldPassword(!showOldPassword)}
                disabled={isLoading}
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
                disabled={isLoading}
              />
              <button
                type="button"
                className="eye-btn"
                onClick={() => setShowNewPassword(!showNewPassword)}
                disabled={isLoading}
                aria-label={showNewPassword ? 'Скрыть пароль' : 'Показать пароль'}
              >
                👁
              </button>
            </div>
          </div>
        </div>

        <button className="change-btn" onClick={handleChangePassword} disabled={isLoading}>
          {isLoading ? 'Изменение...' : 'Изменить'}
        </button>
      </div>
    </div>
  );
};

export default SettingsPage;