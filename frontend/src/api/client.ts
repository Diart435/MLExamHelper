import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Список эндпоинтов, для которых НЕ нужно делать авто-refresh
const AUTH_ENDPOINTS = [
  '/api/auth/login',
  '/api/auth/register',
  '/api/auth/refresh',
  '/api/auth/logout',
];

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('accessToken');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Проверяем, является ли это auth-эндпоинтом
    const isAuthEndpoint = AUTH_ENDPOINTS.some((endpoint) =>
      originalRequest.url?.includes(endpoint)
    );

    // Делаем refresh ТОЛЬКО если это 401, запрос не повторялся, И это НЕ auth-эндпоинт
    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !isAuthEndpoint 
    ) {
      originalRequest._retry = true;

      try {
        const response = await axios.post(
          `${API_BASE_URL}/api/auth/refresh`,
          {},
          { withCredentials: true }
        );

        const newAccessToken = response.data.accessToken;
        localStorage.setItem('accessToken', newAccessToken);

        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        localStorage.removeItem('accessToken');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    // Для auth-эндпоинтов (например, неверный пароль при логине) 
    // просто пробрасываем ошибку дальше, чтобы её обработал компонент LoginPage
    return Promise.reject(error);
  }
);

export default apiClient;