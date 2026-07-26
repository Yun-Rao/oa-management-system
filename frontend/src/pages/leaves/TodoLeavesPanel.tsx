import { useEffect, useState } from "react";
import { Alert, App, Button, Popconfirm, Space, Table } from "antd";

import { approveLeave, listTodo } from "../../api/leaves";
import { ApiError } from "../../api/client";
import type { LeaveResponse } from "../../types/api";
import { leaveTypeTag } from "../../utils/leave";
import LeaveDetailModal from "./LeaveDetailModal";
import RejectModal from "./RejectModal";

const PAGE_SIZE = 20;

export default function TodoLeavesPanel() {
  const { message } = App.useApp();
  const [items, setItems] = useState<LeaveResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);

  function fetchList(p: number) {
    setLoading(true);
    setError(null);
    return listTodo({ page: p, page_size: PAGE_SIZE })
      .then((resp) => {
        setItems(resp.items);
        setTotal(resp.total);
      })
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listTodo({ page, page_size: PAGE_SIZE })
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
  }, [page]);

  function errText(e: unknown) {
    return e instanceof ApiError ? e.message : "网络异常,请稍后重试";
  }

  async function onApprove(l: LeaveResponse) {
    try {
      await approveLeave(l.id);
      message.success("已通过");
      await fetchList(page);
    } catch (e) {
      message.error(errText(e));
      await fetchList(page);
    }
  }

  const columns = [
    { title: "申请人", key: "applicant", render: (_: unknown, l: LeaveResponse) => l.applicant.name },
    { title: "类型", key: "type", render: (_: unknown, l: LeaveResponse) => leaveTypeTag(l.type) },
    { title: "日期", key: "date", render: (_: unknown, l: LeaveResponse) => `${l.start_date} ~ ${l.end_date}` },
    { title: "原因", dataIndex: "reason", key: "reason" },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, l: LeaveResponse) => (
        <Space>
          <Popconfirm title="确认通过该申请?" onConfirm={() => void onApprove(l)}>
            <Button type="link" size="small">
              通过
            </Button>
          </Popconfirm>
          <Button type="link" size="small" danger onClick={() => setRejectingId(l.id)}>
            驳回
          </Button>
          <Button type="link" size="small" onClick={() => setDetailId(l.id)}>
            详情
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
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
      <RejectModal
        leaveId={rejectingId}
        onClose={() => setRejectingId(null)}
        onSuccess={() => {
          message.success("已驳回");
          void fetchList(page);
        }}
      />
      <LeaveDetailModal leaveId={detailId} onClose={() => setDetailId(null)} />
    </>
  );
}
