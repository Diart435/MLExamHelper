import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { completeVkLogin } from '../api/vkAuth';
import { useAuthStore } from '../store/authStore'; 

const VkCallbackPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const setVkAuth = useAuthStore((state) => state.setVkAuth); 
  const [error, setError] = useState('');
  if (error) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', flexDirection: 'column' }}>
        <h2 style={{ color: '#e64646' }}>{error}</h2>
        <p>Перенаправление на страницу входа...</p>
      </div>
    );
  }
  useEffect(() => {
    // 1. БЕРЕМ ДАННЫЕ ИЗ URL (после редиректа от VK)
    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const deviceId = searchParams.get('device_id');

    if (code && state && deviceId) {
      // 2. ОТПРАВЛЯЕМ ИХ НА БЭКЕНД (POST на /api/auth/vk/callback)
      completeVkLogin(code, state, deviceId)
        .then((data) => {
          // 3. СОХРАНЯЕМ ТОКЕН И ДАННЫЕ ПОЛЬЗОВАТЕЛЯ
          setVkAuth(data);
          
          // 4. ДЕЛАЕМ РЕДИРЕКТ ВНУТРИ ПРИЛОЖЕНИЯ (пользователь не виснет!)
          navigate('/courses'); 
        })
        .catch((err) => {
          console.error('Ошибка обмена кода на токены:', err);
          setError('Не удалось завершить вход.');
          setTimeout(() => navigate('/login'), 3000);
        });
    }
  }, [searchParams, navigate, setVkAuth]);

  // Пока идет запрос, показываем лоадер
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <h2>Выполняется вход через VK ID...</h2>
    </div>
  );
};

export default VkCallbackPage;