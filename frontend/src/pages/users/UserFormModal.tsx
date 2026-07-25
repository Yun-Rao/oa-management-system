import { useEffect, useState } from "react";
import { Alert, Form, Input, Modal } from "antd";

import { ApiError } from "../../api/client";
import { createUser, updateUser } from "../../api/users";
import type { UserResponse } from "../../types/api";

interface Props {
  open: boolean;
  editing: UserResponse | null;
  onClose: () => void;
  onSuccess: () => void;
}

interface UserFormValues {
  email: string;
  name: string;
  password?: string;
}

export default function UserFormModal({ open, editing, onClose, onSuccess }: Props) {
  const [form] = Form.useForm<UserFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setError(null);
    }
  }, [open]);

  async function onFinish(values: UserFormValues) {
    setSubmitting(true);
    setError(null);
    try {
      if (editing) {
        await updateUser(editing.id, { email: values.email, name: values.name });
      } else {
        await createUser({ email: values.email, name: values.name, password: values.password! });
      }
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
      title={editing ? "编辑用户" : "新建用户"}
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Form<UserFormValues>
        key={editing ? editing.id : "new"}
        form={form}
        layout="vertical"
        onFinish={onFinish}
        preserve={false}
        initialValues={editing ? { email: editing.email, name: editing.name } : undefined}
      >
        <Form.Item
          name="email"
          label="邮箱"
          rules={[
            { required: true, message: "请输入邮箱" },
            { type: "email", message: "邮箱格式不正确" },
          ]}
        >
          <Input autoComplete="off" />
        </Form.Item>
        <Form.Item
          name="name"
          label="姓名"
          rules={[
            { required: true, message: "请输入姓名" },
            { max: 100, message: "姓名最长 100 字" },
          ]}
        >
          <Input />
        </Form.Item>
        {!editing && (
          <Form.Item
            name="password"
            label="初始密码"
            rules={[
              { required: true, message: "请输入初始密码" },
              { min: 8, max: 72, message: "密码长度须为 8-72 位" },
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
}
