import { useEffect, useState } from "react";
import { Alert, Button, DatePicker, Select, Space, Table, TreeSelect } from "antd";
import type { Dayjs } from "dayjs";

import { listAll } from "../../api/expenses";
import { listDeptTree } from "../../api/departments";
import { ApiError } from "../../api/client";
import type { DepartmentNode, ExpenseItem } from "../../types/api";
import { toTreeSelectData } from "../../utils/deptTree";
import { EXPENSE_STATUS_MAP, EXPENSE_TYPE_MAP, expenseStatusTag, expenseTypeTag } from "../../utils/expense";
import ExpenseDetailModal from "./ExpenseDetailModal";

const PAGE_SIZE = 20;

interface Filters {
  department_id: string | null;
  status: string | null;
  type: string | null;
  range: [Dayjs, Dayjs] | null;
}

export default function AllExpensesPanel() {
  const [items, setItems] = useState<ExpenseItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<Filters>({ department_id: null, status: null, type: null, range: null });
  const [tree, setTree] = useState<DepartmentNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listDeptTree()
      .then((d) => {
        if (!cancelled) setTree(d);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listAll({
      ...(filters.department_id ? { department_id: filters.department_id } : {}),
      ...(filters.status ? { status: filters.status } : {}),
      ...(filters.type ? { type: filters.type } : {}),
      ...(filters.range
        ? {
            start_from: filters.range[0].format("YYYY-MM-DD"),
            end_to: filters.range[1].format("YYYY-MM-DD"),
          }
        : {}),
      page,
      page_size: PAGE_SIZE,
    })
      .then((resp) => {
        if (cancelled) return;
        setItems(resp.items);
        setTotal(resp.total);
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
  }, [page, filters]);

  function patch(p: Partial<Filters>) {
    setPage(1);
    setFilters((prev) => ({ ...prev, ...p }));
  }

  const columns = [
    { title: "申请人", key: "applicant", render: (_: unknown, e: ExpenseItem) => e.applicant.name },
    { title: "类型", key: "type", render: (_: unknown, e: ExpenseItem) => expenseTypeTag(e.type) },
    { title: "金额", key: "amount", render: (_: unknown, e: ExpenseItem) => `¥${e.amount}` },
    { title: "说明", dataIndex: "reason", key: "reason" },
    { title: "状态", key: "status", render: (_: unknown, e: ExpenseItem) => expenseStatusTag(e.status) },
    { title: "审批人", key: "approver", render: (_: unknown, e: ExpenseItem) => e.approver?.name ?? "—" },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, e: ExpenseItem) => (
        <Button type="link" size="small" onClick={() => setDetailId(e.id)}>
          详情
        </Button>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }} wrap>
        <TreeSelect
          placeholder="部门"
          allowClear
          style={{ width: 180 }}
          treeData={toTreeSelectData(tree)}
          treeDefaultExpandAll
          value={filters.department_id ?? undefined}
          onChange={(v) => patch({ department_id: (v as string) ?? null })}
        />
        <Select
          placeholder="状态"
          allowClear
          style={{ width: 140 }}
          value={filters.status ?? undefined}
          onChange={(v) => patch({ status: v ?? null })}
          options={Object.entries(EXPENSE_STATUS_MAP).map(([value, m]) => ({ value, label: m.label }))}
        />
        <Select
          placeholder="类型"
          allowClear
          style={{ width: 120 }}
          value={filters.type ?? undefined}
          onChange={(v) => patch({ type: v ?? null })}
          options={Object.entries(EXPENSE_TYPE_MAP).map(([value, m]) => ({ value, label: m.label }))}
        />
        <DatePicker.RangePicker
          placeholder={["开始日期", "结束日期"]}
          value={filters.range}
          onChange={(v) => patch({ range: v as [Dayjs, Dayjs] | null })}
        />
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
      <ExpenseDetailModal expenseId={detailId} onClose={() => setDetailId(null)} />
    </>
  );
}
