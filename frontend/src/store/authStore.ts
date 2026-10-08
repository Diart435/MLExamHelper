import { create } from 'zustand';

interface AuthState {
  token: string | null;
  email: string | null;
  firstName: string | null;
  lastName: string | null;
  userRole: string | null;
  isAuthenticated: boolean;
  setToken: (token: string, email: string, firstName: string, lastName: string, role: string) => void;
  updateUser: (firstName?: string, lastName?: string, email?: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  email: null,
  firstName: null,
  lastName: null,
  userRole: null,
  isAuthenticated: false,

  setToken: (token, email, firstName, lastName, role) =>
    set({
      token,
      email,
      firstName,
      lastName,
      userRole: role,
      isAuthenticated: true,
    }),

  updateUser: (newFirstName, newLastName, newEmail) => {
    const state = get();
    set({
      firstName: newFirstName ?? state.firstName,
      lastName: newLastName ?? state.lastName,
      email: newEmail ?? state.email,
    });
  },

  logout: () =>
    set({
      token: null,
      email: null,
      firstName: null,
      lastName: null,
      userRole: null,
      isAuthenticated: false,
    }),
}));