import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/auth", () => ({
  changePassword: vi.fn(),
}));

import { changePassword } from "../api/auth";
import { ApiError } from "../api/client";
import ChangePasswordModal from "./ChangePasswordModal";

beforeEach(() => {
  vi.clearAllMocks();
});

async function fillForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("旧密码"), "Old12345");
  await user.type(screen.getByLabelText("新密码"), "New12345");
  await user.type(screen.getByLabelText("确认新密码"), "New12345");
}

describe("ChangePasswordModal", () => {
  it("确认密码不一致:不发起请求", async () => {
    render(<ChangePasswordModal open onClose={() => {}} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("旧密码"), "Old12345");
    await user.type(screen.getByLabelText("新密码"), "New12345");
    await user.type(screen.getByLabelText("确认新密码"), "Different1");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("两次输入的密码不一致")).toBeInTheDocument();
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("成功:以 snake_case 语义调用 changePassword 并关闭", async () => {
    vi.mocked(changePassword).mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(<ChangePasswordModal open onClose={onClose} />);
    const user = userEvent.setup();
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() => expect(changePassword).toHaveBeenCalledWith("Old12345", "New12345"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("失败(旧密码错误):显示 ApiError.message,不关闭", async () => {
    vi.mocked(changePassword).mockRejectedValue(new ApiError("INVALID_PASSWORD", "旧密码错误"));
    const onClose = vi.fn();
    render(<ChangePasswordModal open onClose={onClose} />);
    const user = userEvent.setup();
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("旧密码错误")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
