import MockAdapter from "axios-mock-adapter";
import { beforeEach, describe, expect, it } from "vitest";

import { client } from "./client";
import {
  createDepartment,
  deleteDepartment,
  listDeptMembers,
  listDeptTree,
  updateDepartment,
} from "./departments";

const mock = new MockAdapter(client);

beforeEach(() => {
  localStorage.clear();
  mock.reset();
});

describe("departments api", () => {
  it("listDeptTree:GET /departments 返回嵌套树", async () => {
    const tree = [
      {
        id: "d1",
        name: "技术部",
        parent_id: null,
        member_count: 3,
        children: [
          { id: "d2", name: "前端组", parent_id: "d1", member_count: 1, children: [] },
        ],
      },
    ];
    mock.onGet("/departments").reply(200, tree);
    const data = await listDeptTree();
    expect(data).toEqual(tree);
  });

  it("createDepartment:POST /departments 仅名称(根部门)", async () => {
    mock.onPost("/departments").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({ name: "市场部" });
      return [201, { id: "d3", name: "市场部", parent_id: null }];
    });
    const data = await createDepartment({ name: "市场部" });
    expect(data).toEqual({ id: "d3", name: "市场部", parent_id: null });
  });

  it("createDepartment:POST /departments 带 parent_id(子部门)", async () => {
    mock.onPost("/departments").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({ name: "后端组", parent_id: "d1" });
      return [201, { id: "d4", name: "后端组", parent_id: "d1" }];
    });
    await createDepartment({ name: "后端组", parent_id: "d1" });
  });

  it("updateDepartment:PATCH /departments/{id} 改名", async () => {
    mock.onPatch("/departments/d1").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({ name: "研发部" });
      return [200, { id: "d1", name: "研发部", parent_id: null }];
    });
    await updateDepartment("d1", { name: "研发部" });
  });

  it("updateDepartment:PATCH /departments/{id} 移动(parent_id 可为 null=根)", async () => {
    mock.onPatch("/departments/d2").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({ parent_id: null });
      return [200, { id: "d2", name: "前端组", parent_id: null }];
    });
    await updateDepartment("d2", { parent_id: null });
  });

  it("deleteDepartment:DELETE /departments/{id}", async () => {
    mock.onDelete("/departments/d9").reply(204);
    await expect(deleteDepartment("d9")).resolves.toBeUndefined();
  });

  it("listDeptMembers:GET /departments/{id}/members 带分页参数", async () => {
    const body = { items: [], total: 0, page: 2, page_size: 20 };
    mock.onGet("/departments/d1/members").reply((config) => {
      expect(config.params).toEqual({ page: 2, page_size: 20 });
      return [200, body];
    });
    const data = await listDeptMembers("d1", { page: 2, page_size: 20 });
    expect(data).toEqual(body);
  });

  it("错误信封透传为 ApiError(409 同级重名)", async () => {
    mock.onPost("/departments").reply(409, {
      error: { code: "CONFLICT", message: "同级下已存在同名部门" },
    });
    const err = await createDepartment({ name: "技术部" }).catch((e: unknown) => e);
    expect(err).toMatchObject({ code: "CONFLICT", message: "同级下已存在同名部门" });
  });
});
