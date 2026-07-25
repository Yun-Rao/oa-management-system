import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DepartmentNode, UserResponse } from "../../types/api";
import DeptMembersPanel from "./DeptMembersPanel";

const dept: DepartmentNode = {
  id: "d1",
  name: "技术部",
  parent_id: null,
  member_count: 2,
  children: [],
};

const member: UserResponse = {
  id: "u1",
  email: "a@x.com",
  name: "张三",
  is_active: true,
  roles: [{ code: "employee", name: "普通员工" }],
  department: { id: "d1", name: "技术部" },
  manager: null,
};

const baseProps = {
  dept,
  members: [member],
  total: 1,
  page: 1,
  loading: false,
  error: null as string | null,
  onPageChange: vi.fn(),
};

describe("DeptMembersPanel", () => {
  it("未选中部门:空态提示,不渲染表格", () => {
    render(<DeptMembersPanel {...baseProps} dept={null} members={[]} total={0} />);
    expect(screen.getByText("请选择左侧部门查看成员")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("渲染成员行(姓名/邮箱/角色/状态)", () => {
    render(<DeptMembersPanel {...baseProps} />);
    expect(screen.getByText("张三")).toBeInTheDocument();
    expect(screen.getByText("a@x.com")).toBeInTheDocument();
    expect(screen.getByText("普通员工")).toBeInTheDocument();
    expect(screen.getByText("启用")).toBeInTheDocument();
  });

  it("error(含 403):Alert 展示,不白屏", () => {
    render(<DeptMembersPanel {...baseProps} error="无权查看该部门成员" />);
    expect(screen.getByText("无权查看该部门成员")).toBeInTheDocument();
  });

  it("翻页回调", async () => {
    const onPageChange = vi.fn();
    render(<DeptMembersPanel {...baseProps} total={40} onPageChange={onPageChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByTitle("2"));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });
});
