import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './RegisterPage.css';

const RegisterPage = () => {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (!firstName.trim() || !lastName.trim()) {
      alert('Имя и фамилия обязательны для заполнения!');
      return;
    }
    setIsLoading(true);
    try {
      // Имитация задержки сети
      await new Promise((resolve) => setTimeout(resolve, 800));

      const email = sessionStorage.getItem('pendingEmail') || '';

      const newUser = {
        email: email,
        firstName: firstName,
        lastName: lastName,
        role: 'Студент'
      };

      const existingUsers = JSON.parse(localStorage.getItem('mock_users') || '[]');
      existingUsers.push(newUser);
      localStorage.setItem('mock_users', JSON.stringify(existingUsers));

      sessionStorage.removeItem('pendingEmail');
      sessionStorage.removeItem('pendingPassword');

      alert(`Аккаунт успешно создан!\nДобро пожаловать, ${firstName}!`);
      navigate('/login');
    } catch (error) {
      console.error('Ошибка при регистрации:', error);
      alert('Ошибка при создании аккаунта. Попробуйте снова.');
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
        <button 
          className="reg-nav-logo-btn" 
          type="button" 
          onClick={() => navigate('/welcome')}
        >
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

        <Link
          to="/main-register"
          className="reg-stripe reg-stripe-left"
          title="Вернуться к шагу 1: почта и пароль"
        />
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