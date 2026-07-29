import { client } from "./client";
import type { DashboardSummary } from "../types/api";

export async function getDashboard(month?: string): Promise<DashboardSummary> {
  const { data } = await client.get<DashboardSummary>("/dashboard", {
    params: month ? { month } : {},
  });
  return data;
}
