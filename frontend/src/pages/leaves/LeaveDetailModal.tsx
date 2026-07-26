import { useEffect, useState } from "react";
import { Alert, Descriptions, Modal, Spin, Timeline } from "antd";
import dayjs from "dayjs";

import { getLeaveDetail } from "../../api/leaves";
import { ApiError } from "../../api/client";
import type { LeaveDetailResponse } from "../../types/api";
import { LEAVE_STATUS_MAP, leaveStatusTag, leaveTypeTag } from "../../utils/leave";

interface Props {
  leaveId: string | null;
  onClose: () => void;
}

export default function LeaveDetailModal({ leaveId, onClose }: Props) {
  const [detail, setDetail] = useState<LeaveDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!leaveId) return;
    let cancelled = false;
    setDetail(null);
    setError(null);
    setLoading(true);
    getLeaveDetail(leaveId)
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
  }, [leaveId]);

  return (
    <Modal title="请假详情" open={leaveId !== null} onCancel={onClose} footer={null} destroyOnHidden>
      {loading && <Spin />}
      {error && <Alert type="error" message={error} showIcon />}
      {detail && (
        <>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="类型">{leaveTypeTag(detail.type)}</Descriptions.Item>
            <Descriptions.Item label="日期">{`${detail.start_date} ~ ${detail.end_date}`}</Descriptions.Item>
            <Descriptions.Item label="原因">{detail.reason}</Descriptions.Item>
            <Descriptions.Item label="状态">{leaveStatusTag(detail.status)}</Descriptions.Item>
            <Descriptions.Item label="申请人">{detail.applicant.name}</Descriptions.Item>
            <Descriptions.Item label="审批人">{detail.approver.name}</Descriptions.Item>
            <Descriptions.Item label="创建时间">
              {dayjs(detail.created_at).format("YYYY-MM-DD HH:mm")}
            </Descriptions.Item>
          </Descriptions>
          <Timeline
            style={{ marginTop: 16 }}
            items={detail.history.map((h) => ({
              children: `${LEAVE_STATUS_MAP[h.to_status]?.label ?? h.to_status} · ${h.actor.name} · ${dayjs(
                h.created_at
              ).format("YYYY-MM-DD HH:mm")}${h.comment ? ` — ${h.comment}` : ""}`,
            }))}
          />
        </>
      )}
    </Modal>
  );
}
