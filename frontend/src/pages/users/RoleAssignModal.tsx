import { useEffect, useState } from "react";
import { Alert, Checkbox, Modal, Spin } from "antd";

import { ApiError } from "../../api/client";
import { listRoles } from "../../api/roles";
import { assignRoles } from "../../api/users";
import type { RoleResponse, UserResponse } from "../../types/api";

interface Props {
  user: UserResponse | null;
  onClose: () => void;
  onSuccess: () => void;
}

export default function RoleAssignModal({ user, onClose, onSuccess }: Props) {
  const [roles, setRoles] = useState<RoleResponse[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    setError(null);
    setRoles(null);
    setSelected(user.roles.map((r) => r.code));
    listRoles()
      .then(setRoles)
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试")
      );
  }, [user]);

  async function onOk() {
    if (!user) return;
    setSubmitting(true);
    setError(null);
    try {
      await assignRoles(user.id, selected);
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
      title={user ? `分配角色:${user.name}` : "分配角色"}
      open={user !== null}
      onCancel={onClose}
      onOk={onOk}
      confirmLoading={submitting}
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      {roles === null && !error ? (
        <Spin />
      ) : (
        <Checkbox.Group
          style={{ display: "flex", flexDirection: "column", gap: 8 }}
          value={selected}
          onChange={(vals) => setSelected(vals as string[])}
          options={(roles ?? []).map((r) => ({
            label: `${r.name}(${r.code})`,
            value: r.code,
          }))}
        />
      )}
    </Modal>
  );
}
