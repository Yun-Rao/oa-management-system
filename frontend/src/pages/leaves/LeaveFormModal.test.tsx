import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/leaves", () => ({ createLeave: vi.fn() }));

import { createLeave } from "../../api/leaves";
import { ApiError } from "../../api/client";
import LeaveFormModal from "./LeaveFormModal";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("LeaveFormModal", () => {
  it("提交参数正确:日期格式化 YYYY-MM-DD", async () => {
    vi.mocked(createLeave).mockResolvedValue({} as never);
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    render(<LeaveFormModal open onClose={onClose} onSuccess={onSuccess} />);
    const user = userEvent.setup();
    // 选类型
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByText("病假"));
    // 起止日期
    const rangePicker = document.querySelector(".ant-picker") as HTMLElement;
    await user.click(rangePicker);
    const startInput = screen.getByPlaceholderText("开始日期");
    const endInput = screen.getByPlaceholderText("结束日期");
    await user.type(startInput, "2026-08-01");
    await user.type(endInput, "2026-08-03{enter}");
    await user.type(screen.getByLabelText("请假原因"), "感冒发烧");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() =>
      expect(createLeave).toHaveBeenCalledWith({
        type: "sick",
        start_date: "2026-08-01",
        end_date: "2026-08-03",
        reason: "感冒发烧",
      })
    );
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("校验:类型/日期/原因必填", async () => {
    render(<LeaveFormModal open onClose={() => {}} onSuccess={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("请选择请假类型")).toBeInTheDocument();
    expect(await screen.findByText("请选择起止日期")).toBeInTheDocument();
    expect(await screen.findByText("请输入请假原因")).toBeInTheDocument();
    expect(createLeave).not.toHaveBeenCalled();
  });

  it("失败(409 区间重叠):Modal 内 Alert,不关闭", async () => {
    vi.mocked(createLeave).mockRejectedValue(new ApiError("CONFLICT", "时间区间重叠"));
    const onClose = vi.fn();
    render(<LeaveFormModal open onClose={onClose} onSuccess={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByText("病假"));
    await user.click(document.querySelector(".ant-picker") as HTMLElement);
    await user.type(screen.getByPlaceholderText("开始日期"), "2026-08-01");
    await user.type(screen.getByPlaceholderText("结束日期"), "2026-08-03{enter}");
    await user.type(screen.getByLabelText("请假原因"), "感冒");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("时间区间重叠")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("关闭后重开:旧错误 Alert 被清除", async () => {
    // 用有状态的 Harness 驱动 open(不用 rerender:setup 的 render 包装在
    // ConfigProvider/AntdApp 内,rerender 会替换根节点导致组件重挂载、测不出残留状态)
    vi.mocked(createLeave).mockRejectedValue(new ApiError("CONFLICT", "时间区间重叠"));
    function Harness() {
      const [open, setOpen] = useState(true);
      return (
        <>
          <button onClick={() => setOpen(true)}>reopen</button>
          <LeaveFormModal open={open} onClose={() => setOpen(false)} onSuccess={() => {}} />
        </>
      );
    }
    render(<Harness />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByText("病假"));
    await user.click(document.querySelector(".ant-picker") as HTMLElement);
    await user.type(screen.getByPlaceholderText("开始日期"), "2026-08-01");
    await user.type(screen.getByPlaceholderText("结束日期"), "2026-08-03{enter}");
    await user.type(screen.getByLabelText("请假原因"), "感冒");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("时间区间重叠")).toBeInTheDocument();
    await user.click(document.querySelector(".ant-modal-close") as HTMLElement);
    await user.click(screen.getByRole("button", { name: "reopen" }));
    await screen.findByLabelText("请假原因");
    expect(screen.queryByText("时间区间重叠")).toBeNull();
  });
});
