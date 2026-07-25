import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { useAuthStore } from "../store/auth";
import LoginPage from "./LoginPage";

const originalLogin = useAuthStore.getState().login;

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div>首页占位</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ token: null, user: null, login: originalLogin });
});

describe("LoginPage", () => {
  it("已登录(token 存在)直接跳首页", () => {
    useAuthStore.setState({ token: "tok" });
    renderLogin();
    expect(screen.getByText("首页占位")).toBeInTheDocument();
  });

  it("提交成功:调用 login 并跳首页", async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    useAuthStore.setState({ login });
    renderLogin();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("邮箱"), "a@x.com");
    await user.type(screen.getByLabelText("密码"), "Passw0rd!");
    await user.click(screen.getByRole("button", { name: "登 录" }));
    await waitFor(() => expect(screen.getByText("首页占位")).toBeInTheDocument());
    expect(login).toHaveBeenCalledWith("a@x.com", "Passw0rd!");
  });

  it("登录失败:显示 ApiError.message,不跳转", async () => {
    const login = vi.fn().mockRejectedValue(new ApiError("INVALID_CREDENTIALS", "邮箱或密码错误"));
    useAuthStore.setState({ login });
    renderLogin();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("邮箱"), "a@x.com");
    await user.type(screen.getByLabelText("密码"), "bad");
    await user.click(screen.getByRole("button", { name: "登 录" }));
    expect(await screen.findByText("邮箱或密码错误")).toBeInTheDocument();
    expect(screen.queryByText("首页占位")).not.toBeInTheDocument();
  });

  it("空表单提交:不调用 login", async () => {
    const login = vi.fn();
    useAuthStore.setState({ login });
    renderLogin();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "登 录" }));
    expect(await screen.findByText("请输入邮箱")).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });
});
