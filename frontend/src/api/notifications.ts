import { client } from "./client";
import type { NotificationItem, NotificationListResponse } from "../types/api";

export async function listNotifications(params: {
  is_read?: boolean;
  page: number;
  page_size: number;
}): Promise<NotificationListResponse> {
  const { data } = await client.get<NotificationListResponse>("/notifications", { params });
  return data;
}

export async function getUnreadCount(): Promise<number> {
  const { data } = await client.get<{ count: number }>("/notifications/unread-count");
  return data.count;
}

export async function markRead(id: string): Promise<NotificationItem> {
  const { data } = await client.post<NotificationItem>(`/notifications/${id}/read`);
  return data;
}

export async function markAllRead(): Promise<number> {
  const { data } = await client.post<{ updated: number }>("/notifications/read-all");
  return data.updated;
}
