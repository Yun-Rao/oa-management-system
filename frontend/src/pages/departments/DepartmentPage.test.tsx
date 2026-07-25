import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/departments", () => ({
  listDeptTree: vi.fn(),
  createDepartment: vi.fn(),
  updateDepartment: vi.fn(),
  deleteDepartment: vi.fn(),
  listDeptMembers: vi.fn(),
}));

import { deleteDepartment, listDeptMembers, listDeptTree } from "../../api/departments";
import { useAuthStore } from "../../store/auth";
import type { CurrentUser, DepartmentNode, UserResponse } from "../../types/api";
import DepartmentPage from "./DepartmentPage";

const adminUser: CurrentUser = {
  id: "a1",
  email: "admin@x.com",
  name: "管理员",
  is_active: true,
  roles: [{ code: "admin", name: "管理员" }],
  department: null,
  manager: null,
  permissions: [
    "department:list",
    "department:members",
    "department:create",
    "department:update",
    "department:delete",
  ],
};

const tree: DepartmentNode[] = [
  {
    id: "d1",
    name: "技术部",
    parent_id: null,
    member_count: 1,
    children: [{ id: "d2", name: "前端组", parent_id: "d1", member_count: 0, children: [] }],
  },
  { id: "d5", name: "市场部", parent_id: null, member_count: 0, children: [] },
];

const member: UserResponse = {
  id: "u1",
  email: "a@x.com",
  name: "张三",
  is_active: true,
  roles: [],
  department: { id: "d1", name: "技术部" },
  manager: null,
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/departments"]}>
      <Routes>
        <Route path="/departments" element={<DepartmentPage />} />
        <Route path="/" element={<div>首页占位</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  useAuthStore.setState({ token: "tok", user: adminUser });
  vi.mocked(listDeptTree).mockResolvedValue(tree);
  vi.mocked(listDeptMembers).mockResolvedValue({ items: [member], total: 1, page: 1, page_size: 20 });
});

describe("DepartmentPage", () => {
  it("无 department:list 权限:跳回首页", () => {
    useAuthStore.setState({ user: { ...adminUser, permissions: [] } });
    renderPage();
    expect(screen.getByText("首页占位")).toBeInTheDocument();
    expect(listDeptTree).not.toHaveBeenCalled();
  });

  it("树渲染,默认选中第一个根部门并拉取其成员", async () => {
    renderPage();
    expect(await screen.findByText("技术部(1)")).toBeInTheDocument();
    expect(screen.getByText("前端组(0)")).toBeInTheDocument();
    await waitFor(() =>
      expect(listDeptMembers).toHaveBeenCalledWith("d1", { page: 1, page_size: 20 })
    );
    expect(await screen.findByText("张三")).toBeInTheDocument();
  });

  it("切换选中部门:重新拉取该部门成员", async () => {
    vi.mocked(listDeptMembers).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    renderPage();
    await screen.findByText("技术部(1)");
    const user = userEvent.setup();
    await user.click(screen.getByText("市场部(0)"));
    await waitFor(() =>
      expect(listDeptMembers).toHaveBeenCalledWith("d5", { page: 1, page_size: 20 })
    );
  });

  it("成员接口 403:Alert 展示不白屏", async () => {
    const { ApiError } = await import("../../api/client");
    vi.mocked(listDeptMembers).mockRejectedValue(new ApiError("FORBIDDEN", "无权查看该部门成员"));
    renderPage();
    expect(await screen.findByText("无权查看该部门成员")).toBeInTheDocument();
  });

  it("删除部门:调 deleteDepartment 并重新拉树", async () => {
    vi.mocked(deleteDepartment).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText("市场部(0)");
    const user = userEvent.setup();
    // 删除未选中的"市场部"(树顺序:技术部、前端组、市场部,删除按钮第 3 个)
    await user.click(screen.getAllByRole("button", { name: "删除部门" })[2]);
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    await waitFor(() => expect(deleteDepartment).toHaveBeenCalledWith("d5"));
    // 删除后重新拉树
    await waitFor(() => expect(listDeptTree).toHaveBeenCalledTimes(2));
  });
});
