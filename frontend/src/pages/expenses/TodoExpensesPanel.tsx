import { useCallback, useEffect, useState } from "react";
import { Alert, App, Button, Popconfirm, Space, Table } from "antd";

import { approveExpense, listTodo } from "../../api/expenses";
import { ApiError } from "../../api/client";
import type { ExpenseItem } from "../../types/api";
import { expenseStatusTag, expenseTypeTag } from "../../utils/expense";
import ExpenseDetailModal from "./ExpenseDetailModal";
import RejectModal from "./RejectModal";

const PAGE_SIZE = 20;

export default function TodoExpensesPanel() {
  const { message } = App.useApp();
  const [items, setItems] = useState<ExpenseItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);

  const fetchList = useCallback(async (p: number) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listTodo({ page: p, page_size: PAGE_SIZE });
      setItems(resp.items);
      setTotal(resp.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchList(page);
  }, [page, fetchList]);

  async function onApprove(e: ExpenseItem) {
    try {
      await approveExpense(e.id);
      message.success("已通过");
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : "网络异常,请稍后重试");
    }
    await fetchList(page);
  }

  const columns = [
    { title: "申请人", key: "applicant", render: (_: unknown, e: ExpenseItem) => e.applicant.name },
    { title: "类型", key: "type", render: (_: unknown, e: ExpenseItem) => expenseTypeTag(e.type) },
    { title: "金额", key: "amount", render: (_: unknown, e: ExpenseItem) => `¥${e.amount}` },
    { title: "说明", dataIndex: "reason", key: "reason" },
    { title: "级别", key: "status", render: (_: unknown, e: ExpenseItem) => expenseStatusTag(e.status) },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, e: ExpenseItem) => (
        <Space>
          <Popconfirm title="确认通过该申请?" onConfirm={() => void onApprove(e)}>
            <Button type="link" size="small">
              通过
            </Button>
          </Popconfirm>
          <Button type="link" size="small" danger onClick={() => setRejectingId(e.id)}>
            驳回
          </Button>
          <Button type="link" size="small" onClick={() => setDetailId(e.id)}>
            详情
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Table<ExpenseItem>
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p) => setPage(p),
        }}
      />
      <RejectModal
        expenseId={rejectingId}
        onClose={() => setRejectingId(null)}
        onSuccess={() => {
          message.success("已驳回");
          void fetchList(page);
        }}
      />
      <ExpenseDetailModal expenseId={detailId} onClose={() => setDetailId(null)} />
    </>
  );
}
