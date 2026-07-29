import { useState } from "react";
import { Card, Tabs } from "antd";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuthStore } from "../../store/auth";
import AllLeavesPanel from "./AllLeavesPanel";
import LeaveDetailModal from "./LeaveDetailModal";
import MyLeavesPanel from "./MyLeavesPanel";
import TodoLeavesPanel from "./TodoLeavesPanel";

export default function LeavesPage() {
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const allowed = hasPermission("leave:list");
  const location = useLocation();
  const navigate = useNavigate();
  const openLeaveId =
    (location.state as { openLeaveId?: string } | null)?.openLeaveId ?? null;

  const tabs = [
    { key: "mine", label: "我的申请", permission: "leave:list", children: <MyLeavesPanel /> },
    { key: "todo", label: "待我审批", permission: "leave:approve", children: <TodoLeavesPanel /> },
    { key: "all", label: "全部记录", permission: "leave:list_all", children: <AllLeavesPanel /> },
  ].filter((t) => hasPermission(t.permission));

  const [activeKey, setActiveKey] = useState<string | null>(null);

  if (!allowed) {
    return <Navigate to="/" replace />;
  }

  return (
    <Card title="请假审批">
      <Tabs
        activeKey={activeKey ?? tabs[0]?.key}
        onChange={setActiveKey}
        items={tabs.map(({ key, label, children }) => ({ key, label, children }))}
      />
      <LeaveDetailModal
        leaveId={openLeaveId}
        onClose={() => navigate(".", { replace: true, state: null })}
      />
    </Card>
  );
}
