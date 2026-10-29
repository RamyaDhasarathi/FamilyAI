import { create } from 'zustand';
import { clearTokens, getAccessToken, saveTokens } from '../api/client';
import { getMeApi, loginApi, logoutApi } from '../api/auth';
import { AuthState, User } from '../types';

interface AuthStore extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  loadStoredAuth: () => Promise<void>;
  setUser: (user: User | null) => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  accessToken: null,
  refreshToken: null,
  isAuthenticated: false,
  isLoading: true,

  login: async (email, password) => {
    const data = await loginApi(email, password);
    await saveTokens(data.access_token, data.refresh_token);
    const user: User = {
      user_id: data.user_id,
      email: email,
      display_name: data.display_name,
      is_active: true,
      family_id: data.family_id,
      membership_id: data.membership_id,
      family_role: data.family_role,
      family_name: data.family_name || 'My Family',
    };
    set({
      user,
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      isAuthenticated: true,
    });
  },

  logout: async () => {
    try {
      await logoutApi();
    } catch {
      // Ignore
    }
    await clearTokens();
    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    });
  },

  loadStoredAuth: async () => {
    try {
      const token = await getAccessToken();
      if (token) {
        const me = await getMeApi();
        set({
          user: me,
          accessToken: token,
          isAuthenticated: true,
          isLoading: false,
        });
      } else {
        set({ isLoading: false });
      }
    } catch {
      await clearTokens();
      set({ user: null, accessToken: null, isAuthenticated: false, isLoading: false });
    }
  },

  setUser: (user) => set({ user }),
}));
