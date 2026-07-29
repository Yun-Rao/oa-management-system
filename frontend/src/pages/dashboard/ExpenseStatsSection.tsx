import { Card, Col, Row, Statistic, Table } from "antd";

import type { ExpenseStatItem } from "../../types/api";

interface Props {
  stats: ExpenseStatItem[];
}

function sumAmount(stats: ExpenseStatItem[]): string {
  return stats.reduce((s, x) => s + Number(x.total_amount), 0).toFixed(2);
}

export default function ExpenseStatsSection({ stats }: Props) {
  const totalCount = stats.reduce((s, x) => s + x.request_count, 0);

  const columns = [
    { title: "部门", dataIndex: "department_name", key: "department_name" },
    { title: "报销笔数", dataIndex: "request_count", key: "request_count" },
    {
      title: "报销金额",
      key: "total_amount",
      render: (_: unknown, x: ExpenseStatItem) => `¥${x.total_amount}`,
    },
  ];

  return (
    <Card title="部门报销统计" style={{ marginBottom: 16 }}>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Statistic title="总笔数" value={totalCount} />
        </Col>
        <Col span={6}>
          <Statistic title="总金额" value={`¥${sumAmount(stats)}`} />
        </Col>
      </Row>
      <Table<ExpenseStatItem>
        rowKey="department_id"
        columns={columns}
        dataSource={stats}
        pagination={false}
      />
    </Card>
  );
}
