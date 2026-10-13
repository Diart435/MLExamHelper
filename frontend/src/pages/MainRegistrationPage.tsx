import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './MainRegistrationPage.css';

const MainRegistrationPage = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (!email.trim()) {
      alert('Пожалуйста, заполните почту!');
      return;
    }

    if (password !== confirmPassword) {
      alert('Пароли не совпадают!');
      return;
    }

    if (password.length < 8) {
      alert('Пароль должен содержать минимум 8 символов.');
      return;
    }

    setIsLoading(true);
    try {
      // Сохраняем данные для второго шага (бэкенд проверит уникальность почты там)
      sessionStorage.setItem('pendingEmail', email.trim());
      sessionStorage.setItem('pendingPassword', password);
      
      navigate('/register');
    } catch (error) {
      console.error('Ошибка при подготовке регистрации:', error);
      alert('Ошибка. Попробуйте снова.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="mr-page">
      <div className="mr-bolts" />
      <div className="mr-chevron" />
      <div className="mr-nav-green" />
      
      <div className="mr-nav-black">
        <button className="mr-nav-logo-btn" type="button" onClick={() => navigate('/welcome')}>
          <span className="mr-nav-logo-icon" />
          <span className="mr-nav-logo">ai-помощник</span>
        </button>
      </div>

      <div className="mr-card" />

      <form className="mr-form" onSubmit={handleSubmit}>
        <span className="mr-title">Регистрация</span>

        <div className="mr-field-group mr-field-email">
          <span className="mr-field-label">Почта</span>
          <div className="mr-field-box">
            <input
              className="mr-field-input"
              type="email"
              placeholder="пример@gmail.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={isLoading}
            />
          </div>
        </div>

        <div className="mr-field-group mr-field-password">
          <span className="mr-field-label">Пароль</span>
          <div className="mr-field-box">
            <input
              className="mr-field-input"
              type={showPassword ? 'text' : 'password'}
              placeholder="введите ваш пароль"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={isLoading}
            />
            <button
              type="button"
              className="mr-eye-btn"
              onClick={() => setShowPassword(!showPassword)}
              disabled={isLoading}
              aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'}
            >
              <span className="mr-eye-icon" />
            </button>
          </div>
        </div>

        <div className="mr-field-group mr-field-confirm">
          <span className="mr-field-label">Подтвердите пароль</span>
          <div className="mr-field-box">
            <input
              className="mr-field-input"
              type={showConfirmPassword ? 'text' : 'password'}
              placeholder="повторите пароль"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              disabled={isLoading}
            />
            <button
              type="button"
              className="mr-eye-btn"
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
              disabled={isLoading}
              aria-label={showConfirmPassword ? 'Скрыть пароль' : 'Показать пароль'}
            >
              <span className="mr-eye-icon" />
            </button>
          </div>
        </div>

        <button type="submit" className="mr-submit" disabled={isLoading}>
          {isLoading ? 'Загрузка...' : 'Далее'}
        </button>

        <span className="mr-stripe mr-stripe-left mr-stripe-active" />
        <Link to="/register" className="mr-stripe mr-stripe-right" title="Перейти к шагу 2" />

        <div className="mr-footer">
          <span className="mr-footer-line" />
          <span className="mr-footer-text">Уже есть аккаунт?</span>
          <Link to="/login" className="mr-footer-link">Войти</Link>
          <span className="mr-footer-line" />
        </div>
      </form>
    </div>
  );
};

export default MainRegistrationPage;