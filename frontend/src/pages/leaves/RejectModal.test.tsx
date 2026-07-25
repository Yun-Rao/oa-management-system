import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/leaves", () => ({ rejectLeave: vi.fn() }));

import { rejectLeave } from "../../api/leaves";
import { ApiError } from "../../api/client";
import RejectModal from "./RejectModal";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RejectModal", () => {
  it("提交:rejectLeave(id, reason),成功后 onSuccess + onClose", async () => {
    vi.mocked(rejectLeave).mockResolvedValue({} as never);
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    render(<RejectModal leaveId="l1" onClose={onClose} onSuccess={onSuccess} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("驳回原因"), "人手不足");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() => expect(rejectLeave).toHaveBeenCalledWith("l1", "人手不足"));
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("校验:原因必填", async () => {
    render(<RejectModal leaveId="l1" onClose={() => {}} onSuccess={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("请输入驳回原因")).toBeInTheDocument();
    expect(rejectLeave).not.toHaveBeenCalled();
  });

  it("失败:Modal 内 Alert,不关闭", async () => {
    vi.mocked(rejectLeave).mockRejectedValue(new ApiError("CONFLICT", "单据已终态"));
    const onClose = vi.fn();
    render(<RejectModal leaveId="l1" onClose={onClose} onSuccess={() => {}} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("驳回原因"), "人手不足");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("单据已终态")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
