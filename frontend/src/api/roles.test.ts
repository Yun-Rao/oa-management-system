import MockAdapter from "axios-mock-adapter";
import { beforeEach, describe, expect, it } from "vitest";

import { changePassword } from "./auth";
import { client } from "./client";
import { listRoles } from "./roles";

const mock = new MockAdapter(client);

beforeEach(() => {
  localStorage.clear();
  mock.reset();
});

describe("roles api", () => {
  it("listRoles:GET /roles 返回数组", async () => {
    const roles = [
      { code: "admin", name: "管理员", description: null, permissions: [{ code: "user:list", name: "用户列表" }] },
    ];
    mock.onGet("/roles").reply(200, roles);
    const data = await listRoles();
    expect(data).toEqual(roles);
  });
});

describe("auth api changePassword", () => {
  it("POST /auth/change-password 传 snake_case 字段", async () => {
    mock.onPost("/auth/change-password").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({
        old_password: "Old12345",
        new_password: "New12345",
      });
      return [204];
    });
    await changePassword("Old12345", "New12345");
  });
});
