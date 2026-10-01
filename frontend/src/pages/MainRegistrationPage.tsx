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

    if (password !== confirmPassword) {
        alert('Пароли не совпадают!');
        return;
    }

    if (password.length < 6) {
        alert('Пароль должен содержать минимум 6 символов.');
        return;
    }

    setIsLoading(true);
    try {
        // ЗАГЛУШКА
        await new Promise((resolve) => setTimeout(resolve, 800));
        console.log('Шаг 1 регистрации:', { email, password });
        sessionStorage.setItem('pendingEmail', email);
        sessionStorage.setItem('pendingPassword', password);
        navigate('/register');
    } catch (error) {
        console.error('Ошибка при регистрации:', error);
        alert('Ошибка при создании аккаунта. Попробуйте снова.');
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
        <div className="mr-nav-logo-wrap">
          <span className="mr-nav-logo-icon" />
          <span className="mr-nav-logo">ai-помощник</span>
        </div>
        <span className="mr-nav-btn">Регистрация</span>
      </div>
      <div className="mr-top-btn mr-top-info">Информация</div>
      <Link to="/login" className="mr-top-btn mr-top-login">Вход</Link>

      <div className="mr-card" />

      <form className="mr-form" onSubmit={handleSubmit}>
        <span className="mr-title">Регистрация</span>

        {/* Поле: Почта */}
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

        {/* Поле: Пароль */}
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

        {/* Поле: Подтвердите пароль */}
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
          {isLoading ? 'Создание...' : 'Далее'}
        </button>

        <span className="mr-stripe mr-stripe-left mr-stripe-active" />
            <Link
            to="/register"
            className="mr-stripe mr-stripe-right"
            title="Перейти к шагу 2: имя, фамилия и предметы"
            />


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