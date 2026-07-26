import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/leaves", () => ({
  listMine: vi.fn(),
  cancelLeave: vi.fn(),
  createLeave: vi.fn(),
  getLeaveDetail: vi.fn(),
}));

import { cancelLeave, listMine } from "../../api/leaves";
import type { LeaveListResponse } from "../../types/api";
import MyLeavesPanel from "./MyLeavesPanel";

const pending = {
  id: "l1", type: "sick", start_date: "2026-08-01", end_date: "2026-08-03",
  reason: "感冒", status: "pending",
  applicant: { id: "u1", name: "张三" }, approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-25T10:00:00",
};
const approved = { ...pending, id: "l2", status: "approved", type: "annual", reason: "回家" };

function paged(items: unknown[]): LeaveListResponse {
  return { items: items as never, total: items.length, page: 1, page_size: 20 };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listMine).mockResolvedValue(paged([pending, approved]));
});

describe("MyLeavesPanel", () => {
  it("列表渲染:类型/日期/状态/审批人;pending 行有撤回,终态行无", async () => {
    render(<MyLeavesPanel />);
    expect(await screen.findByText("感冒")).toBeInTheDocument();
    expect(screen.getByText("回家")).toBeInTheDocument();
    // 两行共用同一日期区间(approved 由 pending spread 而来),故断言 2 处
    expect(screen.getAllByText("2026-08-01 ~ 2026-08-03")).toHaveLength(2);
    expect(screen.getAllByText("王主管").length).toBeGreaterThan(0);
    // 撤回按钮仅 1 个(pending 行),详情每行都有
    expect(screen.getAllByRole("button", { name: "撤回" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "详情" })).toHaveLength(2);
  });

  it("status 筛选:带参数重查并回第 1 页", async () => {
    render(<MyLeavesPanel />);
    await screen.findByText("感冒");
    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));
    // "待审批" 同时出现在表格状态 Tag 与下拉选项,需限定在下拉内点选
    const dropdown = document.querySelector(".ant-select-dropdown") as HTMLElement;
    await user.click(await within(dropdown).findByText("待审批"));
    await waitFor(() =>
      expect(listMine).toHaveBeenCalledWith({ status: "pending", page: 1, page_size: 20 })
    );
  });

  it("撤回:Popconfirm 确认后调 cancelLeave 并刷新", async () => {
    vi.mocked(cancelLeave).mockResolvedValue({} as never);
    render(<MyLeavesPanel />);
    await screen.findByText("感冒");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "撤回" }));
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    await waitFor(() => expect(cancelLeave).toHaveBeenCalledWith("l1"));
    await waitFor(() => expect(listMine).toHaveBeenCalledTimes(2));
  });

  it("新建申请:点按钮打开 LeaveFormModal", async () => {
    render(<MyLeavesPanel />);
    await screen.findByText("感冒");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "新建申请" }));
    expect(await screen.findByText("新建请假申请")).toBeInTheDocument();
  });
});
