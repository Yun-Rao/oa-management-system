import { useCallback, useEffect, useState } from "react";
import { Alert, App, Card } from "antd";
import { Navigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { deleteDepartment, listDeptMembers, listDeptTree } from "../../api/departments";
import { useAuthStore } from "../../store/auth";
import type { DepartmentNode, UserResponse } from "../../types/api";
import { findNode } from "../../utils/deptTree";
import DeptFormModal from "./DeptFormModal";
import DeptMembersPanel from "./DeptMembersPanel";
import DeptTreePanel from "./DeptTreePanel";

const PAGE_SIZE = 20;

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : "网络异常,请稍后重试";
}

export default function DepartmentPage() {
  const { message } = App.useApp();
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const allowed = hasPermission("department:list");
  const canCreate = hasPermission("department:create");
  const canUpdate = hasPermission("department:update");
  const canDelete = hasPermission("department:delete");

  const [tree, setTree] = useState<DepartmentNode[]>([]);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [members, setMembers] = useState<UserResponse[]>([]);
  const [membersTotal, setMembersTotal] = useState(0);
  const [membersPage, setMembersPage] = useState(1);
  const [membersLoading, setMembersLoading] = useState(false);
  const [membersError, setMembersError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editingDept, setEditingDept] = useState<DepartmentNode | null>(null);
  const [presetParentId, setPresetParentId] = useState<string | null>(null);

  const fetchTree = useCallback(async () => {
    setTreeError(null);
    try {
      const data = await listDeptTree();
      setTree(data);
      setSelectedId((prev) => {
        if (prev) return prev;
        return data.length > 0 ? data[0].id : null;
      });
    } catch (e) {
      setTreeError(errMsg(e));
    }
  }, []);

  useEffect(() => {
    if (allowed) void fetchTree();
  }, [allowed, fetchTree]);

  useEffect(() => {
    if (!allowed || !selectedId) return;
    let cancelled = false;
    setMembersLoading(true);
    setMembersError(null);
    listDeptMembers(selectedId, { page: membersPage, page_size: PAGE_SIZE })
      .then((resp) => {
        if (cancelled) return;
        setMembers(resp.items);
        setMembersTotal(resp.total);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setMembers([]);
        setMembersTotal(0);
        setMembersError(errMsg(e));
      })
      .finally(() => {
        if (!cancelled) setMembersLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [allowed, selectedId, membersPage]);

  function onSelectDept(id: string) {
    if (id === selectedId) return;
    setSelectedId(id);
    setMembersPage(1);
  }

  function openCreate(parentId: string | null) {
    setEditingDept(null);
    setPresetParentId(parentId);
    setFormOpen(true);
  }

  function openEdit(node: DepartmentNode) {
    setEditingDept(node);
    setPresetParentId(null);
    setFormOpen(true);
  }

  async function onDelete(node: DepartmentNode) {
    try {
      await deleteDepartment(node.id);
      message.success("已删除");
      if (node.id === selectedId) {
        setSelectedId(null);
        setMembers([]);
        setMembersTotal(0);
      }
      await fetchTree();
    } catch (e) {
      message.error(errMsg(e));
    }
  }

  if (!allowed) {
    return <Navigate to="/" replace />;
  }

  const selectedDept = selectedId ? findNode(tree, selectedId) : null;

  return (
    <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
      <Card title="部门" style={{ width: 340, flexShrink: 0 }}>
        {treeError && (
          <Alert type="error" message={treeError} showIcon style={{ marginBottom: 16 }} />
        )}
        <DeptTreePanel
          tree={tree}
          selectedId={selectedId}
          canCreate={canCreate}
          canUpdate={canUpdate}
          canDelete={canDelete}
          onSelect={onSelectDept}
          onCreateRoot={() => openCreate(null)}
          onCreateChild={(node) => openCreate(node.id)}
          onEdit={openEdit}
          onDelete={(node) => void onDelete(node)}
        />
      </Card>
      <Card title="成员" style={{ flex: 1 }}>
        <DeptMembersPanel
          dept={selectedDept}
          members={members}
          total={membersTotal}
          page={membersPage}
          loading={membersLoading}
          error={membersError}
          onPageChange={setMembersPage}
        />
      </Card>
      <DeptFormModal
        open={formOpen}
        tree={tree}
        editing={editingDept}
        presetParentId={presetParentId}
        onClose={() => setFormOpen(false)}
        onSuccess={() => {
          message.success(editingDept ? "已保存" : "已创建");
          void fetchTree();
        }}
      />
    </div>
  );
}
