import { Outlet, Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

const MainLayout = () => {
  const logout = useAuthStore((state) => state.logout);
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="flex h-screen bg-gray-100">
      <aside className="w-64 bg-white shadow-md p-4">
        <h2 className="text-xl font-bold mb-6">AI Exams</h2>
        <nav className="flex flex-col gap-2">
          <Link to="/courses" className="p-2 hover:bg-gray-200 rounded">Курсы</Link>
          <Link to="/results" className="p-2 hover:bg-gray-200 rounded">Результаты</Link>
          <Link to="/analytics" className="p-2 hover:bg-gray-200 rounded">Аналитика</Link>
          <button 
            onClick={handleLogout} 
            className="mt-auto p-2 text-red-500 hover:bg-red-100 rounded"
          >
            Выйти
          </button>
        </nav>
      </aside>

      <main className="flex-1 p-6 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
};

export default MainLayout;