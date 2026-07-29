import { useState } from "react";
import { Alert, App, Form, Input, InputNumber, Modal, Select, Upload } from "antd";
import type { UploadFile } from "antd";

import { createExpense } from "../../api/expenses";
import { ApiError } from "../../api/client";
import type { ExpenseType } from "../../types/api";
import { EXPENSE_TYPE_MAP } from "../../utils/expense";

const MAX_FILES = 5;
const MAX_SIZE = 5 * 1024 * 1024;
const ALLOWED_EXT = [".jpg", ".jpeg", ".png", ".pdf"];

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

interface ExpenseFormValues {
  type: ExpenseType;
  amount: number;
  reason: string;
}

export default function ExpenseFormModal({ open, onClose, onSuccess }: Props) {
  const { message } = App.useApp();
  const [form] = Form.useForm<ExpenseFormValues>();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function acceptFile(file: File): boolean {
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED_EXT.includes(ext)) {
      message.error("仅支持 jpg/jpeg/png/pdf 格式");
      return false;
    }
    if (file.size > MAX_SIZE) {
      message.error(`单个文件不能超过 5MB`);
      return false;
    }
    return true;
  }

  async function onFinish(values: ExpenseFormValues) {
    if (fileList.length === 0) {
      setError("请上传 1~5 个附件凭证");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("type", values.type);
      fd.append("amount", values.amount.toFixed(2));
      fd.append("reason", values.reason);
      for (const f of fileList) {
        if (f.originFileObj) fd.append("files", f.originFileObj);
      }
      await createExpense(fd);
      onSuccess();
      handleClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  function handleClose() {
    setError(null);
    setFileList([]);
    form.resetFields();
    onClose();
  }

  return (
    <Modal
      title="新建报销申请"
      open={open}
      onCancel={handleClose}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Form<ExpenseFormValues> form={form} layout="vertical" onFinish={onFinish} preserve={false}>
        <Form.Item name="type" label="报销类型" rules={[{ required: true, message: "请选择报销类型" }]}>
          <Select
            placeholder="请选择"
            options={Object.entries(EXPENSE_TYPE_MAP).map(([value, m]) => ({ value, label: m.label }))}
          />
        </Form.Item>
        <Form.Item name="amount" label="金额(元)" rules={[{ required: true, message: "请输入金额" }]}>
          <InputNumber style={{ width: "100%" }} min={0.01} precision={2} placeholder="0.00" />
        </Form.Item>
        <Form.Item
          name="reason"
          label="报销说明"
          rules={[
            { required: true, message: "请输入报销说明" },
            { max: 500, message: "最多 500 字" },
          ]}
        >
          <Input.TextArea rows={3} maxLength={500} showCount />
        </Form.Item>
        <Form.Item label="附件凭证(1~5 个,jpg/png/pdf,单个 ≤5MB)" required>
          <Upload
            fileList={fileList}
            multiple
            beforeUpload={(file) => {
              if (fileList.length >= MAX_FILES) {
                message.error("最多 5 个附件");
                return Upload.LIST_IGNORE;
              }
              if (!acceptFile(file)) return Upload.LIST_IGNORE;
              return false;
            }}
            onChange={({ fileList: fl }) => setFileList(fl.slice(0, MAX_FILES))}
            onRemove={(f) => setFileList((prev) => prev.filter((x) => x.uid !== f.uid))}
          >
            <button type="button" className="ant-btn ant-btn-default">
              点击上传
            </button>
          </Upload>
        </Form.Item>
      </Form>
    </Modal>
  );
}
