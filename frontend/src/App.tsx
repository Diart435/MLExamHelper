import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { type ReactNode } from 'react';
import { useAuthStore } from './store/authStore';
import CabinetLayout from './components/CabinetLayout';

import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import MainRegistrationPage from './pages/MainRegistrationPage';
import MainPage from './pages/MainPage';
import CoursesPage from './pages/CoursesPage';
import MaterialsPage from './pages/MaterialsPage';
import TestsPage from './pages/TestsPage';
import ResultsPage from './pages/ResultsPage';
import AnalyticsPage from './pages/AnalyticsPage';
import WelcomePage from './pages/WelcomePage';

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
        <Route path="/login" element={<LoginPage />} />
        <Route path="/main-register" element={<MainRegistrationPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/welcome" element={<WelcomePage/>}/>

        <Route element={<ProtectedRoute><CabinetLayout /></ProtectedRoute>}>
          <Route path="/menu" element={<MainPage />} />
          <Route path="/courses" element={<CoursesPage />} />
          <Route path="/courses/:courseId/materials" element={<MaterialsPage />} />
          <Route path="/tests/:testId" element={<TestsPage />} />
          <Route path="/results" element={<ResultsPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
        </Route>

        <Route path="/" element={<Navigate to="/menu" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;