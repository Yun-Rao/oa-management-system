import { useCallback, useEffect, useState } from "react";
import { Alert, App, Button, Popconfirm, Select, Space, Table } from "antd";

import { cancelLeave, listMine } from "../../api/leaves";
import { ApiError } from "../../api/client";
import type { LeaveResponse } from "../../types/api";
import { LEAVE_STATUS_MAP, leaveStatusTag, leaveTypeTag } from "../../utils/leave";
import LeaveDetailModal from "./LeaveDetailModal";
import LeaveFormModal from "./LeaveFormModal";

const PAGE_SIZE = 20;

export default function MyLeavesPanel() {
  const { message } = App.useApp();
  const [items, setItems] = useState<LeaveResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);

  const fetchList = useCallback(async (p: number, s: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listMine({ ...(s ? { status: s } : {}), page: p, page_size: PAGE_SIZE });
      setItems(resp.items);
      setTotal(resp.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listMine({ ...(status ? { status } : {}), page, page_size: PAGE_SIZE })
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
  }, [page, status]);

  async function onCancel(l: LeaveResponse) {
    try {
      await cancelLeave(l.id);
      message.success("已撤回");
      await fetchList(page, status);
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    }
  }

  const columns = [
    { title: "类型", key: "type", render: (_: unknown, l: LeaveResponse) => leaveTypeTag(l.type) },
    { title: "日期", key: "date", render: (_: unknown, l: LeaveResponse) => `${l.start_date} ~ ${l.end_date}` },
    { title: "原因", dataIndex: "reason", key: "reason" },
    { title: "状态", key: "status", render: (_: unknown, l: LeaveResponse) => leaveStatusTag(l.status) },
    { title: "审批人", key: "approver", render: (_: unknown, l: LeaveResponse) => l.approver.name },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, l: LeaveResponse) => (
        <Space>
          {l.status === "pending" && (
            <Popconfirm title="确认撤回该申请?" onConfirm={() => void onCancel(l)}>
              <Button type="link" size="small" danger>
                撤回
              </Button>
            </Popconfirm>
          )}
          <Button type="link" size="small" onClick={() => setDetailId(l.id)}>
            详情
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Select
          placeholder="状态筛选"
          allowClear
          style={{ width: 140 }}
          value={status}
          onChange={(v) => {
            setPage(1);
            setStatus(v ?? null);
          }}
          options={Object.entries(LEAVE_STATUS_MAP).map(([value, m]) => ({ value, label: m.label }))}
        />
        <Button type="primary" onClick={() => setFormOpen(true)}>
          新建申请
        </Button>
      </Space>
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Table<LeaveResponse>
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
      <LeaveFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSuccess={() => {
          message.success("已提交");
          setPage(1);
          setStatus(null);
          void fetchList(1, null);
        }}
      />
      <LeaveDetailModal leaveId={detailId} onClose={() => setDetailId(null)} />
    </>
  );
}
