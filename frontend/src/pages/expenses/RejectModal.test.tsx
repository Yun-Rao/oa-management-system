import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/expenses", () => ({ rejectExpense: vi.fn() }));

import { rejectExpense } from "../../api/expenses";
import RejectModal from "./RejectModal";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RejectModal(报销)", () => {
  it("原因为空:校验拦截不提交", async () => {
    render(<RejectModal expenseId="e1" onClose={vi.fn()} onSuccess={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("请输入驳回原因")).toBeInTheDocument();
    expect(rejectExpense).not.toHaveBeenCalled();
  });

  it("填写原因提交:调 rejectExpense 并 onSuccess + onClose", async () => {
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    vi.mocked(rejectExpense).mockResolvedValue({} as never);
    render(<RejectModal expenseId="e1" onClose={onClose} onSuccess={onSuccess} />);
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox"), "发票不清");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() => expect(rejectExpense).toHaveBeenCalledWith("e1", "发票不清"));
    expect(onSuccess).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });
});
