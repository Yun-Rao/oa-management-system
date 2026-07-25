import { client } from "./client";
import type { DepartmentNode, DepartmentResponse, UserListResponse } from "../types/api";

export async function listDeptTree(): Promise<DepartmentNode[]> {
  const { data } = await client.get<DepartmentNode[]>("/departments");
  return data;
}

export async function createDepartment(body: {
  name: string;
  parent_id?: string | null;
}): Promise<DepartmentResponse> {
  const { data } = await client.post<DepartmentResponse>("/departments", body);
  return data;
}

export async function updateDepartment(
  id: string,
  body: { name?: string; parent_id?: string | null }
): Promise<DepartmentResponse> {
  const { data } = await client.patch<DepartmentResponse>(`/departments/${id}`, body);
  return data;
}

export async function deleteDepartment(id: string): Promise<void> {
  await client.delete(`/departments/${id}`);
}

export async function listDeptMembers(
  id: string,
  params: { page: number; page_size: number }
): Promise<UserListResponse> {
  const { data } = await client.get<UserListResponse>(`/departments/${id}/members`, { params });
  return data;
}
