import { create } from 'zustand';

interface AuthState {
  token: string | null;
  isAuthenticated: boolean;
  userName: string | null;
  userRole: string | null;
  
  setToken: (token: string, name?: string, role?: string) => void; // Обновлена сигнатура
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('access_token'),
  isAuthenticated: !!localStorage.getItem('access_token'),
  userName: localStorage.getItem('user_name') || null,
  userRole: localStorage.getItem('user_role') || null,
  
  setToken: (token: string, name?: string, role?: string) => {
    localStorage.setItem('access_token', token);
    
    if (name) localStorage.setItem('user_name', name);
    if (role) localStorage.setItem('user_role', role);
    
    set({ 
      token, 
      isAuthenticated: true, 
      userName: name || localStorage.getItem('user_name'), 
      userRole: role || localStorage.getItem('user_role') 
    });
  },
  
  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_name');
    localStorage.removeItem('user_role');
    set({ 
      token: null, 
      isAuthenticated: false, 
      userName: null, 
      userRole: null 
    });
  },
}));