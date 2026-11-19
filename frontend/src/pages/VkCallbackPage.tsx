import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { completeVkLogin } from '../api/vkAuth';
import { useAuthStore } from '../store/authStore'; 

const VkCallbackPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  
  // 👇 ИСПОЛЬЗУЕМ НОВУЮ ФУНКЦИЮ
  const setVkAuth = useAuthStore((state) => state.setVkAuth); 

  const [error, setError] = useState('');

  useEffect(() => {
    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const deviceId = searchParams.get('device_id');
    const vkError = searchParams.get('error');

    if (vkError) {
      setError('Ошибка авторизации VK: ' + vkError);
      setTimeout(() => navigate('/login'), 3000);
      return;
    }

    if (code && state && deviceId) {
      completeVkLogin(code, state, deviceId)
        .then((data) => {
          // 👇 ВЫЗЫВАЕМ setVkAuth с данными от бэкенда
          // Бэкенд ДОЛЖЕН вернуть объект: { accessToken, email, firstName, lastName }
          setVkAuth(data);
          
          navigate('/courses'); // Перенаправляем на главную страницу после успеха
        })
        .catch((err) => {
          console.error('Ошибка обмена кода на токены:', err);
          setError('Не удалось завершить вход. Попробуйте еще раз.');
          setTimeout(() => navigate('/login'), 3000);
        });
    } else {
      setError('Некорректные параметры авторизации.');
      setTimeout(() => navigate('/login'), 3000);
    }
  }, [searchParams, navigate, setVkAuth]);

  if (error) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', flexDirection: 'column' }}>
        <h2 style={{ color: '#e64646', fontFamily: 'Tektur, sans-serif' }}>{error}</h2>
        <p style={{ color: '#707071', fontFamily: 'Tektur, sans-serif' }}>Перенаправление на страницу входа...</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', flexDirection: 'column', fontFamily: 'Tektur, sans-serif' }}>
      <h2>Выполняется вход через VK ID...</h2>
      <p style={{ color: '#707071', marginTop: '10px' }}>Пожалуйста, подождите</p>
    </div>
  );
};

export default VkCallbackPage;