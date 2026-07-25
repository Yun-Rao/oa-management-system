import { client } from "./client";
import type { UserListResponse, UserResponse } from "../types/api";

export interface ListUsersParams {
  page: number;
  page_size: number;
  keyword?: string;
}

export async function listUsers(params: ListUsersParams): Promise<UserListResponse> {
  const { page, page_size, keyword } = params;
  const { data } = await client.get<UserListResponse>("/users", {
    params: keyword ? { page, page_size, keyword } : { page, page_size },
  });
  return data;
}

export async function createUser(body: {
  email: string;
  name: string;
  password: string;
}): Promise<UserResponse> {
  const { data } = await client.post<UserResponse>("/users", body);
  return data;
}

export async function updateUser(
  id: string,
  body: { email?: string; name?: string }
): Promise<UserResponse> {
  const { data } = await client.patch<UserResponse>(`/users/${id}`, body);
  return data;
}

export async function setUserStatus(id: string, isActive: boolean): Promise<UserResponse> {
  const { data } = await client.patch<UserResponse>(`/users/${id}/status`, {
    is_active: isActive,
  });
  return data;
}

export async function assignRoles(id: string, roleCodes: string[]): Promise<UserResponse> {
  const { data } = await client.put<UserResponse>(`/users/${id}/roles`, {
    role_codes: roleCodes,
  });
  return data;
}
