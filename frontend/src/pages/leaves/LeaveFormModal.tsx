import { useState } from "react";
import { Alert, DatePicker, Form, Input, Modal, Select } from "antd";
import type { Dayjs } from "dayjs";

import { createLeave } from "../../api/leaves";
import { ApiError } from "../../api/client";
import type { LeaveType } from "../../types/api";
import { LEAVE_TYPE_MAP } from "../../utils/leave";

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

interface LeaveFormValues {
  type: LeaveType;
  range: [Dayjs, Dayjs];
  reason: string;
}

export default function LeaveFormModal({ open, onClose, onSuccess }: Props) {
  const [form] = Form.useForm<LeaveFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onFinish(values: LeaveFormValues) {
    setSubmitting(true);
    setError(null);
    try {
      await createLeave({
        type: values.type,
        start_date: values.range[0].format("YYYY-MM-DD"),
        end_date: values.range[1].format("YYYY-MM-DD"),
        reason: values.reason,
      });
      onSuccess();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      title="新建请假申请"
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Form<LeaveFormValues> form={form} layout="vertical" onFinish={onFinish} preserve={false}>
        <Form.Item name="type" label="请假类型" rules={[{ required: true, message: "请选择请假类型" }]}>
          <Select
            placeholder="请选择"
            options={Object.entries(LEAVE_TYPE_MAP).map(([value, m]) => ({ value, label: m.label }))}
          />
        </Form.Item>
        <Form.Item name="range" label="起止日期" rules={[{ required: true, message: "请选择起止日期" }]}>
          <DatePicker.RangePicker style={{ width: "100%" }} placeholder={["开始日期", "结束日期"]} />
        </Form.Item>
        <Form.Item
          name="reason"
          label="请假原因"
          rules={[
            { required: true, message: "请输入请假原因" },
            { max: 500, message: "最多 500 字" },
          ]}
        >
          <Input.TextArea rows={3} maxLength={500} showCount />
        </Form.Item>
      </Form>
    </Modal>
  );
}
