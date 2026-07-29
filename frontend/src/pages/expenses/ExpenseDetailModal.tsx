import { useEffect, useState } from "react";
import { Alert, App, Button, Descriptions, Modal, Spin, Timeline } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import { downloadAttachment, getExpenseDetail } from "../../api/expenses";
import { ApiError } from "../../api/client";
import type { ExpenseAttachment, ExpenseDetail } from "../../types/api";
import { EXPENSE_STATUS_MAP, expenseStatusTag, expenseTypeTag } from "../../utils/expense";

interface Props {
  expenseId: string | null;
  onClose: () => void;
}

function currentApproval(d: ExpenseDetail): string {
  if (d.status === "pending_l1") return `第 1 级 · ${d.approver?.name ?? "主管"}`;
  if (d.status === "pending_l2") return "第 2 级 · HR/Admin 权限池";
  return "—";
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${bytes}B`;
}

export default function ExpenseDetailModal({ expenseId, onClose }: Props) {
  const { message } = App.useApp();
  const [detail, setDetail] = useState<ExpenseDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!expenseId) return;
    let cancelled = false;
    setDetail(null);
    setError(null);
    setLoading(true);
    getExpenseDetail(expenseId)
      .then((d) => {
        if (!cancelled) setDetail(d);
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
  }, [expenseId]);

  async function onDownload(a: ExpenseAttachment) {
    if (!detail) return;
    try {
      const blob = await downloadAttachment(detail.id, a.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = a.filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    }
  }

  return (
    <Modal title="报销详情" open={expenseId !== null} onCancel={onClose} footer={null} destroyOnHidden>
      {loading && <Spin />}
      {error && <Alert type="error" message={error} showIcon />}
      {detail && (
        <>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="类型">{expenseTypeTag(detail.type)}</Descriptions.Item>
            <Descriptions.Item label="金额">{`¥${detail.amount}`}</Descriptions.Item>
            <Descriptions.Item label="说明">{detail.reason}</Descriptions.Item>
            <Descriptions.Item label="状态">{expenseStatusTag(detail.status)}</Descriptions.Item>
            <Descriptions.Item label="当前审批">{currentApproval(detail)}</Descriptions.Item>
            <Descriptions.Item label="申请人">{detail.applicant.name}</Descriptions.Item>
            <Descriptions.Item label="创建时间">
              {dayjs(detail.created_at).format("YYYY-MM-DD HH:mm")}
            </Descriptions.Item>
            <Descriptions.Item label="附件凭证">
              {detail.attachments.map((a) => (
                <Button
                  key={a.id}
                  type="link"
                  size="small"
                  icon={<DownloadOutlined />}
                  onClick={() => void onDownload(a)}
                >
                  {`${a.filename}(${formatSize(a.size_bytes)})`}
                </Button>
              ))}
            </Descriptions.Item>
          </Descriptions>
          <Timeline
            style={{ marginTop: 16 }}
            items={detail.history.map((h) => ({
              children: `${EXPENSE_STATUS_MAP[h.to_status]?.label ?? h.to_status} · ${h.actor.name} · ${dayjs(
                h.created_at
              ).format("YYYY-MM-DD HH:mm")}${h.comment ? ` — ${h.comment}` : ""}`,
            }))}
          />
        </>
      )}
    </Modal>
  );
}
