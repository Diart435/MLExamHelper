import { useEffect } from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import '../pages/MenuPage.css';

const CabinetLayout = () => {
  const location = useLocation();
  const checkAuth = useAuthStore((state) => state.checkAuth);
  const logout = useAuthStore((state) => state.logout);
  
  // <-- Читаем флаг инициализации и реальные данные
  const isInitialized = useAuthStore((state) => state.isInitialized);
  const firstName = useAuthStore((state) => state.firstName);
  const lastName = useAuthStore((state) => state.lastName);
  const userRole = useAuthStore((state) => state.userRole) || 'Студент';

  const navigate = useNavigate();

  // <-- Если данные ещё не загрузились, показываем простой лоадер (или верни null)
  if (!isInitialized) {
    return (
      <div className="menu-page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="loading-text">Загрузка профиля...</div>
      </div>
    );
  }

  // <-- Используем реальные данные или фоллбек только ПОСЛЕ инициализации
  const displayName = firstName || 'Пользователь';
  const displayLastName = lastName || '';
  const fullName = `${displayName} ${displayLastName}`.trim();

  const getInitials = (name: string) => {
    if (!name || name === 'Пользователь') return 'П';
    const parts = name.trim().split(' ');
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return name.substring(0, 2).toUpperCase();
  };

  const userInitials = getInitials(displayName);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      console.error('Ошибка при выходе:', error);
    } finally {
      navigate('/login');
    }
  };

  const isCoursesPage = location.pathname === '/courses';

  return (
    <div className="menu-page">
      <div className="bg-circles-pattern" />

      <aside className="sidebar-column v15_914">
        <div className="sidebar-header v15_916">
          <div className="logo-wrapper">
            <div className="ai-white-area">
              <div className="bump purple top-left" />
              <div className="bump green top-right" />

              <button className="ai-pill" type="button">
                <span className="ai-icon" />
                <span className="ai-text">ai-помощник</span>
              </button>

              <div className="bump purple bottom-left" />
              <div className="bump green bottom-right" />
            </div>
          </div>
        </div>

        <div className="user-profile-block v15_934">
          <div className="avatar-bg-circle" />
          <div className="avatar-circle v15_935">{userInitials}</div>
          <h2 className="user-name v15_940">{fullName}</h2>
          <p className="user-role v15_939">{userRole}</p>
        </div>

        <nav className="sidebar-menu">
          <NavLink
            to="/courses"
            end
            className={({ isActive }) =>
              `menu-item item-home v15_943${isActive ? ' menu-item-active' : ''}`
            }
          >
            <span className="icon-home" />
            Курсы
          </NavLink>
          <NavLink
            to="/menu"
            className={({ isActive }) =>
              `menu-item item-materials v15_944${isActive ? ' menu-item-active' : ''}`
            }
          >
            <span className="icon-notebook" />
            Материалы
          </NavLink>
          <NavLink
            to="/results"
            className={({ isActive }) =>
              `menu-item item-tests v15_945${isActive ? ' menu-item-active' : ''}`
            }
          >
            <span className="icon-copy" />
            Мои тесты
          </NavLink>
          <NavLink
            to="/analytics"
            className={({ isActive }) =>
              `menu-item item-progress v15_946${isActive ? ' menu-item-active' : ''}`
            }
          >
            <span className="icon-bookmark" />
            Мой прогресс
          </NavLink>
        </nav>

        <div className="settings-block v15_959">
          <div className="settings-wrapper">
            <div className="settings-white-area">
              <div className="bump green top-left" />
              <div className="bump green top-right" />

              <NavLink
                to="/menu/settings"
                className={({ isActive }) =>
                  `settings-pill v15_961${isActive ? ' menu-item-active' : ''}`
                }
              >
                <span className="icon-sun" />
                Настройки
              </NavLink>

              <div className="bump green bottom-left" />
              <div className="bump green bottom-right" />
            </div>
          </div>
        </div>
      </aside>

      <div className="main-content-area v15_913">
        <button className="logout-btn" onClick={handleLogout}>
          Выйти
        </button>

        {isCoursesPage && (
          <div className="courses-header-box">
            <h1 className="courses-title">Курсы</h1>
            <p className="courses-subtitle">
              Загружайте материалы и готовьтесь к сессии по каждому предмету
            </p>
          </div>
        )}
      </div>

      <div className={`cabinet-outlet${isCoursesPage ? ' cabinet-outlet--courses' : ''}`}>
        <Outlet />
      </div>
    </div>
  );
};

export default CabinetLayout;