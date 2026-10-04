import { Link } from 'react-router-dom';
import './WelcomePage.css';

import pattern from './assets/pattern.png';
import clipGreen from './assets/icon-clip-green.png';
import planetGreen from './assets/icon-planet-green.png';
import clipBlack from './assets/icon-clip-black.png';
import planetPurple from './assets/icon-planet-purple.png';
import hatPurple from './assets/icon-hat-purple.png';

const WelcomePage = () => {
  return (
    <div className="welcome-page">

              {/* ===== НАВБАР ===== */}
        <div className="nav-container">
          <div className="nav-green" />
          <div className="nav-black">

            <Link to="/welcome" className="nav-logo-btn">
              <span className="nav-logo-icon" />
              <span className="nav-logo">ai-помощник</span>
            </Link>

            <div className="nav-buttons">
              <Link to="/login" className="nav-btn">Вход</Link>
              <Link to="/main-register" className="nav-btn">Регистрация</Link>
            </div>

          </div>
        </div>
      {/* ===== ОСНОВНОЙ КОНТЕНТ ===== */}
      <div className="content">

        <img src={pattern} alt="" className="pattern pattern-right" />
        <img src={pattern} alt="" className="pattern pattern-left" />

        <img src={clipGreen}    alt="" className="icon icon-clip-green" />
        <img src={planetGreen}  alt="" className="icon icon-planet-green" />
        <img src={clipBlack}    alt="" className="icon icon-clip-black" />
        <img src={planetPurple} alt="" className="icon icon-planet-purple" />
        <img src={hatPurple}    alt="" className="icon icon-hat-purple" />

        <div className="text-content">
          <h1 className="main-title">
            АССИСТЕНТ
            <br />
            ДЛЯ УЧЁБЫ
          </h1>
          <p className="description">
            Сайт для подготовки к экзаменам с помощью ИИ-помощника — это
            образовательная платформа, которая помогает студенту эффективно
            изучать учебные материалы. Пользователь может загружать лекции,
            презентации и методички, а ИИ анализирует их и составляет
            персональный план подготовки. ИИ-помощник отвечает на вопросы,
            объясняет сложные темы и создаёт тесты и практические задания.
            Система позволяет отслеживать прогресс и выявлять темы, которым
            требуется дополнительное внимание.
          </p>
        </div>
      </div>
    </div>
  );
};

export default WelcomePage;