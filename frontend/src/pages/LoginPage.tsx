import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import './LoginPage.css';

const LoginPage = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const setToken = useAuthStore((state) => state.setToken);
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      // ЗАГЛУШКА
      await new Promise((resolve) => setTimeout(resolve, 800));
      setToken('mock_jwt_token_' + Date.now());
      navigate('/courses');
    } catch (error) {
      console.error('Ошибка при входе:', error);
      alert('Неверная почта или пароль.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="main-container">
      <div className="bolts" />
        <div className="chevron" />
          <div className="nav-green" />
            <div className="nav-black">
              <div className="nav-logo-wrap">
                <span className="nav-logo-icon" />
                <span className="nav-logo">ai-помощник</span>
              </div>
              <Link to="/register" className="nav-btn">Регистрация</Link>
            </div>
          <div className="top-btn top-btn-info">Информация</div>
      <Link to="/login" className="top-btn top-btn-login">Вход</Link>

      <div className="card" />

      {/* Форма */}
      <form className="login-form" onSubmit={handleSubmit}>
        <span className="form-title">Авторизация</span>

        <div className="field-group field-email">
          <span className="field-label">Почта</span>
          <div className="field-box">
            <input
              className="field-input"
              type="email"
              placeholder="пример@gmail.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={isLoading}
            />
          </div>
        </div>

        <div className="field-group field-password">
          <span className="field-label">Введите пароль</span>
          <div className="field-box">
            <input
              className="field-input"
              type={showPassword ? 'text' : 'password'}
              placeholder="введите ваш пароль"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={isLoading}
            />
            <button
              type="button"
              className="eye-btn"
              onClick={() => setShowPassword(!showPassword)}
              disabled={isLoading}
              aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'}
            >
              <span className="eye-icon" />
            </button>
          </div>
        </div>

        <button type="submit" className="submit-btn" disabled={isLoading}>
          {isLoading ? 'Вход...' : 'Войти'}
        </button>

        <div className="form-footer">
          <span className="footer-line" />
          <span className="footer-text">Нет аккаунта?</span>
          <Link to="/register" className="footer-link">Регистрация</Link>
          <span className="footer-line" />
        </div>
      </form>
    </div>
  );
};

export default LoginPage;