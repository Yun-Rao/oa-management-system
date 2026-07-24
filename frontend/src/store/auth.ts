import { create } from "zustand";

import { TOKEN_KEY, onUnauthorized } from "../api/client";
import * as authApi from "../api/auth";
import type { CurrentUser } from "../types/api";

interface AuthState {
  token: string | null;
  user: CurrentUser | null;
  login: (email: string, password: string) => Promise<void>;
  fetchMe: () => Promise<void>;
  logout: () => void;
  hasPermission: (code: string) => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem(TOKEN_KEY),
  user: null,

  async login(email, password) {
    const resp = await authApi.login(email, password);
    localStorage.setItem(TOKEN_KEY, resp.access_token);
    set({ token: resp.access_token });
    await get().fetchMe();
  },

  async fetchMe() {
    const user = await authApi.getMe();
    set({ user });
  },

  logout() {
    localStorage.removeItem(TOKEN_KEY);
    set({ token: null, user: null });
  },

  hasPermission(code) {
    return get().user?.permissions.includes(code) ?? false;
  },
}));

// 401 时清空内存态(client.ts 已负责清 localStorage 与跳转)
onUnauthorized(() => {
  useAuthStore.setState({ token: null, user: null });
});
