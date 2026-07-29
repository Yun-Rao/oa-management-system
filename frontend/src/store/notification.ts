import { create } from "zustand";

import { getUnreadCount } from "../api/notifications";

interface NotificationState {
  unreadCount: number;
  refresh: () => Promise<void>;
  decrement: (n: number) => void;
  clear: () => void;
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  unreadCount: 0,

  async refresh() {
    try {
      const count = await getUnreadCount();
      set({ unreadCount: count });
    } catch {
      // 轮询失败静默,下轮重试
    }
  },

  decrement(n) {
    set({ unreadCount: Math.max(0, get().unreadCount - n) });
  },

  clear() {
    set({ unreadCount: 0 });
  },
}));
