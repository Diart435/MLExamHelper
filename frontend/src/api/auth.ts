import apiClient from './client';

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  firstName: string;
  lastName: string;
}

export interface AuthResponse {
  userId: string;
  email: string;
  firstName: string;
  lastName: string;
  accessToken: string;
}

// Вход в систему
export const login = async (data: LoginRequest): Promise<AuthResponse> => {
  const response = await apiClient.post<AuthResponse>('/api/auth/login', data);
  return response.data;
};

// Регистрация
export const register = async (data: RegisterRequest): Promise<AuthResponse> => {
  const response = await apiClient.post<AuthResponse>('/api/auth/register', data);
  return response.data;
};

// Обновление токена
export const refresh = async (): Promise<{ accessToken: string }> => {
  const response = await apiClient.post<{ accessToken: string }>('/api/auth/refresh');
  return response.data;
};

// Выход из системы
export const logout = async (): Promise<void> => {
  try {
    await apiClient.post('/api/auth/logout');
  } catch (error) {
    console.error('Ошибка при запросе на выход:', error);
  } finally {
    localStorage.removeItem('accessToken');
  }
};