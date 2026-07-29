import { Card, Col, Row, Statistic, Table } from "antd";

import type { LeaveStatItem } from "../../types/api";

interface Props {
  stats: LeaveStatItem[];
}

export default function LeaveStatsSection({ stats }: Props) {
  const totalCount = stats.reduce((s, x) => s + x.request_count, 0);
  const totalDays = stats.reduce((s, x) => s + x.total_days, 0);

  const columns = [
    { title: "部门", dataIndex: "department_name", key: "department_name" },
    { title: "请假人次", dataIndex: "request_count", key: "request_count" },
    { title: "请假天数", dataIndex: "total_days", key: "total_days" },
  ];

  return (
    <Card title="部门请假统计" style={{ marginBottom: 16 }}>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Statistic title="总人次" value={totalCount} />
        </Col>
        <Col span={6}>
          <Statistic title="总天数" value={totalDays} />
        </Col>
      </Row>
      <Table<LeaveStatItem>
        rowKey="department_id"
        columns={columns}
        dataSource={stats}
        pagination={false}
      />
    </Card>
  );
}
