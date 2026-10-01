import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { type ReactNode } from 'react';
import { useAuthStore } from './store/authStore';
import MainLayout from './components/MainLayout';

// Импорты страниц
import LoginPage from './pages/LoginPage';
import CoursesPage from './pages/CoursesPage';
import MaterialsPage from './pages/MaterialsPage';
import TestsPage from './pages/TestsPage';
import ResultsPage from './pages/ResultsPage';
import AnalyticsPage from './pages/AnalyticsPage';
import RegisterPage from './pages/RegisterPage';
import MainRegistrationPage from './pages/MainRegistrationPage';

// Компонент для защиты роутов
const ProtectedRoute = ({ children }: { children: ReactNode }) => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Публичный роут */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/main-register" element={<MainRegistrationPage />} />
        <Route path="/register" element={<RegisterPage />} />
        {/* Защищенные роуты внутри общего Layout */}
        <Route element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
          <Route path="/courses" element={<CoursesPage />} />
          <Route path="/courses/:courseId/materials" element={<MaterialsPage />} />
          <Route path="/tests/:testId" element={<TestsPage />} />
          <Route path="/results" element={<ResultsPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/" element={<Navigate to="/courses" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;