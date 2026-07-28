import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/leaves", () => ({ getLeaveDetail: vi.fn() }));

import { getLeaveDetail } from "../../api/leaves";
import { ApiError } from "../../api/client";
import LeaveDetailModal from "./LeaveDetailModal";

const detail = {
  id: "l1",
  type: "sick",
  start_date: "2026-08-01",
  end_date: "2026-08-03",
  reason: "感冒",
  status: "rejected",
  applicant: { id: "u1", name: "张三" },
  approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-25T10:00:00",
  history: [
    { from_status: null, to_status: "pending", actor: { id: "u1", name: "张三" }, comment: null, created_at: "2026-07-25T10:00:00" },
    { from_status: "pending", to_status: "rejected", actor: { id: "u2", name: "王主管" }, comment: "人手不足", created_at: "2026-07-25T11:00:00" },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("LeaveDetailModal", () => {
  it("字段 + 状态历史渲染(含驳回 comment)", async () => {
    vi.mocked(getLeaveDetail).mockResolvedValue(detail);
    render(<LeaveDetailModal leaveId="l1" onClose={() => {}} />);
    expect(await screen.findByText("感冒")).toBeInTheDocument();
    expect(screen.getByText("张三")).toBeInTheDocument();
    expect(screen.getByText("王主管")).toBeInTheDocument();
    expect(screen.getByText("2026-08-01 ~ 2026-08-03")).toBeInTheDocument();
    // 历史:两行,驳回行含原因
    expect(await screen.findByText(/待审批/)).toBeInTheDocument();
    // "已驳回" 同时出现在状态 Tag 与时间线,断言至少一处渲染
    expect(screen.getAllByText(/已驳回/).length).toBeGreaterThan(0);
    expect(screen.getByText(/人手不足/)).toBeInTheDocument();
  });

  it("403 越权:Modal 内 Alert", async () => {
    vi.mocked(getLeaveDetail).mockRejectedValue(new ApiError("FORBIDDEN", "无权查看该单据"));
    render(<LeaveDetailModal leaveId="l1" onClose={() => {}} />);
    expect(await screen.findByText("无权查看该单据")).toBeInTheDocument();
  });
});
