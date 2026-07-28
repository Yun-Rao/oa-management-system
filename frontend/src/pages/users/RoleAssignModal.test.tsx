import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/roles", () => ({ listRoles: vi.fn() }));
vi.mock("../../api/users", () => ({ assignRoles: vi.fn() }));

import { ApiError } from "../../api/client";
import { listRoles } from "../../api/roles";
import { assignRoles } from "../../api/users";
import type { RoleResponse, UserResponse } from "../../types/api";
import RoleAssignModal from "./RoleAssignModal";

const roles: RoleResponse[] = [
  { code: "admin", name: "管理员", description: null, permissions: [] },
  { code: "employee", name: "普通员工", description: null, permissions: [] },
];

const target: UserResponse = {
  id: "u1",
  email: "a@x.com",
  name: "张三",
  is_active: true,
  roles: [{ code: "employee", name: "普通员工" }],
  department: null,
  manager: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listRoles).mockResolvedValue(roles);
});

describe("RoleAssignModal", () => {
  it("打开时拉取角色并初始勾选现有角色", async () => {
    render(<RoleAssignModal user={target} onClose={() => {}} onSuccess={() => {}} />);
    const employee = await screen.findByRole("checkbox", { name: /普通员工/ });
    const admin = screen.getByRole("checkbox", { name: /管理员/ });
    expect(employee).toBeChecked();
    expect(admin).not.toBeChecked();
  });

  it("保存:assignRoles 传整体替换后的 code 数组", async () => {
    vi.mocked(assignRoles).mockResolvedValue(target);
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    render(<RoleAssignModal user={target} onClose={onClose} onSuccess={onSuccess} />);
    const user = userEvent.setup();
    await screen.findByRole("checkbox", { name: /普通员工/ });
    await user.click(screen.getByRole("checkbox", { name: /管理员/ }));
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() => expect(assignRoles).toHaveBeenCalledOnce());
    const [id, codes] = vi.mocked(assignRoles).mock.calls[0];
    expect(id).toBe("u1");
    expect([...codes].sort()).toEqual(["admin", "employee"]);
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("保存失败:显示 ApiError.message,不关闭", async () => {
    vi.mocked(assignRoles).mockRejectedValue(new ApiError("FORBIDDEN", "无权限"));
    const onClose = vi.fn();
    render(<RoleAssignModal user={target} onClose={onClose} onSuccess={() => {}} />);
    const user = userEvent.setup();
    await screen.findByRole("checkbox", { name: /普通员工/ });
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("无权限")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
