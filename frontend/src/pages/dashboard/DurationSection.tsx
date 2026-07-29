import { Card, Col, Row, Statistic } from "antd";

import type { ApprovalDurationItem } from "../../types/api";

interface Props {
  durations: ApprovalDurationItem[];
}

const CATEGORY_LABEL: Record<string, string> = {
  leave: "请假审批",
  expense: "报销审批",
};

export default function DurationSection({ durations }: Props) {
  return (
    <Card title="审批时效统计">
      <Row gutter={16}>
        {durations.map((d) => (
          <Col span={6} key={d.category}>
            <Statistic
              title={`${CATEGORY_LABEL[d.category] ?? d.category}平均时效(完成 ${d.completed_count} 单)`}
              value={d.avg_hours === null ? "—" : `${d.avg_hours} 小时`}
            />
          </Col>
        ))}
      </Row>
    </Card>
  );
}
