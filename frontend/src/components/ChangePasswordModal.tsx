import { useState } from "react";
import { Alert, Form, Input, Modal, message } from "antd";

import { changePassword } from "../api/auth";
import { ApiError } from "../api/client";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface PwdFormValues {
  oldPassword: string;
  newPassword: string;
  confirm: string;
}

export default function ChangePasswordModal({ open, onClose }: Props) {
  const [form] = Form.useForm<PwdFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onFinish(values: PwdFormValues) {
    setSubmitting(true);
    setError(null);
    try {
      await changePassword(values.oldPassword, values.newPassword);
      message.success("密码修改成功");
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      title="修改密码"
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Form<PwdFormValues> form={form} layout="vertical" onFinish={onFinish} preserve={false}>
        <Form.Item name="oldPassword" label="旧密码" rules={[{ required: true, message: "请输入旧密码" }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Form.Item
          name="newPassword"
          label="新密码"
          rules={[
            { required: true, message: "请输入新密码" },
            { min: 8, max: 72, message: "密码长度须为 8-72 位" },
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirm"
          label="确认新密码"
          dependencies={["newPassword"]}
          rules={[
            { required: true, message: "请再次输入新密码" },
            ({ getFieldValue }) => ({
              validator: (_, value: string) =>
                !value || getFieldValue("newPassword") === value
                  ? Promise.resolve()
                  : Promise.reject(new Error("两次输入的密码不一致")),
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
