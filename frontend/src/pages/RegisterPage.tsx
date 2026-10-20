import { useState, type FormEvent, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import './RegisterPage.css';

const RegisterPage = () => {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const navigate = useNavigate();
  // Берём функцию register из нашего обновлённого стора
  const register = useAuthStore((state) => state.register);

  // Защита: если пользователь открыл эту страницу напрямую без шага 1, возвращаем его назад
  useEffect(() => {
    if (!sessionStorage.getItem('pendingEmail')) {
      navigate('/main-register');
    }
  }, [navigate]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (!firstName.trim() || !lastName.trim()) {
      alert('Имя и фамилия обязательны для заполнения!');
      return;
    }

    setIsLoading(true);
    try {
      const email = sessionStorage.getItem('pendingEmail') || '';
      const password = sessionStorage.getItem('pendingPassword') || '';

      // 1. Делаем реальный запрос к API
      await register(email, password, firstName.trim(), lastName.trim());

      // 2. Очищаем временные данные
      sessionStorage.removeItem('pendingEmail');
      sessionStorage.removeItem('pendingPassword');

      // 3. Перенаправляем в личный кабинет (так как register уже авторизовал пользователя и сохранил токен)
      navigate('/menu');
      
    } catch (error: any) {
      console.error('Ошибка при регистрации:', error);
      // Пытаемся показать сообщение от бэкенда, иначе стандартное
      const errorMsg = error.response?.data?.message || 'Ошибка при создании аккаунта. Возможно, эта почта уже занята.';
      alert(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="reg-page">
      <div className="reg-bolts" />
      <div className="reg-chevron" />
      <div className="reg-nav-green" />
      
      <div className="reg-nav-black">
        <button className="reg-nav-logo-btn" type="button" onClick={() => navigate('/welcome')}>
          <span className="reg-nav-logo-icon" />
          <span className="reg-nav-logo">ai-помощник</span>
        </button>
      </div>

      <div className="reg-card" />
      
      <form className="reg-form" onSubmit={handleSubmit}>
        <span className="reg-title">Регистрация</span>

        <div className="reg-field-group reg-field-1">
          <span className="reg-field-label">Ваше имя</span>
          <div className="reg-field-box">
            <input
              className="reg-field-input"
              type="text"
              placeholder="Иван"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              required
              disabled={isLoading}
            />
          </div>
        </div>

        <div className="reg-field-group reg-field-2">
          <span className="reg-field-label">Ваша фамилия</span>
          <div className="reg-field-box">
            <input
              className="reg-field-input"
              type="text"
              placeholder="Иванов"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              required
              disabled={isLoading}
            />
          </div>
        </div>

        <button type="submit" className="reg-submit" disabled={isLoading}>
          {isLoading ? 'Создание...' : 'Создать аккаунт'}
        </button>

        <Link to="/main-register" className="reg-stripe reg-stripe-left" title="Вернуться к шагу 1" />
        <span className="reg-stripe reg-stripe-right reg-stripe-active" />

        <div className="reg-footer">
          <span className="reg-footer-line" />
          <span className="reg-footer-text">Уже есть аккаунт?</span>
          <Link to="/login" className="reg-footer-link">Войти</Link>
          <span className="reg-footer-line" />
        </div>
      </form>
    </div>
  );
};

export default RegisterPage;