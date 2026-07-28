import { Tag } from "antd";

export const LEAVE_TYPE_MAP: Record<string, { label: string; color: string }> = {
  personal: { label: "事假", color: "blue" },
  sick: { label: "病假", color: "orange" },
  annual: { label: "年假", color: "green" },
  compensatory: { label: "调休", color: "purple" },
};

export const LEAVE_STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: "待审批", color: "gold" },
  approved: { label: "已通过", color: "green" },
  rejected: { label: "已驳回", color: "red" },
  canceled: { label: "已撤回", color: "default" },
};

export function leaveTypeTag(type: string) {
  const m = LEAVE_TYPE_MAP[type] ?? { label: type, color: "default" };
  return <Tag color={m.color}>{m.label}</Tag>;
}

export function leaveStatusTag(status: string) {
  const m = LEAVE_STATUS_MAP[status] ?? { label: status, color: "default" };
  return <Tag color={m.color}>{m.label}</Tag>;
}
