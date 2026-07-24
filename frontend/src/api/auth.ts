import { client } from "./client";
import type { CurrentUser, LoginResponse } from "../types/api";

export async function login(email: string, password: string): Promise<LoginResponse> {
  const { data } = await client.post<LoginResponse>("/auth/login", { email, password });
  return data;
}

export async function getMe(): Promise<CurrentUser> {
  const { data } = await client.get<CurrentUser>("/auth/me");
  return data;
}
