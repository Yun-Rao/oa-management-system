import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, TOKEN_KEY, client, navigation, onUnauthorized } from "./client";

const mock = new MockAdapter(client);

beforeEach(() => {
  localStorage.clear();
  mock.reset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("请求拦截器", () => {
  it("有 token 时携带 Authorization 头", async () => {
    localStorage.setItem(TOKEN_KEY, "tok");
    mock.onGet("/x").reply((config) => [200, { auth: config.headers?.Authorization ?? null }]);
    const { data } = await client.get("/x");
    expect(data.auth).toBe("Bearer tok");
  });

  it("无 token 时不带 Authorization 头", async () => {
    mock.onGet("/x").reply((config) => [200, { auth: config.headers?.Authorization ?? null }]);
    const { data } = await client.get("/x");
    expect(data.auth).toBeNull();
  });
});

describe("响应拦截器", () => {
  it("业务错误信封解析为 ApiError(code, message)", async () => {
    mock.onGet("/x").reply(404, { error: { code: "NOT_FOUND", message: "用户不存在" } });
    const err = await client.get("/x").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("NOT_FOUND");
    expect(err.message).toBe("用户不存在");
  });

  it("非信封错误归为 UNKNOWN", async () => {
    mock.onGet("/x").reply(500, { detail: "boom" });
    const err = await client.get("/x").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("UNKNOWN");
    expect(err.message).toBe("网络异常,请稍后重试");
  });

  it("401:清 token、触发 onUnauthorized 回调、跳登录页", async () => {
    localStorage.setItem(TOKEN_KEY, "tok");
    const handler = vi.fn();
    onUnauthorized(handler);
    const nav = vi.spyOn(navigation, "toLogin").mockImplementation(() => {});
    mock.onGet("/users").reply(401, { error: { code: "UNAUTHORIZED", message: "未认证" } });
    await client.get("/users").catch(() => {});
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(handler).toHaveBeenCalledOnce();
    expect(nav).toHaveBeenCalledOnce();
  });

  it("登录接口自身的 401 不跳转", async () => {
    const nav = vi.spyOn(navigation, "toLogin").mockImplementation(() => {});
    mock
      .onPost("/auth/login")
      .reply(401, { error: { code: "INVALID_CREDENTIALS", message: "邮箱或密码错误" } });
    await client.post("/auth/login", {}).catch(() => {});
    expect(nav).not.toHaveBeenCalled();
  });
});
