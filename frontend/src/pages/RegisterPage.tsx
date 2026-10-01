import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './RegisterPage.css';

const RegisterPage = () => {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [subjects, setSubjects] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      // ЗАГЛУШКА (позже замени на apiClient.post('/auth/register', ...))
      await new Promise((resolve) => setTimeout(resolve, 800));
      console.log('Данные регистрации:', { firstName, lastName, subjects });
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
          <div className="reg-nav-logo-wrap">
            <span className="reg-nav-logo-icon" />
            <span className="reg-nav-logo">ai-помощник</span>
          </div>
          <span className="reg-nav-btn">Регистрация</span>
        </div>
      <div className="reg-top-btn reg-top-info">Информация</div>
      <Link to="/login" className="reg-top-btn reg-top-login">Вход</Link>
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

        <div className="reg-field-group reg-field-3">
          <span className="reg-field-label">Интересующие вас предметы</span>
          <div className="reg-field-box">
            <input
              className="reg-field-input"
              type="text"
              placeholder="Математика, физика..."
              value={subjects}
              onChange={(e) => setSubjects(e.target.value)}
              disabled={isLoading}
            />
          </div>
        </div>

        <button type="submit" className="reg-submit" disabled={isLoading}>
          {isLoading ? 'Создание...' : 'Создать аккаунт'}
        </button>

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