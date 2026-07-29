import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { LeaveStatItem } from "../../types/api";
import LeaveStatsSection from "./LeaveStatsSection";

const rows: LeaveStatItem[] = [
  { department_id: "d1", department_name: "技术部", request_count: 5, total_days: 11.5 },
  { department_id: "d2", department_name: "市场部", request_count: 3, total_days: 4.5 },
];

describe("LeaveStatsSection", () => {
  it("明细渲染部门行;汇总求和:总人次 8、总天数 16", () => {
    render(<LeaveStatsSection stats={rows} />);
    expect(screen.getByText("技术部")).toBeInTheDocument();
    expect(screen.getByText("市场部")).toBeInTheDocument();
    expect(screen.getByText("总人次").parentElement).toHaveTextContent("8");
    expect(screen.getByText("总天数").parentElement).toHaveTextContent("16");
  });

  it("空数组:汇总为 0,表格空态", () => {
    render(<LeaveStatsSection stats={[]} />);
    expect(screen.getByText("总人次").parentElement).toHaveTextContent("0");
    expect(screen.getAllByText("暂无数据").length).toBeGreaterThan(0);
  });
});
