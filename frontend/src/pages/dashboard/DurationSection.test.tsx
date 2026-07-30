import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ApprovalDurationItem } from "../../types/api";
import DurationSection from "./DurationSection";

describe("DurationSection", () => {
  it("avg_hours 数值显示 {x} 小时;null 显示 —;类别中文名", () => {
    const durations: ApprovalDurationItem[] = [
      { category: "leave", completed_count: 12, avg_hours: 20.4 },
      { category: "expense", completed_count: 0, avg_hours: null },
    ];
    render(<DurationSection durations={durations} />);
    expect(screen.getByText("20.4 小时")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText(/请假审批/)).toBeInTheDocument();
    expect(screen.getByText(/报销审批/)).toBeInTheDocument();
    expect(screen.getByText(/完成 12 单/)).toBeInTheDocument();
    expect(screen.getByText(/完成 0 单/)).toBeInTheDocument();
  });

  it("未知 category 原样显示", () => {
    render(
      <DurationSection durations={[{ category: "other", completed_count: 1, avg_hours: 1.5 }]} />
    );
    expect(screen.getByText(/other/)).toBeInTheDocument();
    expect(screen.getByText("1.5 小时")).toBeInTheDocument();
  });
});
