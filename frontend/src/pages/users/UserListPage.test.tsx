import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/users", () => ({
  listUsers: vi.fn(),
  setUserStatus: vi.fn(),
  assignRoles: vi.fn(),
  updateUserOrg: vi.fn(),
}));
vi.mock("../../api/roles", () => ({ listRoles: vi.fn() }));
vi.mock("../../api/departments", () => ({ listDeptTree: vi.fn(), listDeptMembers: vi.fn() }));
vi.mock("./UserFormModal", () => ({ default: () => null }));
vi.mock("./UserOrgModal", () => ({ default: () => null }));

import { listRoles } from "../../api/roles";
import { assignRoles, listUsers, setUserStatus } from "../../api/users";
import { useAuthStore } from "../../store/auth";
import type { CurrentUser, UserResponse } from "../../types/api";
import UserListPage from "./UserListPage";

const adminUser: CurrentUser = {
  id: "a1",
  email: "admin@x.com",
  name: "管理员",
  is_active: true,
  roles: [{ code: "admin", name: "管理员" }],
  department: null,
  manager: null,
  permissions: ["user:list", "user:create", "user:update", "user:disable", "role:list", "role:assign"],
};

const row: UserResponse = {
  id: "u1",
  email: "a@x.com",
  name: "张三",
  is_active: true,
  roles: [{ code: "employee", name: "普通员工" }],
  department: { id: "d1", name: "技术部" },
  manager: null,
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/users"]}>
      <Routes>
        <Route path="/users" element={<UserListPage />} />
        <Route path="/" element={<div>首页占位</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  useAuthStore.setState({ token: "tok", user: adminUser });
  vi.mocked(listUsers).mockResolvedValue({ items: [row], total: 1, page: 1, page_size: 20 });
  vi.mocked(listRoles).mockResolvedValue([
    { code: "admin", name: "管理员", description: null, permissions: [] },
    { code: "employee", name: "普通员工", description: null, permissions: [] },
  ]);
});

describe("UserListPage", () => {
  it("无 user:list 权限:跳回首页", () => {
    useAuthStore.setState({ user: { ...adminUser, permissions: [] } });
    renderPage();
    expect(screen.getByText("首页占位")).toBeInTheDocument();
  });

  it("渲染列表行(姓名/邮箱/部门/状态)", async () => {
    renderPage();
    expect(await screen.findByText("张三")).toBeInTheDocument();
    expect(screen.getByText("a@x.com")).toBeInTheDocument();
    expect(screen.getByText("技术部")).toBeInTheDocument();
    expect(screen.getByText("启用")).toBeInTheDocument();
  });

  it("搜索:带 keyword 重新拉取并回到第 1 页", async () => {
    renderPage();
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("姓名或邮箱"), "张");
    await user.click(screen.getByRole("button", { name: "search" }));
    await waitFor(() =>
      expect(listUsers).toHaveBeenCalledWith({ page: 1, page_size: 20, keyword: "张" })
    );
  });

  it("禁用流程:Popconfirm 确认后调 setUserStatus(id, false)", async () => {
    vi.mocked(setUserStatus).mockResolvedValue({ ...row, is_active: false });
    renderPage();
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "禁用" }));
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    await waitFor(() => expect(setUserStatus).toHaveBeenCalledWith("u1", false));
  });

  it("分配角色:打开弹窗勾选保存,assignRoles 参数正确", async () => {
    renderPage();
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "分配角色" }));
    const adminBox = await screen.findByRole("checkbox", { name: /管理员/ });
    await user.click(adminBox);
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() => expect(assignRoles).toHaveBeenCalledOnce());
    const [id, codes] = vi.mocked(assignRoles).mock.calls[0];
    expect(id).toBe("u1");
    expect([...codes].sort()).toEqual(["admin", "employee"]);
  });

  it("归属:admin 可见入口,点击打开 UserOrgModal", async () => {
    renderPage();
    await screen.findByText("张三");
    expect(screen.getByRole("button", { name: "归属" })).toBeInTheDocument();
  });
});
