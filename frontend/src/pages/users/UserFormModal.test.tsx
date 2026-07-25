import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/users", () => ({
  createUser: vi.fn(),
  updateUser: vi.fn(),
}));

import { createUser, updateUser } from "../../api/users";
import { ApiError } from "../../api/client";
import type { UserResponse } from "../../types/api";
import UserFormModal from "./UserFormModal";

const editingUser: UserResponse = {
  id: "u1",
  email: "a@x.com",
  name: "张三",
  is_active: true,
  roles: [],
  department: null,
  manager: null,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("UserFormModal 创建模式", () => {
  it("空表单提交:不发起请求", async () => {
    render(<UserFormModal open editing={null} onClose={() => {}} onSuccess={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("请输入邮箱")).toBeInTheDocument();
    expect(createUser).not.toHaveBeenCalled();
  });

  it("提交:createUser 参数正确并触发 onSuccess/onClose", async () => {
    vi.mocked(createUser).mockResolvedValue(editingUser);
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    render(<UserFormModal open editing={null} onClose={onClose} onSuccess={onSuccess} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("邮箱"), "new@x.com");
    await user.type(screen.getByLabelText("姓名"), "新用户");
    await user.type(screen.getByLabelText("初始密码"), "Passw0rd!");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() =>
      expect(createUser).toHaveBeenCalledWith({
        email: "new@x.com",
        name: "新用户",
        password: "Passw0rd!",
      })
    );
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});

describe("UserFormModal 编辑模式", () => {
  it("预填邮箱姓名、无密码字段,提交调 updateUser", async () => {
    vi.mocked(updateUser).mockResolvedValue(editingUser);
    render(<UserFormModal open editing={editingUser} onClose={() => {}} onSuccess={() => {}} />);
    expect(screen.getByLabelText("邮箱")).toHaveValue("a@x.com");
    expect(screen.getByLabelText("姓名")).toHaveValue("张三");
    expect(screen.queryByLabelText("初始密码")).not.toBeInTheDocument();
    const user = userEvent.setup();
    await user.clear(screen.getByLabelText("姓名"));
    await user.type(screen.getByLabelText("姓名"), "张三丰");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() =>
      expect(updateUser).toHaveBeenCalledWith("u1", { email: "a@x.com", name: "张三丰" })
    );
  });

  it("失败(邮箱重复):显示 ApiError.message,不关闭", async () => {
    vi.mocked(updateUser).mockRejectedValue(new ApiError("EMAIL_TAKEN", "邮箱已被使用"));
    const onClose = vi.fn();
    render(<UserFormModal open editing={editingUser} onClose={onClose} onSuccess={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("邮箱已被使用")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
