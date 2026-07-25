import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
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

  it("关闭后重开:旧错误 Alert 被清除", async () => {
    // 用有状态的 Harness 驱动 leaveId(不用 rerender:setup 的 render 包装在
    // ConfigProvider/AntdApp 内,rerender 会替换根节点导致组件重挂载、测不出残留状态)
    vi.mocked(rejectLeave).mockRejectedValue(new ApiError("CONFLICT", "单据已终态"));
    function Harness() {
      const [leaveId, setLeaveId] = useState<string | null>("l1");
      return (
        <>
          <button onClick={() => setLeaveId("l1")}>reopen</button>
          <RejectModal leaveId={leaveId} onClose={() => setLeaveId(null)} onSuccess={() => {}} />
        </>
      );
    }
    render(<Harness />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("驳回原因"), "人手不足");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("单据已终态")).toBeInTheDocument();
    await user.click(document.querySelector(".ant-modal-close") as HTMLElement);
    await user.click(screen.getByRole("button", { name: "reopen" }));
    await screen.findByLabelText("驳回原因");
    expect(screen.queryByText("单据已终态")).toBeNull();
  });
});
