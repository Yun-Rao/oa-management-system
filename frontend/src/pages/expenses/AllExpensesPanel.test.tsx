import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/expenses", () => ({
  listAll: vi.fn(),
  getExpenseDetail: vi.fn(),
  downloadAttachment: vi.fn(),
}));
vi.mock("../../api/departments", () => ({ listDeptTree: vi.fn() }));

import { listDeptTree } from "../../api/departments";
import { listAll } from "../../api/expenses";
import type { ExpenseListResponse } from "../../types/api";
import AllExpensesPanel from "./AllExpensesPanel";

const item = {
  id: "e1", type: "travel", amount: "1999.50", reason: "出差打车", status: "pending_l1",
  applicant: { id: "u1", name: "张三" }, approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-29T09:00:00", updated_at: "2026-07-29T09:00:00",
};

function paged(items: unknown[]): ExpenseListResponse {
  return { items: items as never, total: items.length, page: 1, page_size: 20 };
}

function renderPanel() {
  return render(
    <App>
      <AllExpensesPanel />
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listAll).mockResolvedValue(paged([item]));
  vi.mocked(listDeptTree).mockResolvedValue([
    { id: "d1", name: "技术部", parent_id: null, member_count: 3, children: [] },
  ]);
});

describe("AllExpensesPanel", () => {
  it("初始加载:listAll 仅带分页参数,渲染申请人/金额/状态", async () => {
    renderPanel();
    expect(await screen.findByText("出差打车")).toBeInTheDocument();
    expect(screen.getByText("张三")).toBeInTheDocument();
    expect(screen.getByText("¥1999.50")).toBeInTheDocument();
    expect(listAll).toHaveBeenCalledWith({ page: 1, page_size: 20 });
  });

  it("状态筛选透传", async () => {
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("combobox")[1]);
    const dropdown = document.querySelector(".ant-select-dropdown") as HTMLElement;
    await user.click(await within(dropdown).findByText("已通过"));
    await waitFor(() =>
      expect(listAll).toHaveBeenCalledWith({ status: "approved", page: 1, page_size: 20 })
    );
  });

  it("类型筛选透传", async () => {
    renderPanel();
    await screen.findByText("出差打车");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("combobox")[2]);
    const dropdown = document.querySelector(".ant-select-dropdown") as HTMLElement;
    await user.click(await within(dropdown).findByText("差旅"));
    await waitFor(() =>
      expect(listAll).toHaveBeenCalledWith({ type: "travel", page: 1, page_size: 20 })
    );
  });
});
