import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/expenses", () => ({
  getExpenseDetail: vi.fn(),
  downloadAttachment: vi.fn(),
}));

import { downloadAttachment, getExpenseDetail } from "../../api/expenses";
import type { ExpenseDetail } from "../../types/api";
import ExpenseDetailModal from "./ExpenseDetailModal";

function detail(over: Partial<ExpenseDetail>): ExpenseDetail {
  return {
    id: "e1",
    type: "travel",
    amount: "1999.50",
    reason: "出差打车",
    status: "pending_l1",
    applicant: { id: "u1", name: "张三" },
    approver: { id: "u2", name: "王主管" },
    created_at: "2026-07-29T09:00:00",
    updated_at: "2026-07-29T09:00:00",
    history: [
      { from_status: null, to_status: "pending_l1", actor: { id: "u1", name: "张三" }, comment: null, created_at: "2026-07-29T09:00:00" },
    ],
    attachments: [
      { id: "a1", filename: "发票.png", content_type: "image/png", size_bytes: 2048, created_at: "2026-07-29T09:00:00" },
    ],
    ...over,
  };
}

function renderModal() {
  return render(
    <App>
      <ExpenseDetailModal expenseId="e1" onClose={vi.fn()} />
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();
});

describe("ExpenseDetailModal", () => {
  it("L1:当前审批显示 第 1 级 · 主管姓名", async () => {
    vi.mocked(getExpenseDetail).mockResolvedValue(detail({}));
    renderModal();
    expect(await screen.findByText("报销详情")).toBeInTheDocument();
    expect(screen.getByText("第 1 级 · 王主管")).toBeInTheDocument();
    expect(screen.getByText("¥1999.50")).toBeInTheDocument();
    expect(screen.getByText("待主管审批")).toBeInTheDocument();
  });

  it("L2:当前审批显示 第 2 级 · HR/Admin 权限池", async () => {
    vi.mocked(getExpenseDetail).mockResolvedValue(detail({ status: "pending_l2", approver: null }));
    renderModal();
    expect(await screen.findByText("第 2 级 · HR/Admin 权限池")).toBeInTheDocument();
  });

  it("终态:当前审批显示 —", async () => {
    vi.mocked(getExpenseDetail).mockResolvedValue(detail({ status: "approved" }));
    renderModal();
    await screen.findByText("报销详情");
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("附件列表渲染,点击触发鉴权下载", async () => {
    vi.mocked(getExpenseDetail).mockResolvedValue(detail({}));
    vi.mocked(downloadAttachment).mockResolvedValue(new Blob(["x"]));
    renderModal();
    const user = userEvent.setup();
    await user.click(await screen.findByText(/发票\.png/));
    expect(downloadAttachment).toHaveBeenCalledWith("e1", "a1");
    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
  });

  it("Timeline 渲染 actor 与驳回原因", async () => {
    vi.mocked(getExpenseDetail).mockResolvedValue(
      detail({
        status: "rejected",
        history: [
          { from_status: null, to_status: "pending_l1", actor: { id: "u1", name: "张三" }, comment: null, created_at: "2026-07-29T09:00:00" },
          { from_status: "pending_l1", to_status: "rejected", actor: { id: "u2", name: "王主管" }, comment: "发票不清", created_at: "2026-07-29T10:00:00" },
        ],
      })
    );
    renderModal();
    expect(await screen.findByText(/已驳回 · 王主管/)).toBeInTheDocument();
    expect(screen.getByText(/发票不清/)).toBeInTheDocument();
  });
});
