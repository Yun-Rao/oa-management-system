import MockAdapter from "axios-mock-adapter";
import { beforeEach, describe, expect, it } from "vitest";

import { client } from "./client";
import { assignRoles, createUser, listUsers, setUserStatus, updateUser, updateUserOrg } from "./users";

const mock = new MockAdapter(client);

beforeEach(() => {
  localStorage.clear();
  mock.reset();
});

describe("users api", () => {
  it("listUsers:GET /users 带分页与关键字参数", async () => {
    const body = { items: [], total: 0, page: 1, page_size: 20 };
    mock.onGet("/users").reply((config) => {
      expect(config.params).toEqual({ page: 1, page_size: 20, keyword: "张" });
      return [200, body];
    });
    const data = await listUsers({ page: 1, page_size: 20, keyword: "张" });
    expect(data).toEqual(body);
  });

  it("listUsers:无关键字时不传 keyword 参数", async () => {
    mock.onGet("/users").reply((config) => {
      expect(config.params).toEqual({ page: 2, page_size: 20 });
      return [200, { items: [], total: 0, page: 2, page_size: 20 }];
    });
    await listUsers({ page: 2, page_size: 20 });
  });

  it("createUser:POST /users", async () => {
    mock.onPost("/users").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({
        email: "a@x.com",
        name: "张三",
        password: "Passw0rd!",
      });
      return [200, { id: "u1" }];
    });
    await createUser({ email: "a@x.com", name: "张三", password: "Passw0rd!" });
  });

  it("updateUser:PATCH /users/{id}", async () => {
    mock.onPatch("/users/u1").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({ email: "b@x.com", name: "李四" });
      return [200, { id: "u1" }];
    });
    await updateUser("u1", { email: "b@x.com", name: "李四" });
  });

  it("setUserStatus:PATCH /users/{id}/status", async () => {
    mock.onPatch("/users/u1/status").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({ is_active: false });
      return [200, { id: "u1" }];
    });
    await setUserStatus("u1", false);
  });

  it("assignRoles:PUT /users/{id}/roles 整体替换", async () => {
    mock.onPut("/users/u1/roles").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({ role_codes: ["admin", "employee"] });
      return [200, { id: "u1" }];
    });
    await assignRoles("u1", ["admin", "employee"]);
  });

  it("错误信封透传为 ApiError", async () => {
    mock.onGet("/users").reply(403, { error: { code: "FORBIDDEN", message: "无权限" } });
    const err = await listUsers({ page: 1, page_size: 20 }).catch((e: unknown) => e);
    expect(err).toMatchObject({ code: "FORBIDDEN", message: "无权限" });
  });
});

describe("users api updateUserOrg", () => {
  it("PATCH /users/{id}/org 传部门与上级", async () => {
    mock.onPatch("/users/u1/org").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({
        department_id: "d1",
        manager_id: "u2",
      });
      return [200, { id: "u1" }];
    });
    await updateUserOrg("u1", { department_id: "d1", manager_id: "u2" });
  });

  it("PATCH /users/{id}/org 清空语义(null)", async () => {
    mock.onPatch("/users/u1/org").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({
        department_id: null,
        manager_id: null,
      });
      return [200, { id: "u1" }];
    });
    await updateUserOrg("u1", { department_id: null, manager_id: null });
  });
});
