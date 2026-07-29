import { useState } from "react";
import { Card, Tabs } from "antd";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuthStore } from "../../store/auth";
import AllExpensesPanel from "./AllExpensesPanel";
import ExpenseDetailModal from "./ExpenseDetailModal";
import MyExpensesPanel from "./MyExpensesPanel";
import TodoExpensesPanel from "./TodoExpensesPanel";

export default function ExpensesPage() {
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const allowed = hasPermission("expense:list");
  const location = useLocation();
  const navigate = useNavigate();
  const openExpenseId =
    (location.state as { openExpenseId?: string } | null)?.openExpenseId ?? null;

  const tabs = [
    { key: "mine", label: "我的申请", show: hasPermission("expense:list"), children: <MyExpensesPanel /> },
    {
      key: "todo",
      label: "待我审批",
      show: hasPermission("expense:approve") || hasPermission("expense:approve_l2"),
      children: <TodoExpensesPanel />,
    },
    { key: "all", label: "全部记录", show: hasPermission("expense:list_all"), children: <AllExpensesPanel /> },
  ].filter((t) => t.show);

  const [activeKey, setActiveKey] = useState<string | null>(null);

  if (!allowed) {
    return <Navigate to="/" replace />;
  }

  return (
    <Card title="报销审批">
      <Tabs
        activeKey={activeKey ?? tabs[0]?.key}
        onChange={setActiveKey}
        items={tabs.map(({ key, label, children }) => ({ key, label, children }))}
      />
      <ExpenseDetailModal
        expenseId={openExpenseId}
        onClose={() => navigate(".", { replace: true, state: null })}
      />
    </Card>
  );
}
