import { client } from "./client";
import type { LeaveDetailResponse, LeaveListResponse, LeaveResponse, LeaveType } from "../types/api";

export async function createLeave(body: {
  type: LeaveType;
  start_date: string;
  end_date: string;
  reason: string;
}): Promise<LeaveResponse> {
  const { data } = await client.post<LeaveResponse>("/leaves", body);
  return data;
}

export async function cancelLeave(id: string): Promise<LeaveResponse> {
  const { data } = await client.post<LeaveResponse>(`/leaves/${id}/cancel`);
  return data;
}

export async function listMine(params: {
  status?: string;
  page: number;
  page_size: number;
}): Promise<LeaveListResponse> {
  const { data } = await client.get<LeaveListResponse>("/leaves/mine", { params });
  return data;
}

export async function listTodo(params: {
  page: number;
  page_size: number;
}): Promise<LeaveListResponse> {
  const { data } = await client.get<LeaveListResponse>("/leaves/todo", { params });
  return data;
}

export async function listAll(params: {
  department_id?: string;
  status?: string;
  type?: string;
  start_from?: string;
  end_to?: string;
  page: number;
  page_size: number;
}): Promise<LeaveListResponse> {
  const { data } = await client.get<LeaveListResponse>("/leaves", { params });
  return data;
}

export async function getLeaveDetail(id: string): Promise<LeaveDetailResponse> {
  const { data } = await client.get<LeaveDetailResponse>(`/leaves/${id}`);
  return data;
}

export async function approveLeave(id: string): Promise<LeaveResponse> {
  const { data } = await client.post<LeaveResponse>(`/leaves/${id}/approve`);
  return data;
}

export async function rejectLeave(id: string, reason: string): Promise<LeaveResponse> {
  const { data } = await client.post<LeaveResponse>(`/leaves/${id}/reject`, { reason });
  return data;
}
