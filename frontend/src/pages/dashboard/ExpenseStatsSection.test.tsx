import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ExpenseStatItem } from "../../types/api";
import ExpenseStatsSection from "./ExpenseStatsSection";

const rows: ExpenseStatItem[] = [
  { department_id: "d1", department_name: "技术部", request_count: 8, total_amount: "12345.60" },
  { department_id: "d2", department_name: "市场部", request_count: 2, total_amount: "100.40" },
];

describe("ExpenseStatsSection", () => {
  it("明细金额 ¥ 直拼;汇总总金额 Number 求和 toFixed(2)", () => {
    render(<ExpenseStatsSection stats={rows} />);
    expect(screen.getByText("¥12345.60")).toBeInTheDocument();
    expect(screen.getByText("¥100.40")).toBeInTheDocument();
    expect(screen.getByText("¥12446.00")).toBeInTheDocument();
    expect(screen.getByText("总笔数").parentElement).toHaveTextContent("10");
  });

  it("空数组:汇总 0 与 ¥0.00,表格空态", () => {
    render(<ExpenseStatsSection stats={[]} />);
    expect(screen.getByText("总笔数").parentElement).toHaveTextContent("0");
    expect(screen.getByText("¥0.00")).toBeInTheDocument();
    expect(screen.getAllByText("暂无数据").length).toBeGreaterThan(0);
  });
});
