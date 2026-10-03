import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import '../pages/MenuPage.css';

const CabinetLayout = () => {
  const logout = useAuthStore((state) => state.logout);

  const userName = useAuthStore((state) => state.userName) || 'Пользователь';
  const userRole = useAuthStore((state) => state.userRole) || 'Студент';
  
  const navigate = useNavigate();

  const getInitials = (name: string | null) => {
    if (!name) return 'П';
    const parts = name.trim().split(' ');
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return name.substring(0, 2).toUpperCase();
  };

  const userInitials = getInitials(userName);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

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
          <h2 className="user-name v15_940">{userName}</h2>
          <p className="user-role v15_939">{userRole}</p>
        </div>

        <nav className="sidebar-menu">
          <NavLink
            to="/menu"
            end
            className={({ isActive }) =>
              `menu-item item-home v15_943${isActive ? ' menu-item-active' : ''}`
            }
          >
            <span className="icon-home" />
            Главная
          </NavLink>
          <NavLink
            to="/courses"
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

                <button className="settings-pill v15_961" type="button">
                    <span className="icon-sun" />
                    Настройки
                </button>
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
      </div>

      <div className="cabinet-outlet">
        <Outlet />
      </div>
    </div>
  );
};

export default CabinetLayout;