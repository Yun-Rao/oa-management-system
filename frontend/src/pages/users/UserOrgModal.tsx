import { useEffect, useMemo, useState } from "react";
import { Alert, Form, Modal, Select, TreeSelect } from "antd";

import { ApiError } from "../../api/client";
import { listDeptMembers, listDeptTree } from "../../api/departments";
import { updateUserOrg } from "../../api/users";
import type { DepartmentNode, UserResponse } from "../../types/api";
import { toTreeSelectData } from "../../utils/deptTree";

interface Props {
  user: UserResponse | null;
  onClose: () => void;
  onSuccess: () => void;
}

interface OrgFormValues {
  department_id?: string;
  manager_id?: string;
}

export default function UserOrgModal({ user, onClose, onSuccess }: Props) {
  const [form] = Form.useForm<OrgFormValues>();
  const [tree, setTree] = useState<DepartmentNode[]>([]);
  const [candidates, setCandidates] = useState<UserResponse[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const deptId = Form.useWatch("department_id", form);

  useEffect(() => {
    if (!user) return;
    setError(null);
    setCandidates([]);
    void listDeptTree()
      .then(setTree)
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试")
      );
  }, [user]);

  useEffect(() => {
    if (!user || !deptId) {
      setCandidates([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        // 上级候选 = 部门全部成员(spec);单页 100 会截断,翻页拉全
        const all: UserResponse[] = [];
        for (let page = 1; ; page += 1) {
          const resp = await listDeptMembers(deptId, { page, page_size: 100 });
          all.push(...resp.items);
          if (all.length >= resp.total || resp.items.length === 0) break;
        }
        if (!cancelled) setCandidates(all.filter((m) => m.id !== user.id));
      } catch {
        if (!cancelled) setCandidates([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user, deptId]);

  const treeData = useMemo(() => toTreeSelectData(tree), [tree]);

  // 现任上级并入候选:拉取完成前(或极端截断)Select 不至于回显原始 UUID
  const managerOptions = useMemo(() => {
    const opts = candidates.map((m) => ({ value: m.id, label: m.name }));
    const mgr = user?.manager;
    if (mgr && user?.department?.id === deptId && !candidates.some((m) => m.id === mgr.id)) {
      opts.unshift({ value: mgr.id, label: mgr.name });
    }
    return opts;
  }, [candidates, user, deptId]);

  async function onFinish(values: OrgFormValues) {
    if (!user) return;
    setSubmitting(true);
    setError(null);
    try {
      await updateUserOrg(user.id, {
        department_id: values.department_id ?? null,
        manager_id: values.manager_id ?? null,
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
      title={`设置归属:${user?.name ?? ""}`}
      open={user !== null}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Form<OrgFormValues>
        key={user?.id ?? "none"}
        form={form}
        layout="vertical"
        onFinish={onFinish}
        preserve={false}
        initialValues={
          user
            ? {
                department_id: user.department?.id ?? undefined,
                manager_id: user.manager?.id ?? undefined,
              }
            : undefined
        }
      >
        <Form.Item name="department_id" label="所属部门">
          <TreeSelect
            treeData={treeData}
            allowClear
            placeholder="不选则无部门"
            treeDefaultExpandAll
            onChange={() => form.setFieldsValue({ manager_id: undefined })}
          />
        </Form.Item>
        <Form.Item name="manager_id" label="直属上级">
          <Select
            allowClear
            placeholder="先从部门成员中选择"
            options={managerOptions}
            disabled={!deptId}
            showSearch
            optionFilterProp="label"
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
