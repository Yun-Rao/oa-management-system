import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, TOKEN_KEY } from "../api/client";
import type { CurrentUser } from "../types/api";

vi.mock("../api/auth", () => ({
  login: vi.fn(),
  getMe: vi.fn(),
}));

import * as authApi from "../api/auth";
import { useAuthStore } from "./auth";

const mockUser: CurrentUser = {
  id: "u1",
  email: "a@x.com",
  name: "张三",
  is_active: true,
  roles: [{ code: "employee", name: "员工" }],
  department: null,
  manager: null,
  permissions: ["leave:create", "leave:list"],
};

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ token: null, user: null });
  vi.clearAllMocks();
});

describe("login", () => {
  it("成功:写入 localStorage 与 store,并拉取当前用户", async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: "tok",
      token_type: "bearer",
      expires_in: 86400,
    });
    vi.mocked(authApi.getMe).mockResolvedValue(mockUser);
    await useAuthStore.getState().login("a@x.com", "Passw0rd!");
    const s = useAuthStore.getState();
    expect(s.token).toBe("tok");
    expect(localStorage.getItem(TOKEN_KEY)).toBe("tok");
    expect(s.user?.name).toBe("张三");
  });

  it("失败:抛 ApiError 且不写 token", async () => {
    vi.mocked(authApi.login).mockRejectedValue(
      new ApiError("INVALID_CREDENTIALS", "邮箱或密码错误")
    );
    await expect(
      useAuthStore.getState().login("a@x.com", "bad")
    ).rejects.toMatchObject({ code: "INVALID_CREDENTIALS" });
    expect(useAuthStore.getState().token).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});

describe("fetchMe", () => {
  it("填充 user", async () => {
    vi.mocked(authApi.getMe).mockResolvedValue(mockUser);
    await useAuthStore.getState().fetchMe();
    expect(useAuthStore.getState().user?.email).toBe("a@x.com");
  });
});

describe("logout", () => {
  it("清空 store 与 localStorage", () => {
    localStorage.setItem(TOKEN_KEY, "tok");
    useAuthStore.setState({ token: "tok", user: mockUser });
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});

describe("hasPermission", () => {
  it("命中返回 true,未命中或无用户返回 false", () => {
    useAuthStore.setState({ user: mockUser });
    expect(useAuthStore.getState().hasPermission("leave:create")).toBe(true);
    expect(useAuthStore.getState().hasPermission("leave:list_all")).toBe(false);
    useAuthStore.setState({ user: null });
    expect(useAuthStore.getState().hasPermission("leave:create")).toBe(false);
  });
});
