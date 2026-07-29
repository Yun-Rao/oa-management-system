import { Tag } from "antd";

export const EXPENSE_TYPE_MAP: Record<string, { label: string; color: string }> = {
  travel: { label: "差旅", color: "blue" },
  office: { label: "办公", color: "green" },
  entertainment: { label: "招待", color: "orange" },
  transport: { label: "交通", color: "purple" },
  other: { label: "其他", color: "default" },
};

export const EXPENSE_STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending_l1: { label: "待主管审批", color: "gold" },
  pending_l2: { label: "待二级审批", color: "volcano" },
  approved: { label: "已通过", color: "green" },
  rejected: { label: "已驳回", color: "red" },
  cancelled: { label: "已撤回", color: "default" },
};

export function expenseTypeTag(type: string) {
  const m = EXPENSE_TYPE_MAP[type] ?? { label: type, color: "default" };
  return <Tag color={m.color}>{m.label}</Tag>;
}

export function expenseStatusTag(status: string) {
  const m = EXPENSE_STATUS_MAP[status] ?? { label: status, color: "default" };
  return <Tag color={m.color}>{m.label}</Tag>;
}
