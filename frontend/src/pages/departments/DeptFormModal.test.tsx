import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/departments", () => ({
  createDepartment: vi.fn(),
  updateDepartment: vi.fn(),
}));

import { ApiError } from "../../api/client";
import { createDepartment, updateDepartment } from "../../api/departments";
import type { DepartmentNode, DepartmentResponse } from "../../types/api";
import DeptFormModal from "./DeptFormModal";

const tree: DepartmentNode[] = [
  {
    id: "d1",
    name: "技术部",
    parent_id: null,
    member_count: 3,
    children: [{ id: "d2", name: "前端组", parent_id: "d1", member_count: 1, children: [] }],
  },
  { id: "d5", name: "市场部", parent_id: null, member_count: 5, children: [] },
];

const editingNode: DepartmentNode = tree[0];

const savedResp: DepartmentResponse = { id: "d1", name: "研发部", parent_id: null };

const baseProps = {
  tree,
  onClose: () => {},
  onSuccess: () => {},
};

beforeEach(() => {
  vi.clearAllMocks();
});

function parentFormItem() {
  return within(screen.getByText("父部门").closest(".ant-form-item") as HTMLElement);
}

describe("DeptFormModal 新建模式", () => {
  it("名称为空提交:校验提示,不发起请求", async () => {
    render(<DeptFormModal open {...baseProps} editing={null} presetParentId={null} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("请输入部门名称")).toBeInTheDocument();
    expect(createDepartment).not.toHaveBeenCalled();
  });

  it("提交(根部门):createDepartment 仅带 name", async () => {
    vi.mocked(createDepartment).mockResolvedValue(savedResp);
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    render(
      <DeptFormModal open tree={tree} editing={null} presetParentId={null} onClose={onClose} onSuccess={onSuccess} />
    );
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("部门名称"), "人事部");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() => expect(createDepartment).toHaveBeenCalledWith({ name: "人事部" }));
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("提交(预填父部门):createDepartment 带 parent_id", async () => {
    vi.mocked(createDepartment).mockResolvedValue(savedResp);
    render(<DeptFormModal open {...baseProps} editing={null} presetParentId="d1" />);
    // 预填父部门显示在 TreeSelect 选中项
    expect(parentFormItem().getByText("技术部")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("部门名称"), "测试组");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() =>
      expect(createDepartment).toHaveBeenCalledWith({ name: "测试组", parent_id: "d1" })
    );
  });
});

describe("DeptFormModal 编辑模式", () => {
  it("预填名称与父部门;候选树排除自身及后代", async () => {
    render(<DeptFormModal open {...baseProps} editing={editingNode} presetParentId={null} />);
    expect(screen.getByLabelText("部门名称")).toHaveValue("技术部");
    const user = userEvent.setup();
    // 打开父部门 TreeSelect 下拉
    await user.click(parentFormItem().getByRole("combobox"));
    const dropdown = await screen.findByRole("tree");
    // 自身"技术部"与后代"前端组"被排除;"市场部"可选
    expect(within(dropdown).queryByText("技术部")).not.toBeInTheDocument();
    expect(within(dropdown).queryByText("前端组")).not.toBeInTheDocument();
    expect(within(dropdown).getByText("市场部")).toBeInTheDocument();
  });

  it("改父部门并提交:updateDepartment 带 name 与新 parent_id", async () => {
    vi.mocked(updateDepartment).mockResolvedValue(savedResp);
    render(<DeptFormModal open {...baseProps} editing={tree[0].children[0]} presetParentId={null} />);
    expect(screen.getByLabelText("部门名称")).toHaveValue("前端组");
    expect(parentFormItem().getByText("技术部")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(parentFormItem().getByRole("combobox"));
    const dropdown = await screen.findByRole("tree");
    await user.click(within(dropdown).getByText("市场部"));
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() =>
      expect(updateDepartment).toHaveBeenCalledWith("d2", { name: "前端组", parent_id: "d5" })
    );
  });

  it("清空父部门提交:parent_id 显式 null(设为根)", async () => {
    vi.mocked(updateDepartment).mockResolvedValue(savedResp);
    render(<DeptFormModal open {...baseProps} editing={tree[0].children[0]} presetParentId={null} />);
    const user = userEvent.setup();
    await user.click(parentFormItem().getByRole("combobox"));
    // 清空选择(TreeSelect allowClear 的清除图标)
    const item = parentFormItem().getByText("技术部").closest(".ant-select-selector") as HTMLElement;
    await user.hover(item);
    const clearIcon = item.parentElement!.querySelector(".ant-select-clear") as HTMLElement;
    await user.click(clearIcon);
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() =>
      expect(updateDepartment).toHaveBeenCalledWith("d2", { name: "前端组", parent_id: null })
    );
  });

  it("失败(同级重名 409):显示 ApiError.message,不关闭", async () => {
    vi.mocked(updateDepartment).mockRejectedValue(new ApiError("CONFLICT", "同级下已存在同名部门"));
    const onClose = vi.fn();
    render(
      <DeptFormModal open tree={tree} editing={editingNode} presetParentId={null} onClose={onClose} onSuccess={() => {}} />
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("同级下已存在同名部门")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
