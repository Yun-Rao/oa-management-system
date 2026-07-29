import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/expenses", () => ({
  listMine: vi.fn(),
  cancelExpense: vi.fn(),
  createExpense: vi.fn(),
  getExpenseDetail: vi.fn(),
  downloadAttachment: vi.fn(),
}));

import { cancelExpense, listMine } from "../../api/expenses";
import type { ExpenseListResponse } from "../../types/api";
import MyExpensesPanel from "./MyExpensesPanel";

const pending = {
  id: "e1", type: "travel", amount: "1999.50", reason: "出差打车", status: "pending_l1",
  applicant: { id: "u1", name: "张三" }, approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-29T09:00:00", updated_at: "2026-07-29T09:00:00",
};
const approved = { ...pending, id: "e2", status: "approved", type: "office", amount: "88", reason: "买纸" };

function paged(items: unknown[]): ExpenseListResponse {
  return { items: items as never, total: items.length, page: 1, page_size: 20 };
}

function renderPanel() {
  return render(
    <App>
      <MyExpensesPanel />
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listMine).mockResolvedValue(paged([pending, approved]));
});

describe("MyExpensesPanel", () => {
  it("列表渲染:类型/金额/状态/审批人;pending_l1 行有撤回,终态行无", async () => {
    renderPanel();
    expect(await screen.findByText("出差打车")).toBeInTheDocument();
    expect(screen.getByText("买纸")).toBeInTheDocument();
    expect(screen.getByText("¥1999.50")).toBeInTheDocument();
    expect(screen.getAllByText("王主管").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "撤回" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "详情" })).toHaveLength(2);
  });

  it("status 筛选:带参数重查并回第 1 页", async () => {
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("combobox")[0]);
    const dropdown = document.querySelector(".ant-select-dropdown") as HTMLElement;
    await user.click(await within(dropdown).findByText("待主管审批"));
    await waitFor(() =>
      expect(listMine).toHaveBeenCalledWith({ status: "pending_l1", page: 1, page_size: 20 })
    );
  });

  it("type 筛选:带参数重查", async () => {
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("combobox")[1]);
    const dropdown = document.querySelector(".ant-select-dropdown") as HTMLElement;
    await user.click(await within(dropdown).findByText("差旅"));
    await waitFor(() =>
      expect(listMine).toHaveBeenCalledWith({ type: "travel", page: 1, page_size: 20 })
    );
  });

  it("撤回:Popconfirm 确认后调 cancelExpense 并刷新", async () => {
    vi.mocked(cancelExpense).mockResolvedValue({} as never);
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "撤回" }));
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    await waitFor(() => expect(cancelExpense).toHaveBeenCalledWith("e1"));
    await waitFor(() => expect(listMine).toHaveBeenCalledTimes(2));
  });

  it("新建报销:点按钮打开 ExpenseFormModal", async () => {
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "新建报销" }));
    expect(await screen.findByText("新建报销申请")).toBeInTheDocument();
  });
});
