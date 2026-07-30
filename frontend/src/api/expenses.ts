import { client } from "./client";
import type { ExpenseDetail, ExpenseItem, ExpenseListResponse } from "../types/api";

export async function createExpense(form: FormData): Promise<ExpenseItem> {
  const { data } = await client.post<ExpenseItem>("/expenses", form);
  return data;
}

export async function listMine(params: {
  status?: string;
  type?: string;
  page: number;
  page_size: number;
}): Promise<ExpenseListResponse> {
  const { data } = await client.get<ExpenseListResponse>("/expenses/mine", { params });
  return data;
}

export async function listTodo(params: {
  page: number;
  page_size: number;
}): Promise<ExpenseListResponse> {
  const { data } = await client.get<ExpenseListResponse>("/expenses/todo", { params });
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
}): Promise<ExpenseListResponse> {
  const { data } = await client.get<ExpenseListResponse>("/expenses", { params });
  return data;
}

export async function getExpenseDetail(id: string): Promise<ExpenseDetail> {
  const { data } = await client.get<ExpenseDetail>(`/expenses/${id}`);
  return data;
}

export async function downloadAttachment(expenseId: string, attachmentId: string): Promise<Blob> {
  const { data } = await client.get<Blob>(`/expenses/${expenseId}/attachments/${attachmentId}`, {
    responseType: "blob",
  });
  return data;
}

export async function cancelExpense(id: string): Promise<ExpenseItem> {
  const { data } = await client.post<ExpenseItem>(`/expenses/${id}/cancel`);
  return data;
}

export async function approveExpense(id: string): Promise<ExpenseItem> {
  const { data } = await client.post<ExpenseItem>(`/expenses/${id}/approve`);
  return data;
}

export async function rejectExpense(id: string, reason: string): Promise<ExpenseItem> {
  const { data } = await client.post<ExpenseItem>(`/expenses/${id}/reject`, { reason });
  return data;
}
