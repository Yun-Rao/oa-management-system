import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/leaves", () => ({
  listTodo: vi.fn(),
  approveLeave: vi.fn(),
  rejectLeave: vi.fn(),
  getLeaveDetail: vi.fn(),
}));

import { approveLeave, listTodo } from "../../api/leaves";
import { ApiError } from "../../api/client";
import TodoLeavesPanel from "./TodoLeavesPanel";

const todo = {
  id: "l1", type: "sick", start_date: "2026-08-01", end_date: "2026-08-03",
  reason: "感冒", status: "pending",
  applicant: { id: "u1", name: "张三" }, approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-25T10:00:00",
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listTodo).mockResolvedValue({ items: [todo], total: 1, page: 1, page_size: 20 });
});

describe("TodoLeavesPanel", () => {
  it("列表渲染:申请人/类型/日期/原因", async () => {
    render(<TodoLeavesPanel />);
    expect(await screen.findByText("张三")).toBeInTheDocument();
    expect(screen.getByText("感冒")).toBeInTheDocument();
    expect(screen.getByText("2026-08-01 ~ 2026-08-03")).toBeInTheDocument();
  });

  it("通过:Popconfirm 确认后调 approveLeave 并刷新", async () => {
    vi.mocked(approveLeave).mockResolvedValue({} as never);
    render(<TodoLeavesPanel />);
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "通过" }));
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    await waitFor(() => expect(approveLeave).toHaveBeenCalledWith("l1"));
    await waitFor(() => expect(listTodo).toHaveBeenCalledTimes(2));
  });

  it("驳回:打开 RejectModal", async () => {
    render(<TodoLeavesPanel />);
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "驳回" }));
    expect(await screen.findByText("驳回申请")).toBeInTheDocument();
  });

  it("通过 409(并发已处理):message.error 提示并刷新", async () => {
    vi.mocked(approveLeave).mockRejectedValue(new ApiError("CONFLICT", "单据已终态"));
    render(<TodoLeavesPanel />);
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "通过" }));
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    expect(await screen.findByText("单据已终态")).toBeInTheDocument();
    await waitFor(() => expect(listTodo).toHaveBeenCalledTimes(2));
  });
});
