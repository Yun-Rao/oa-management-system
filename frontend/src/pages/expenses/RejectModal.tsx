import { useState } from "react";
import { Alert, Form, Input, Modal } from "antd";

import { rejectExpense } from "../../api/expenses";
import { ApiError } from "../../api/client";

interface Props {
  expenseId: string | null;
  onClose: () => void;
  onSuccess: () => void;
}

export default function RejectModal({ expenseId, onClose, onSuccess }: Props) {
  const [form] = Form.useForm<{ reason: string }>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onFinish(values: { reason: string }) {
    if (!expenseId) return;
    setSubmitting(true);
    setError(null);
    try {
      await rejectExpense(expenseId, values.reason);
      onSuccess();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  function handleClose() {
    setError(null);
    onClose();
  }

  return (
    <Modal
      title="驳回申请"
      open={expenseId !== null}
      onCancel={handleClose}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Form form={form} layout="vertical" onFinish={onFinish} preserve={false}>
        <Form.Item
          name="reason"
          label="驳回原因"
          rules={[
            { required: true, message: "请输入驳回原因" },
            { max: 500, message: "最多 500 字" },
          ]}
        >
          <Input.TextArea rows={3} maxLength={500} showCount />
        </Form.Item>
      </Form>
    </Modal>
  );
}
