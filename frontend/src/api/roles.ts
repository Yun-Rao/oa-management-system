import { client } from "./client";
import type { RoleResponse } from "../types/api";

export async function listRoles(): Promise<RoleResponse[]> {
  const { data } = await client.get<RoleResponse[]>("/roles");
  return data;
}
