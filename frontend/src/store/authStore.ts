import { create } from 'zustand';
import { login as apiLogin, register as apiRegister, logout as apiLogout } from '../api/auth';
import { getMe as apiGetMe } from '../api/user';

interface AuthState {
  token: string | null;
  email: string | null;
  firstName: string | null;
  lastName: string | null;
  userRole: string | null;
  isAuthenticated: boolean;
  isInitialized: boolean; // <-- 1. Добавили это поле
  
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, firstName: string, lastName: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  updateUser: (firstName: string, lastName: string, email: string) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('accessToken'),
  email: null,
  firstName: null,
  lastName: null,
  userRole: 'Студент',
  isAuthenticated: !!localStorage.getItem('accessToken'),
  isInitialized: false, // <-- 2. Изначально false

  login: async (email: string, password: string) => {
    const response = await apiLogin({ email, password });
    localStorage.setItem('accessToken', response.accessToken);
    set({
      token: response.accessToken,
      email: response.email,
      firstName: response.firstName,
      lastName: response.lastName,
      isAuthenticated: true,
      isInitialized: true, // <-- 3. После входа инициализация завершена
    });
  },

  register: async (email: string, password: string, firstName: string, lastName: string) => {
    const response = await apiRegister({ email, password, firstName, lastName });
    localStorage.setItem('accessToken', response.accessToken);
    set({
      token: response.accessToken,
      email: response.email,
      firstName: response.firstName,
      lastName: response.lastName,
      isAuthenticated: true,
      isInitialized: true, // <-- 3. После регистрации инициализация завершена
    });
  },

  logout: async () => {
    try {
      await apiLogout();
    } catch (error) {
      console.error('Ошибка при выходе:', error);
    } finally {
      localStorage.removeItem('accessToken');
      set({ 
        token: null, 
        email: null, 
        firstName: null, 
        lastName: null, 
        userRole: null, 
        isAuthenticated: false,
        isInitialized: true // <-- 3. После выхода инициализация завершена
      });
    }
  },

  checkAuth: async () => {
    const token = localStorage.getItem('accessToken');
    
    // Если токена нет, сразу завершаем инициализацию
    if (!token) {
      set({ isAuthenticated: false, isInitialized: true }); // <-- 4. ВАЖНО: ставим true
      return;
    }
    
    try {
      const user = await apiGetMe();
      set({ 
        email: user.email, 
        firstName: user.firstName, 
        lastName: user.lastName, 
        isAuthenticated: true,
        isInitialized: true // <-- 4. ВАЖНО: ставим true при успехе
      });
    } catch (error) {
      console.error('checkAuth: ошибка при проверке токена', error);
      localStorage.removeItem('accessToken');
      set({ 
        isAuthenticated: false, 
        firstName: null, 
        lastName: null, 
        email: null,
        isInitialized: true // <-- 4. ВАЖНО: ставим true даже при ошибке, чтобы убрать лоадер
      });
    }
  },

  updateUser: (firstName: string, lastName: string, email: string) => {
    set({ firstName, lastName, email });
  },
}));