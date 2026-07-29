import { useEffect, useState } from "react";
import { Alert, Card, DatePicker, Spin } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { Navigate } from "react-router-dom";

import { getDashboard } from "../../api/dashboard";
import { ApiError } from "../../api/client";
import { useAuthStore } from "../../store/auth";
import type { DashboardSummary } from "../../types/api";
import DurationSection from "./DurationSection";
import ExpenseStatsSection from "./ExpenseStatsSection";
import LeaveStatsSection from "./LeaveStatsSection";

export default function DashboardPage() {
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const allowed = hasPermission("dashboard:view");
  const [month, setMonth] = useState<Dayjs>(() => dayjs());
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getDashboard(month.format("YYYY-MM"))
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [month]);

  if (!allowed) {
    return <Navigate to="/" replace />;
  }

  return (
    <Card
      title="数据看板"
      extra={
        <DatePicker
          picker="month"
          value={month}
          onChange={(v) => {
            if (v) setMonth(v);
          }}
          allowClear={false}
        />
      }
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Spin spinning={loading}>
        {data && (
          <>
            <LeaveStatsSection stats={data.leave_stats} />
            <ExpenseStatsSection stats={data.expense_stats} />
            <DurationSection durations={data.approval_durations} />
          </>
        )}
      </Spin>
    </Card>
  );
}
