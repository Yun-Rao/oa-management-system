import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TOKEN_KEY } from "../api/client";
import { useAuthStore } from "../store/auth";
import type { CurrentUser } from "../types/api";
import RequireAuth from "./RequireAuth";

const originalFetchMe = useAuthStore.getState().fetchMe;
const originalLogout = useAuthStore.getState().logout;

const mockUser: CurrentUser = {
  id: "u1",
  email: "a@x.com",
  name: "张三",
  is_active: true,
  roles: [{ code: "employee", name: "员工" }],
  department: null,
  manager: null,
  permissions: ["leave:create"],
};

function renderProtected(initialEntries: string[] = ["/"], strict = false) {
  const tree = (
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path="/login" element={<div>登录页占位</div>} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <div>受保护内容</div>
            </RequireAuth>
          }
        />
      </Routes>
    </MemoryRouter>
  );
  return render(strict ? <React.StrictMode>{tree}</React.StrictMode> : tree);
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({
    token: null,
    user: null,
    fetchMe: originalFetchMe,
    logout: originalLogout,
  });
});

describe("RequireAuth", () => {
  it("StrictMode 下 token 有、user 无:fetchMe 完成后渲染子内容(竞态回归)", async () => {
    // 模拟真实 fetchMe 流程:先挂起,释放后同步写入 user 再 resolve,
    // 与 store 中 `const user = await getMe(); set({ user })` 的微任务次序一致。
    let releaseFetch!: () => void;
    const gate = new Promise<void>((resolve) => {
      releaseFetch = resolve;
    });
    const fetchMe = vi.fn().mockImplementation(async () => {
      await gate;
      useAuthStore.setState({ user: mockUser });
    });
    useAuthStore.setState({ token: "tok", fetchMe });

    renderProtected(["/"], true);
    expect(fetchMe).toHaveBeenCalled();

    await act(async () => {
      releaseFetch();
    });

    expect(await screen.findByText("受保护内容")).toBeInTheDocument();
  });

  it("无 token:重定向到 /login", () => {
    renderProtected();
    expect(screen.getByText("登录页占位")).toBeInTheDocument();
    expect(screen.queryByText("受保护内容")).not.toBeInTheDocument();
  });

  it("token + user 均在:立即渲染子内容且不调用 fetchMe", () => {
    const fetchMe = vi.fn();
    useAuthStore.setState({ token: "tok", user: mockUser, fetchMe });
    renderProtected();
    expect(screen.getByText("受保护内容")).toBeInTheDocument();
    expect(fetchMe).not.toHaveBeenCalled();
  });

  it("fetchMe 失败:调用 logout 并跳转 /login", async () => {
    const fetchMe = vi.fn().mockRejectedValue(new Error("401"));
    const logout = vi.fn().mockImplementation(() => {
      localStorage.removeItem(TOKEN_KEY);
      useAuthStore.setState({ token: null, user: null });
    });
    useAuthStore.setState({ token: "tok", fetchMe, logout });

    renderProtected();
    await waitFor(() => expect(logout).toHaveBeenCalled());
    expect(await screen.findByText("登录页占位")).toBeInTheDocument();
  });
});
