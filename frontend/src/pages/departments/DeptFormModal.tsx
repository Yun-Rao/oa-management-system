import { useEffect, useMemo, useState } from "react";
import { Alert, Form, Input, Modal, TreeSelect } from "antd";

import { ApiError } from "../../api/client";
import { createDepartment, updateDepartment } from "../../api/departments";
import type { DepartmentNode } from "../../types/api";
import { collectSubtreeIds, findNode, toTreeSelectData } from "../../utils/deptTree";

interface Props {
  open: boolean;
  tree: DepartmentNode[];
  editing: DepartmentNode | null;
  presetParentId: string | null;
  onClose: () => void;
  onSuccess: () => void;
}

interface DeptFormValues {
  name: string;
  parent_id?: string;
}

export default function DeptFormModal({ open, tree, editing, presetParentId, onClose, onSuccess }: Props) {
  const [form] = Form.useForm<DeptFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) setError(null);
  }, [open]);

  const treeData = useMemo(() => {
    if (!editing) return toTreeSelectData(tree);
    const node = findNode(tree, editing.id);
    const exclude = node ? collectSubtreeIds(node) : undefined;
    return toTreeSelectData(tree, exclude);
  }, [tree, editing]);

  async function onFinish(values: DeptFormValues) {
    setSubmitting(true);
    setError(null);
    try {
      if (editing) {
        await updateDepartment(editing.id, {
          name: values.name,
          parent_id: values.parent_id ?? null,
        });
      } else {
        await createDepartment({
          name: values.name,
          ...(values.parent_id ? { parent_id: values.parent_id } : {}),
        });
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
      title={editing ? "编辑部门" : "新建部门"}
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Form<DeptFormValues>
        key={editing ? editing.id : `new-${presetParentId ?? "root"}`}
        form={form}
        layout="vertical"
        onFinish={onFinish}
        preserve={false}
        initialValues={
          editing
            ? { name: editing.name, parent_id: editing.parent_id ?? undefined }
            : { parent_id: presetParentId ?? undefined }
        }
      >
        <Form.Item
          name="name"
          label="部门名称"
          rules={[
            { required: true, message: "请输入部门名称" },
            { max: 100, message: "部门名称最长 100 字" },
          ]}
        >
          <Input />
        </Form.Item>
        <Form.Item name="parent_id" label="父部门">
          <TreeSelect
            treeData={treeData}
            allowClear
            placeholder="不选则为根部门"
            treeDefaultExpandAll
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
