import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/expenses", () => ({
  listTodo: vi.fn(),
  approveExpense: vi.fn(),
  rejectExpense: vi.fn(),
  getExpenseDetail: vi.fn(),
  downloadAttachment: vi.fn(),
}));

import { approveExpense, listTodo } from "../../api/expenses";
import { ApiError } from "../../api/client";
import type { ExpenseListResponse } from "../../types/api";
import TodoExpensesPanel from "./TodoExpensesPanel";

const l1 = {
  id: "e1", type: "travel", amount: "1999.50", reason: "出差打车", status: "pending_l1",
  applicant: { id: "u1", name: "张三" }, approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-29T09:00:00", updated_at: "2026-07-29T09:00:00",
};
const l2 = { ...l1, id: "e2", status: "pending_l2", amount: "5000", reason: "团建", approver: null };

function paged(items: unknown[]): ExpenseListResponse {
  return { items: items as never, total: items.length, page: 1, page_size: 20 };
}

function renderPanel() {
  return render(
    <App>
      <TodoExpensesPanel />
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listTodo).mockResolvedValue(paged([l1, l2]));
});

describe("TodoExpensesPanel", () => {
  it("列表渲染:申请人/金额/级别 Tag;每行有通过/驳回/详情", async () => {
    renderPanel();
    expect(await screen.findByText("出差打车")).toBeInTheDocument();
    expect(screen.getAllByText("张三").length).toBeGreaterThan(0);
    expect(screen.getByText("待主管审批")).toBeInTheDocument();
    expect(screen.getByText("待二级审批")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "通过" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "驳回" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "详情" })).toHaveLength(2);
  });

  it("通过:Popconfirm 确认后调 approveExpense 并刷新", async () => {
    vi.mocked(approveExpense).mockResolvedValue({} as never);
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: "通过" })[0]);
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    await waitFor(() => expect(approveExpense).toHaveBeenCalledWith("e1"));
    await waitFor(() => expect(listTodo).toHaveBeenCalledTimes(2));
  });

  it("通过 409:message 提示且仍刷新列表", async () => {
    vi.mocked(approveExpense).mockRejectedValue(new ApiError("CONFLICT", "该单已被处理"));
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: "通过" })[0]);
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    await screen.findByText("该单已被处理");
    await waitFor(() => expect(listTodo).toHaveBeenCalledTimes(2));
  });

  it("驳回:打开 RejectModal", async () => {
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: "驳回" })[0]);
    expect(await screen.findByText("驳回申请")).toBeInTheDocument();
  });
});
