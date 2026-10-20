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
  
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, firstName: string, lastName: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  updateUser: (firstName: string, lastName: string, email: string) => void; // ← Новое
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('accessToken'),
  email: null,
  firstName: null,
  lastName: null,
  userRole: 'Студент',
  isAuthenticated: !!localStorage.getItem('accessToken'),

  login: async (email: string, password: string) => {
    const response = await apiLogin({ email, password });
    localStorage.setItem('accessToken', response.accessToken);
    set({
      token: response.accessToken,
      email: response.email,
      firstName: response.firstName,
      lastName: response.lastName,
      isAuthenticated: true,
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
    });
  },

  logout: async () => {
    try {
      await apiLogout();
    } catch (error) {
      console.error('Ошибка при выходе:', error);
    } finally {
      localStorage.removeItem('accessToken');
      set({ token: null, email: null, firstName: null, lastName: null, userRole: null, isAuthenticated: false });
    }
  },

  checkAuth: async () => {
    const token = localStorage.getItem('accessToken');
    if (!token) {
      set({ isAuthenticated: false });
      return;
    }
    try {
      const user = await apiGetMe();
      set({ email: user.email, firstName: user.firstName, lastName: user.lastName, isAuthenticated: true });
    } catch (error) {
      localStorage.removeItem('accessToken');
      set({ isAuthenticated: false });
    }
  },

  updateUser: (firstName: string, lastName: string, email: string) => {
    set({ firstName, lastName, email });
  },
}));