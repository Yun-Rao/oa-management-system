import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/leaves", () => ({ listAll: vi.fn(), getLeaveDetail: vi.fn() }));
vi.mock("../../api/departments", () => ({ listDeptTree: vi.fn() }));

import { listAll } from "../../api/leaves";
import { listDeptTree } from "../../api/departments";
import AllLeavesPanel from "./AllLeavesPanel";

const leave = {
  id: "l1", type: "sick", start_date: "2026-08-01", end_date: "2026-08-03",
  reason: "感冒", status: "pending",
  applicant: { id: "u1", name: "张三" }, approver: { id: "u2", name: "王主管" },
  created_at: "2026-07-25T10:00:00",
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listAll).mockResolvedValue({ items: [leave], total: 1, page: 1, page_size: 20 });
  vi.mocked(listDeptTree).mockResolvedValue([
    { id: "d1", name: "技术部", parent_id: null, member_count: 2, children: [] },
  ]);
});

describe("AllLeavesPanel", () => {
  it("列表渲染:申请人/类型/状态/审批人", async () => {
    render(<AllLeavesPanel />);
    expect(await screen.findByText("张三")).toBeInTheDocument();
    expect(screen.getByText("王主管")).toBeInTheDocument();
  });

  it("状态筛选:带 status 参数重查并回第 1 页", async () => {
    render(<AllLeavesPanel />);
    await screen.findByText("张三");
    const user = userEvent.setup();
    // Deviation: antd Select 的 placeholder 不在 input 占位属性上,改用 combobox 角色
    // (DOM 顺序: 0=部门 TreeSelect, 1=状态 Select, 2=类型 Select)
    await user.click(screen.getAllByRole("combobox")[1]);
    await user.click(await screen.findByTitle("已通过"));
    await waitFor(() =>
      expect(listAll).toHaveBeenCalledWith(expect.objectContaining({ status: "approved", page: 1 }))
    );
  });

  it("部门筛选:TreeSelect 选技术部带 department_id", async () => {
    render(<AllLeavesPanel />);
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("combobox")[0]);
    const treeDropdown = await screen.findByRole("tree");
    await user.click(within(treeDropdown).getByText("技术部"));
    await waitFor(() =>
      expect(listAll).toHaveBeenCalledWith(expect.objectContaining({ department_id: "d1", page: 1 }))
    );
  });

  it("日期区间筛选:start_from/end_to 格式化", async () => {
    render(<AllLeavesPanel />);
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(document.querySelector(".ant-picker") as HTMLElement);
    await user.type(screen.getByPlaceholderText("开始日期"), "2026-08-01");
    await user.type(screen.getByPlaceholderText("结束日期"), "2026-08-31{enter}");
    await waitFor(() =>
      expect(listAll).toHaveBeenCalledWith(
        expect.objectContaining({ start_from: "2026-08-01", end_to: "2026-08-31", page: 1 })
      )
    );
  });
});
