import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import '../pages/MenuPage.css';

const CabinetLayout = () => {
  const location = useLocation(); // Хук для отслеживания текущего маршрута
  const logout = useAuthStore((state) => state.logout);
  const firstName = useAuthStore((state) => state.firstName) || 'Пользователь';
  const lastName = useAuthStore((state) => state.lastName) || '';
  const userRole = useAuthStore((state) => state.userRole) || 'Студент';
  
  const navigate = useNavigate();

  const fullName = `${firstName} ${lastName}`.trim();

  const getInitials = (name: string) => {
    if (!name) return 'П';
    const parts = name.trim().split(' ');
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return name.substring(0, 2).toUpperCase();
  };

  const userInitials = getInitials(fullName);

  const handleLogout = async () => {
    try {
      // Ждём, пока бэкенд обработает выход и очистит куки/токены
      await logout(); 
    } catch (error) {
      console.error('Ошибка при выходе:', error);
    } finally {
      // В любом случае перенаправляем на страницу входа
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
        {/* 👇 ЗДЕСЬ ИСПОЛЬЗУЕТСЯ handleLogout */}
        <button className="logout-btn" onClick={handleLogout}>
          Выйти
        </button>
        
        {/* 👇 ЗДЕСЬ ИСПОЛЬЗУЕТСЯ isCoursesPage */}
        {isCoursesPage && (
          <div className="courses-header-box">
            <h1 className="courses-title">Курсы</h1>
            <p className="courses-subtitle">
              Загружайте материалы и готовьтесь к сессии по каждому предмету
            </p>
          </div>
        )}
      </div>

      <div className="cabinet-outlet">
        <Outlet />
      </div>
    </div>
  );
};

export default CabinetLayout;