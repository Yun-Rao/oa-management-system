import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DepartmentNode } from "../../types/api";
import DeptTreePanel from "./DeptTreePanel";

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

const baseProps = {
  tree,
  selectedId: "d1" as string | null,
  onSelect: vi.fn(),
  onCreateRoot: vi.fn(),
  onCreateChild: vi.fn(),
  onEdit: vi.fn(),
  onDelete: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("DeptTreePanel", () => {
  it("渲染树节点(名称+member_count),默认展开", () => {
    render(<DeptTreePanel {...baseProps} canCreate canUpdate canDelete />);
    expect(screen.getByText("技术部(3)")).toBeInTheDocument();
    expect(screen.getByText("前端组(1)")).toBeInTheDocument();
    expect(screen.getByText("市场部(5)")).toBeInTheDocument();
  });

  it("点击节点触发 onSelect", async () => {
    render(<DeptTreePanel {...baseProps} canCreate canUpdate canDelete />);
    const user = userEvent.setup();
    await user.click(screen.getByText("市场部(5)"));
    expect(baseProps.onSelect).toHaveBeenCalledWith("d5");
  });

  it("有权限:顶部新建按钮 + 节点操作按钮;新建子部门回调带节点", async () => {
    render(<DeptTreePanel {...baseProps} canCreate canUpdate canDelete />);
    const user = userEvent.setup();
    expect(screen.getByRole("button", { name: "新建部门" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "新建部门" }));
    expect(baseProps.onCreateRoot).toHaveBeenCalled();
    // 每个节点 3 个操作按钮(aria-label)
    const addButtons = screen.getAllByRole("button", { name: "新建子部门" });
    expect(addButtons).toHaveLength(3);
    await user.click(addButtons[0]);
    expect(baseProps.onCreateChild).toHaveBeenCalledWith(tree[0]);
    await user.click(screen.getAllByRole("button", { name: "编辑部门" })[1]);
    expect(baseProps.onEdit).toHaveBeenCalledWith(tree[0].children[0]);
  });

  it("删除:Popconfirm 确认后回调带节点", async () => {
    render(<DeptTreePanel {...baseProps} canCreate canUpdate canDelete />);
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: "删除部门" })[0]);
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    expect(baseProps.onDelete).toHaveBeenCalledWith(tree[0]);
  });

  it("无权限(manager):全部 CRUD 按钮隐藏", () => {
    render(<DeptTreePanel {...baseProps} canCreate={false} canUpdate={false} canDelete={false} />);
    expect(screen.queryByRole("button", { name: "新建部门" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新建子部门" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "编辑部门" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "删除部门" })).not.toBeInTheDocument();
  });
});
