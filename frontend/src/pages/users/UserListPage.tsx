import { useCallback, useEffect, useState } from "react";
import { Alert, App, Button, Card, Input, Popconfirm, Space, Table, Tag } from "antd";
import { Navigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { listUsers, setUserStatus } from "../../api/users";
import { useAuthStore } from "../../store/auth";
import type { UserResponse } from "../../types/api";
import RoleAssignModal from "./RoleAssignModal";
import UserFormModal from "./UserFormModal";
import UserOrgModal from "./UserOrgModal";

const PAGE_SIZE = 20;

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : "网络异常,请稍后重试";
}

export default function UserListPage() {
  const { message } = App.useApp();
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const allowed = hasPermission("user:list");

  const [items, setItems] = useState<UserResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<UserResponse | null>(null);
  const [assigning, setAssigning] = useState<UserResponse | null>(null);
  const [orgEditing, setOrgEditing] = useState<UserResponse | null>(null);

  const fetchList = useCallback(async (p: number, kw: string) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listUsers({ page: p, page_size: PAGE_SIZE, ...(kw ? { keyword: kw } : {}) });
      setItems(resp.items);
      setTotal(resp.total);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (allowed) void fetchList(page, search);
  }, [allowed, page, search, fetchList]);

  function onSearch() {
    setPage(1);
    setSearch(input.trim());
  }

  async function onToggleStatus(u: UserResponse) {
    try {
      await setUserStatus(u.id, !u.is_active);
      message.success(u.is_active ? "已禁用" : "已启用");
      await fetchList(page, search);
    } catch (e) {
      message.error(errMsg(e));
    }
  }

  if (!allowed) {
    return <Navigate to="/" replace />;
  }

  const columns = [
    { title: "姓名", dataIndex: "name", key: "name" },
    { title: "邮箱", dataIndex: "email", key: "email" },
    {
      title: "角色",
      key: "roles",
      render: (_: unknown, u: UserResponse) =>
        u.roles.map((r) => <Tag key={r.code}>{r.name}</Tag>),
    },
    {
      title: "部门",
      key: "department",
      render: (_: unknown, u: UserResponse) => u.department?.name ?? "-",
    },
    {
      title: "状态",
      key: "status",
      render: (_: unknown, u: UserResponse) =>
        u.is_active ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag>,
    },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, u: UserResponse) => (
        <Space>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setEditing(u);
              setFormOpen(true);
            }}
          >
            编辑
          </Button>
          <Button type="link" size="small" onClick={() => setAssigning(u)}>
            分配角色
          </Button>
          {hasPermission("user:update") && (
            <Button type="link" size="small" onClick={() => setOrgEditing(u)}>
              归属
            </Button>
          )}
          <Popconfirm
            title={u.is_active ? "确认禁用该用户?" : "确认启用该用户?"}
            onConfirm={() => void onToggleStatus(u)}
          >
            <Button type="link" size="small" danger={u.is_active}>
              {u.is_active ? "禁用" : "启用"}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="用户管理"
      extra={
        <Space>
          <Input.Search
            placeholder="姓名或邮箱"
            allowClear
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onSearch={onSearch}
            style={{ width: 240 }}
          />
          <Button
            type="primary"
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            新建用户
          </Button>
        </Space>
      }
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Table<UserResponse>
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p) => setPage(p),
        }}
      />
      <UserFormModal
        open={formOpen}
        editing={editing}
        onClose={() => setFormOpen(false)}
        onSuccess={() => {
          message.success(editing ? "已保存" : "已创建");
          void fetchList(page, search);
        }}
      />
      <RoleAssignModal
        user={assigning}
        onClose={() => setAssigning(null)}
        onSuccess={() => {
          message.success("角色已更新");
          void fetchList(page, search);
        }}
      />
      <UserOrgModal
        user={orgEditing}
        onClose={() => setOrgEditing(null)}
        onSuccess={() => {
          message.success("归属已更新");
          void fetchList(page, search);
        }}
      />
    </Card>
  );
}
