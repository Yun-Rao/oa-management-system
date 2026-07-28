import { Alert, Empty, Table, Tag } from "antd";

import type { DepartmentNode, UserResponse } from "../../types/api";

interface Props {
  dept: DepartmentNode | null;
  members: UserResponse[];
  total: number;
  page: number;
  loading: boolean;
  error: string | null;
  onPageChange: (page: number) => void;
}

export default function DeptMembersPanel({
  dept,
  members,
  total,
  page,
  loading,
  error,
  onPageChange,
}: Props) {
  if (!dept) {
    return <Empty description="请选择左侧部门查看成员" style={{ marginTop: 80 }} />;
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
      title: "状态",
      key: "status",
      render: (_: unknown, u: UserResponse) =>
        u.is_active ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag>,
    },
  ];

  return (
    <div>
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Table<UserResponse>
        rowKey="id"
        columns={columns}
        dataSource={members}
        loading={loading}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p) => onPageChange(p),
        }}
      />
    </div>
  );
}
