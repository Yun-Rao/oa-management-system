import { useCallback, useEffect, useState } from "react";
import { Alert, App, Button, Popconfirm, Select, Space, Table } from "antd";

import { cancelExpense, listMine } from "../../api/expenses";
import { ApiError } from "../../api/client";
import type { ExpenseItem } from "../../types/api";
import { EXPENSE_STATUS_MAP, EXPENSE_TYPE_MAP, expenseStatusTag, expenseTypeTag } from "../../utils/expense";
import ExpenseDetailModal from "./ExpenseDetailModal";
import ExpenseFormModal from "./ExpenseFormModal";

const PAGE_SIZE = 20;

export default function MyExpensesPanel() {
  const { message } = App.useApp();
  const [items, setItems] = useState<ExpenseItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string | null>(null);
  const [type, setType] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);

  const fetchList = useCallback(async (p: number, s: string | null, t: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listMine({
        ...(s ? { status: s } : {}),
        ...(t ? { type: t } : {}),
        page: p,
        page_size: PAGE_SIZE,
      });
      setItems(resp.items);
      setTotal(resp.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchList(page, status, type);
  }, [page, status, type, fetchList]);

  async function onCancel(e: ExpenseItem) {
    try {
      await cancelExpense(e.id);
      message.success("已撤回");
      await fetchList(page, status, type);
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : "网络异常,请稍后重试");
      await fetchList(page, status, type);
    }
  }

  const columns = [
    { title: "类型", key: "type", render: (_: unknown, e: ExpenseItem) => expenseTypeTag(e.type) },
    { title: "金额", key: "amount", render: (_: unknown, e: ExpenseItem) => `¥${e.amount}` },
    { title: "说明", dataIndex: "reason", key: "reason" },
    { title: "状态", key: "status", render: (_: unknown, e: ExpenseItem) => expenseStatusTag(e.status) },
    { title: "审批人", key: "approver", render: (_: unknown, e: ExpenseItem) => e.approver?.name ?? "—" },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, e: ExpenseItem) => (
        <Space>
          {(e.status === "pending_l1" || e.status === "pending_l2") && (
            <Popconfirm title="确认撤回该申请?" onConfirm={() => void onCancel(e)}>
              <Button type="link" size="small" danger>
                撤回
              </Button>
            </Popconfirm>
          )}
          <Button type="link" size="small" onClick={() => setDetailId(e.id)}>
            详情
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          placeholder="状态筛选"
          allowClear
          style={{ width: 140 }}
          value={status}
          onChange={(v) => {
            setPage(1);
            setStatus(v ?? null);
          }}
          options={Object.entries(EXPENSE_STATUS_MAP).map(([value, m]) => ({ value, label: m.label }))}
        />
        <Select
          placeholder="类型筛选"
          allowClear
          style={{ width: 120 }}
          value={type}
          onChange={(v) => {
            setPage(1);
            setType(v ?? null);
          }}
          options={Object.entries(EXPENSE_TYPE_MAP).map(([value, m]) => ({ value, label: m.label }))}
        />
        <Button type="primary" onClick={() => setFormOpen(true)}>
          新建报销
        </Button>
      </Space>
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
      <ExpenseFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSuccess={() => {
          message.success("已提交");
          setPage(1);
          setStatus(null);
          setType(null);
          void fetchList(1, null, null);
        }}
      />
      <ExpenseDetailModal expenseId={detailId} onClose={() => setDetailId(null)} />
    </>
  );
}
