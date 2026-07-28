# 前端 P0#2 组织架构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在前端地基与 P0#1 之上实现 P0#2 组织架构前端:部门管理页(左树右表,部门 CRUD + 成员列表)、用户管理"归属"操作(设置部门与直属上级),并以组件级测试与浏览器实测验收。

**Architecture:** 页面内 `useState`+`useEffect` 管服务器数据(无新运行时依赖);api 层纯函数走地基统一 axios client;AntD Tree / TreeSelect / Table + Modal 标准交互;React Testing Library 做组件级测试;验收由执行 Agent 用 chrome-devtools 驱动真实浏览器逐场景截图。

**Tech Stack:** React 18 + TS(strict) + AntD 5.29 + Zustand + React Router 6 + Vitest + @testing-library/react + axios-mock-adapter

**Spec:** `docs/superpowers/specs/2026-07-25-frontend-org-structure-design.md`(验收标准见 §8)

## Global Constraints

- 每步 TDD:先写失败测试 → 确认失败 → 实现 → 确认通过 → 提交
- 提交只 `git add` 明确列出的文件,**严禁** `git add .` / `git add -A`
- 所有 npm/npx/vitest 命令在 `frontend/` 目录下执行;git 命令在仓库根执行;Shell 为 git bash(Windows),用 Unix 语法
- 设计决策级变更必须同步 spec;实现细节修复不动 spec
- 不修改 `backend/` 下任何文件
- api 层不做 try/catch;错误信封由 `client` 拦截器统一转 `ApiError(code, message)`,页面层捕获后取 `e.message`
- 组件成功提示用 antd 静态 `message.success/error`(可接受无上下文警告)
- antd `Modal` 用 `destroyOnHidden`(5.25+ 替代已废弃的 `destroyOnClose`);编辑类表单回填用 Form `initialValues` + `key={editing?.id ?? "new"}` 重挂载(**禁止** `useEffect` 里 `setFieldsValue`,destroyOnHidden 下会丢值,见 P0#1 验收教训)
- 后端接口契约(以 `backend/app/schemas`、`backend/app/api/v1/departments.py` 为准,TS 类型严格对齐):
  - `POST /departments {name(1-100), parent_id?}` → 201 `DepartmentResponse{id, name, parent_id}`
  - `GET /departments` → `DepartmentNode[]` 嵌套树(`{id, name, parent_id, member_count, children[]}`)
  - `PATCH /departments/{id} {name?, parent_id?}` → `DepartmentResponse`(`parent_id: null` = 设为根部门)
  - `DELETE /departments/{id}` → 204 无响应体
  - `GET /departments/{id}/members?page&page_size` → `UserListResponse`(同 P0#1 `{items: UserResponse[], total, page, page_size}`)
  - `PATCH /users/{id}/org {department_id?, manager_id?}` → `UserResponse`
  - 权限:department:create/update/delete 仅 admin;department:list、department:members admin+manager(manager 仅本部门成员,越权 403);`PATCH /users/{id}/org` 需 user:update
  - 错误:同级重名/有员工或子部门禁删/移动成环 → 409;上级校验 → 422;越权 → 403;前端统一展示 `e.message`,不做 code 分支
- Seed 账号:admin `admin@company.com` / `Admin123!`;seed **不创建**任何部门与 manager 账号(验收场景自行创建);既有验收账号 `demo.user@company.com` / `DemoNew123!`(李演示2,employee)、`e2e.emp@company.com` / `NewEmp123!`(张测试2,employee)可复用
- 本机 vite 代理需 `NODE_OPTIONS=--dns-result-order=ipv4first`
- 浏览器实测**严禁禁用 admin 账号**;chrome-devtools `fill` 对已含值输入框是追加而非替换,替换文本用 click → Control+A → `type_text`

---

## Task 1: 类型追加 + api 层(departments / updateUserOrg)

**Files:**
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/src/api/departments.ts`
- Modify: `frontend/src/api/users.ts`
- Test: `frontend/src/api/departments.test.ts`
- Test: `frontend/src/api/users.test.ts`(追加)

**Interfaces:**
- Consumes: `client`、`ApiError`(地基 `api/client.ts`)、`UserListResponse`、`UserResponse`(既有 `types/api.ts`)
- Produces(后续任务依赖):
  - 类型 `DepartmentNode{id, name, parent_id: string|null, member_count: number, children: DepartmentNode[]}`、`DepartmentResponse{id, name, parent_id: string|null}`、`UserOrgUpdate{department_id?: string|null, manager_id?: string|null}`
  - `listDeptTree(): Promise<DepartmentNode[]>`
  - `createDepartment({name, parent_id?}): Promise<DepartmentResponse>`
  - `updateDepartment(id, {name?, parent_id?}): Promise<DepartmentResponse>`
  - `deleteDepartment(id): Promise<void>`
  - `listDeptMembers(id, {page, page_size}): Promise<UserListResponse>`
  - `updateUserOrg(id, body: UserOrgUpdate): Promise<UserResponse>`

- [ ] **Step 1: 写失败测试 `frontend/src/api/departments.test.ts`**

```ts
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
```

- [ ] **Step 2: 追加失败测试 `frontend/src/api/users.test.ts`**

在文件末尾 `describe("users api", ...)` 之后追加一个 describe(import 行改为 `import { assignRoles, createUser, listUsers, setUserStatus, updateUser, updateUserOrg } from "./users";`):

```ts
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
```

- [ ] **Step 3: 运行确认失败**

Run: `cd frontend && npx vitest run src/api/departments.test.ts src/api/users.test.ts`
Expected: FAIL,`Failed to resolve import "./departments"` 及 `updateUserOrg is not exported`

- [ ] **Step 4: 追加类型 `frontend/src/types/api.ts`**

文件末尾追加:

```ts
export interface DepartmentNode {
  id: string;
  name: string;
  parent_id: string | null;
  member_count: number;
  children: DepartmentNode[];
}

export interface DepartmentResponse {
  id: string;
  name: string;
  parent_id: string | null;
}

export interface UserOrgUpdate {
  department_id?: string | null;
  manager_id?: string | null;
}
```

- [ ] **Step 5: 创建 `frontend/src/api/departments.ts`**

```ts
import { client } from "./client";
import type { DepartmentNode, DepartmentResponse, UserListResponse } from "../types/api";

export async function listDeptTree(): Promise<DepartmentNode[]> {
  const { data } = await client.get<DepartmentNode[]>("/departments");
  return data;
}

export async function createDepartment(body: {
  name: string;
  parent_id?: string | null;
}): Promise<DepartmentResponse> {
  const { data } = await client.post<DepartmentResponse>("/departments", body);
  return data;
}

export async function updateDepartment(
  id: string,
  body: { name?: string; parent_id?: string | null }
): Promise<DepartmentResponse> {
  const { data } = await client.patch<DepartmentResponse>(`/departments/${id}`, body);
  return data;
}

export async function deleteDepartment(id: string): Promise<void> {
  await client.delete(`/departments/${id}`);
}

export async function listDeptMembers(
  id: string,
  params: { page: number; page_size: number }
): Promise<UserListResponse> {
  const { data } = await client.get<UserListResponse>(`/departments/${id}/members`, { params });
  return data;
}
```

- [ ] **Step 6: 追加 `updateUserOrg` 到 `frontend/src/api/users.ts`**

import 行加 `UserOrgUpdate` 类型,文件末尾追加:

```ts
export async function updateUserOrg(id: string, body: UserOrgUpdate): Promise<UserResponse> {
  const { data } = await client.patch<UserResponse>(`/users/${id}/org`, body);
  return data;
}
```

- [ ] **Step 7: 运行确认通过**

Run: `cd frontend && npx vitest run src/api/departments.test.ts src/api/users.test.ts && npm run typecheck`
Expected: 全部通过;typecheck 零错误

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/departments.ts frontend/src/api/users.ts frontend/src/api/departments.test.ts frontend/src/api/users.test.ts
git commit -m "feat(frontend): P0#2 组织架构 api 层与类型(departments CRUD/members、updateUserOrg)"
```

---

## Task 2: 部门树工具函数 + DeptFormModal(新建/编辑复用)

**Files:**
- Create: `frontend/src/utils/deptTree.ts`
- Test: `frontend/src/utils/deptTree.test.ts`
- Create: `frontend/src/pages/departments/DeptFormModal.tsx`
- Test: `frontend/src/pages/departments/DeptFormModal.test.tsx`

**Interfaces:**
- Consumes: `DepartmentNode`、`DepartmentResponse`(Task 1)、`createDepartment`、`updateDepartment`(Task 1)、`ApiError`
- Produces(后续任务依赖):
  - `toTreeSelectData(nodes: DepartmentNode[], excludeIds?: Set<string>): DeptTreeSelectNode[]`(`{value, title, children?}`,UserOrgModal 也复用)
  - `collectSubtreeIds(node: DepartmentNode): Set<string>`(含自身)
  - `findNode(nodes: DepartmentNode[], id: string): DepartmentNode | null`
  - `DeptFormModal` props:`{ open: boolean; tree: DepartmentNode[]; editing: DepartmentNode | null; presetParentId: string | null; onClose: () => void; onSuccess: () => void }`
    - `editing=null` 为新建,`presetParentId` 预填父部门(顶部"新建部门"入口传 null=根)
    - 新建提交:`createDepartment({name, ...(parent_id ? {parent_id} : {})})`
    - 编辑提交:`updateDepartment(editing.id, {name, parent_id: parent_id ?? null})`(清空=根,显式 null)

- [ ] **Step 1: 写失败测试 `frontend/src/utils/deptTree.test.ts`**

```ts
import { describe, expect, it } from "vitest";

import type { DepartmentNode } from "../types/api";
import { collectSubtreeIds, findNode, toTreeSelectData } from "./deptTree";

const tree: DepartmentNode[] = [
  {
    id: "d1",
    name: "技术部",
    parent_id: null,
    member_count: 3,
    children: [
      {
        id: "d2",
        name: "前端组",
        parent_id: "d1",
        member_count: 1,
        children: [{ id: "d4", name: "H5 小组", parent_id: "d2", member_count: 0, children: [] }],
      },
      { id: "d3", name: "后端组", parent_id: "d1", member_count: 2, children: [] },
    ],
  },
  { id: "d5", name: "市场部", parent_id: null, member_count: 5, children: [] },
];

describe("deptTree utils", () => {
  it("findNode:按 id 深度查找", () => {
    expect(findNode(tree, "d4")?.name).toBe("H5 小组");
    expect(findNode(tree, "d5")?.name).toBe("市场部");
    expect(findNode(tree, "nope")).toBeNull();
  });

  it("collectSubtreeIds:含自身与全部后代", () => {
    expect([...collectSubtreeIds(findNode(tree, "d1")!)].sort()).toEqual(["d1", "d2", "d3", "d4"]);
    expect([...collectSubtreeIds(findNode(tree, "d3")!)]).toEqual(["d3"]);
  });

  it("toTreeSelectData:转换为 TreeSelect 数据结构", () => {
    const data = toTreeSelectData(tree);
    expect(data).toHaveLength(2);
    expect(data[0]).toMatchObject({ value: "d1", title: "技术部" });
    expect(data[0].children?.[0]).toMatchObject({ value: "d2", title: "前端组" });
  });

  it("toTreeSelectData:excludeIds 排除自身及后代", () => {
    const data = toTreeSelectData(tree, collectSubtreeIds(findNode(tree, "d2")!));
    expect(data[0].children).toHaveLength(1);
    expect(data[0].children?.[0]).toMatchObject({ value: "d3", title: "后端组" });
    expect(JSON.stringify(data)).not.toContain("前端组");
    expect(JSON.stringify(data)).not.toContain("H5 小组");
  });
});
```

- [ ] **Step 2: 写失败测试 `frontend/src/pages/departments/DeptFormModal.test.tsx`**

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/departments", () => ({
  createDepartment: vi.fn(),
  updateDepartment: vi.fn(),
}));

import { ApiError } from "../../api/client";
import { createDepartment, updateDepartment } from "../../api/departments";
import type { DepartmentNode, DepartmentResponse } from "../../types/api";
import DeptFormModal from "./DeptFormModal";

const tree: DepartmentNode[] = [
  {
    id: "d1",
    name: "技术部",
    parent_id: null,
    member_count: 3,
    children: [{ id: "d2", name: "前端组", parent_id: "d1", member_count: 1, children: [] }],
  },
  { id: "d5", name: "市场部", parent_id: null, member_count: 5, children: [] },
];

const editingNode: DepartmentNode = tree[0];

const savedResp: DepartmentResponse = { id: "d1", name: "研发部", parent_id: null };

const baseProps = {
  tree,
  onClose: () => {},
  onSuccess: () => {},
};

beforeEach(() => {
  vi.clearAllMocks();
});

function parentFormItem() {
  return within(screen.getByText("父部门").closest(".ant-form-item") as HTMLElement);
}

describe("DeptFormModal 新建模式", () => {
  it("名称为空提交:校验提示,不发起请求", async () => {
    render(<DeptFormModal open {...baseProps} editing={null} presetParentId={null} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("请输入部门名称")).toBeInTheDocument();
    expect(createDepartment).not.toHaveBeenCalled();
  });

  it("提交(根部门):createDepartment 仅带 name", async () => {
    vi.mocked(createDepartment).mockResolvedValue(savedResp);
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    render(
      <DeptFormModal open tree={tree} editing={null} presetParentId={null} onClose={onClose} onSuccess={onSuccess} />
    );
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("部门名称"), "人事部");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() => expect(createDepartment).toHaveBeenCalledWith({ name: "人事部" }));
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("提交(预填父部门):createDepartment 带 parent_id", async () => {
    vi.mocked(createDepartment).mockResolvedValue(savedResp);
    render(<DeptFormModal open {...baseProps} editing={null} presetParentId="d1" />);
    // 预填父部门显示在 TreeSelect 选中项
    expect(parentFormItem().getByText("技术部")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("部门名称"), "测试组");
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() =>
      expect(createDepartment).toHaveBeenCalledWith({ name: "测试组", parent_id: "d1" })
    );
  });
});

describe("DeptFormModal 编辑模式", () => {
  it("预填名称与父部门;候选树排除自身及后代", async () => {
    render(<DeptFormModal open {...baseProps} editing={editingNode} presetParentId={null} />);
    expect(screen.getByLabelText("部门名称")).toHaveValue("技术部");
    const user = userEvent.setup();
    // 打开父部门 TreeSelect 下拉
    await user.click(parentFormItem().getByRole("combobox"));
    const dropdown = await screen.findByRole("tree");
    // 自身"技术部"与后代"前端组"被排除;"市场部"可选
    expect(within(dropdown).queryByText("技术部")).not.toBeInTheDocument();
    expect(within(dropdown).queryByText("前端组")).not.toBeInTheDocument();
    expect(within(dropdown).getByText("市场部")).toBeInTheDocument();
  });

  it("改父部门并提交:updateDepartment 带 name 与新 parent_id", async () => {
    vi.mocked(updateDepartment).mockResolvedValue(savedResp);
    render(<DeptFormModal open {...baseProps} editing={tree[0].children[0]} presetParentId={null} />);
    expect(screen.getByLabelText("部门名称")).toHaveValue("前端组");
    expect(parentFormItem().getByText("技术部")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(parentFormItem().getByRole("combobox"));
    const dropdown = await screen.findByRole("tree");
    await user.click(within(dropdown).getByText("市场部"));
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() =>
      expect(updateDepartment).toHaveBeenCalledWith("d2", { name: "前端组", parent_id: "d5" })
    );
  });

  it("清空父部门提交:parent_id 显式 null(设为根)", async () => {
    vi.mocked(updateDepartment).mockResolvedValue(savedResp);
    render(<DeptFormModal open {...baseProps} editing={tree[0].children[0]} presetParentId={null} />);
    const user = userEvent.setup();
    await user.click(parentFormItem().getByRole("combobox"));
    // 清空选择(TreeSelect allowClear 的清除图标)
    const item = parentFormItem().getByText("技术部").closest(".ant-select-selector") as HTMLElement;
    await user.hover(item);
    const clearIcon = item.parentElement!.querySelector(".ant-select-clear") as HTMLElement;
    await user.click(clearIcon);
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() =>
      expect(updateDepartment).toHaveBeenCalledWith("d2", { name: "前端组", parent_id: null })
    );
  });

  it("失败(同级重名 409):显示 ApiError.message,不关闭", async () => {
    vi.mocked(updateDepartment).mockRejectedValue(new ApiError("CONFLICT", "同级下已存在同名部门"));
    const onClose = vi.fn();
    render(
      <DeptFormModal open tree={tree} editing={editingNode} presetParentId={null} onClose={onClose} onSuccess={() => {}} />
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("同级下已存在同名部门")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: 运行确认失败**

Run: `cd frontend && npx vitest run src/utils/deptTree.test.ts src/pages/departments/DeptFormModal.test.tsx`
Expected: FAIL,`Failed to resolve import "./deptTree"` / `"./DeptFormModal"`

- [ ] **Step 4: 实现 `frontend/src/utils/deptTree.ts`**

```ts
import type { DepartmentNode } from "../types/api";

export interface DeptTreeSelectNode {
  value: string;
  title: string;
  children?: DeptTreeSelectNode[];
}

export function findNode(nodes: DepartmentNode[], id: string): DepartmentNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    const found = findNode(n.children, id);
    if (found) return found;
  }
  return null;
}

export function collectSubtreeIds(node: DepartmentNode): Set<string> {
  const ids = new Set<string>([node.id]);
  for (const child of node.children) {
    for (const id of collectSubtreeIds(child)) ids.add(id);
  }
  return ids;
}

export function toTreeSelectData(
  nodes: DepartmentNode[],
  excludeIds?: Set<string>
): DeptTreeSelectNode[] {
  return nodes
    .filter((n) => !excludeIds?.has(n.id))
    .map((n) => ({
      value: n.id,
      title: n.name,
      children: toTreeSelectData(n.children, excludeIds),
    }));
}
```

- [ ] **Step 5: 实现 `frontend/src/pages/departments/DeptFormModal.tsx`**

```tsx
import { useEffect, useMemo, useState } from "react";
import { Alert, Form, Input, Modal, TreeSelect } from "antd";

import { ApiError } from "../../api/client";
import { createDepartment, updateDepartment } from "../../api/departments";
import type { DepartmentNode } from "../../types/api";
import { collectSubtreeIds, findNode, toTreeSelectData } from "../../utils/deptTree";

interface Props {
  open: boolean;
  tree: DepartmentNode[];
  editing: DepartmentNode | null;
  presetParentId: string | null;
  onClose: () => void;
  onSuccess: () => void;
}

interface DeptFormValues {
  name: string;
  parent_id?: string;
}

export default function DeptFormModal({ open, tree, editing, presetParentId, onClose, onSuccess }: Props) {
  const [form] = Form.useForm<DeptFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) setError(null);
  }, [open]);

  const treeData = useMemo(() => {
    if (!editing) return toTreeSelectData(tree);
    const node = findNode(tree, editing.id);
    const exclude = node ? collectSubtreeIds(node) : undefined;
    return toTreeSelectData(tree, exclude);
  }, [tree, editing]);

  async function onFinish(values: DeptFormValues) {
    setSubmitting(true);
    setError(null);
    try {
      if (editing) {
        await updateDepartment(editing.id, {
          name: values.name,
          parent_id: values.parent_id ?? null,
        });
      } else {
        await createDepartment({
          name: values.name,
          ...(values.parent_id ? { parent_id: values.parent_id } : {}),
        });
      }
      onSuccess();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      title={editing ? "编辑部门" : "新建部门"}
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Form<DeptFormValues>
        key={editing ? editing.id : `new-${presetParentId ?? "root"}`}
        form={form}
        layout="vertical"
        onFinish={onFinish}
        preserve={false}
        initialValues={
          editing
            ? { name: editing.name, parent_id: editing.parent_id ?? undefined }
            : { parent_id: presetParentId ?? undefined }
        }
      >
        <Form.Item
          name="name"
          label="部门名称"
          rules={[
            { required: true, message: "请输入部门名称" },
            { max: 100, message: "部门名称最长 100 字" },
          ]}
        >
          <Input />
        </Form.Item>
        <Form.Item name="parent_id" label="父部门">
          <TreeSelect
            treeData={treeData}
            allowClear
            placeholder="不选则为根部门"
            treeDefaultExpandAll
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
```

- [ ] **Step 6: 运行确认通过**

Run: `cd frontend && npx vitest run src/utils/deptTree.test.ts src/pages/departments/DeptFormModal.test.tsx && npm run typecheck`
Expected: 全部通过;typecheck 零错误

- [ ] **Step 7: Commit**

```bash
git add frontend/src/utils/deptTree.ts frontend/src/utils/deptTree.test.ts frontend/src/pages/departments/DeptFormModal.tsx frontend/src/pages/departments/DeptFormModal.test.tsx
git commit -m "feat(frontend): P0#2 部门表单弹窗(新建/编辑复用,TreeSelect 选父部门防环)"
```

---

## Task 3: DeptTreePanel(部门树 + CRUD 入口)

**Files:**
- Create: `frontend/src/pages/departments/DeptTreePanel.tsx`
- Create: `frontend/src/pages/departments/dept.css`
- Test: `frontend/src/pages/departments/DeptTreePanel.test.tsx`

**Interfaces:**
- Consumes: `DepartmentNode`(Task 1)
- Produces(Task 5 依赖):`DeptTreePanel` props:
  ```ts
  {
    tree: DepartmentNode[];
    selectedId: string | null;
    canCreate: boolean;
    canUpdate: boolean;
    canDelete: boolean;
    onSelect: (id: string) => void;
    onCreateRoot: () => void;
    onCreateChild: (node: DepartmentNode) => void;
    onEdit: (node: DepartmentNode) => void;
    onDelete: (node: DepartmentNode) => void; // Popconfirm 确认后触发
  }
  ```

- [ ] **Step 1: 写失败测试 `frontend/src/pages/departments/DeptTreePanel.test.tsx`**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DepartmentNode } from "../../types/api";
import DeptTreePanel from "./DeptTreePanel";

const tree: DepartmentNode[] = [
  {
    id: "d1",
    name: "技术部",
    parent_id: null,
    member_count: 3,
    children: [{ id: "d2", name: "前端组", parent_id: "d1", member_count: 1, children: [] }],
  },
  { id: "d5", name: "市场部", parent_id: null, member_count: 5, children: [] },
];

const baseProps = {
  tree,
  selectedId: "d1" as string | null,
  onSelect: vi.fn(),
  onCreateRoot: vi.fn(),
  onCreateChild: vi.fn(),
  onEdit: vi.fn(),
  onDelete: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("DeptTreePanel", () => {
  it("渲染树节点(名称+member_count),默认展开", () => {
    render(<DeptTreePanel {...baseProps} canCreate canUpdate canDelete />);
    expect(screen.getByText("技术部(3)")).toBeInTheDocument();
    expect(screen.getByText("前端组(1)")).toBeInTheDocument();
    expect(screen.getByText("市场部(5)")).toBeInTheDocument();
  });

  it("点击节点触发 onSelect", async () => {
    render(<DeptTreePanel {...baseProps} canCreate canUpdate canDelete />);
    const user = userEvent.setup();
    await user.click(screen.getByText("市场部(5)"));
    expect(baseProps.onSelect).toHaveBeenCalledWith("d5");
  });

  it("有权限:顶部新建按钮 + 节点操作按钮;新建子部门回调带节点", async () => {
    render(<DeptTreePanel {...baseProps} canCreate canUpdate canDelete />);
    const user = userEvent.setup();
    expect(screen.getByRole("button", { name: "新建部门" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "新建部门" }));
    expect(baseProps.onCreateRoot).toHaveBeenCalled();
    // 每个节点 3 个操作按钮(aria-label)
    const addButtons = screen.getAllByRole("button", { name: "新建子部门" });
    expect(addButtons).toHaveLength(3);
    await user.click(addButtons[0]);
    expect(baseProps.onCreateChild).toHaveBeenCalledWith(tree[0]);
    await user.click(screen.getAllByRole("button", { name: "编辑部门" })[1]);
    expect(baseProps.onEdit).toHaveBeenCalledWith(tree[0].children[0]);
  });

  it("删除:Popconfirm 确认后回调带节点", async () => {
    render(<DeptTreePanel {...baseProps} canCreate canUpdate canDelete />);
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: "删除部门" })[0]);
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    expect(baseProps.onDelete).toHaveBeenCalledWith(tree[0]);
  });

  it("无权限(manager):全部 CRUD 按钮隐藏", () => {
    render(<DeptTreePanel {...baseProps} canCreate={false} canUpdate={false} canDelete={false} />);
    expect(screen.queryByRole("button", { name: "新建部门" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新建子部门" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "编辑部门" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "删除部门" })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/pages/departments/DeptTreePanel.test.tsx`
Expected: FAIL,`Failed to resolve import "./DeptTreePanel"`

- [ ] **Step 3: 实现 `frontend/src/pages/departments/dept.css`**

```css
.dept-tree-actions {
  visibility: hidden;
  margin-left: 8px;
}
.dept-tree-node:hover .dept-tree-actions {
  visibility: visible;
}
```

(vitest 默认不处理 css import,jsdom 中 `visibility:hidden` 不生效,测试可直接点击按钮;浏览器中悬停显现。)

- [ ] **Step 4: 实现 `frontend/src/pages/departments/DeptTreePanel.tsx`**

```tsx
import { Button, Popconfirm, Space, Tree } from "antd";
import type { TreeDataNode } from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { useMemo } from "react";

import type { DepartmentNode } from "../../types/api";
import "./dept.css";

interface Props {
  tree: DepartmentNode[];
  selectedId: string | null;
  canCreate: boolean;
  canUpdate: boolean;
  canDelete: boolean;
  onSelect: (id: string) => void;
  onCreateRoot: () => void;
  onCreateChild: (node: DepartmentNode) => void;
  onEdit: (node: DepartmentNode) => void;
  onDelete: (node: DepartmentNode) => void;
}

interface DeptTreeDataNode extends TreeDataNode {
  dept: DepartmentNode;
  children?: DeptTreeDataNode[];
}

export default function DeptTreePanel({
  tree,
  selectedId,
  canCreate,
  canUpdate,
  canDelete,
  onSelect,
  onCreateRoot,
  onCreateChild,
  onEdit,
  onDelete,
}: Props) {
  const treeData = useMemo<DeptTreeDataNode[]>(
    () =>
      tree.map(function convert(n): DeptTreeDataNode {
        return { key: n.id, title: n.name, dept: n, children: n.children.map(convert) };
      }),
    [tree]
  );

  function renderTitle(data: TreeDataNode) {
    const node = (data as DeptTreeDataNode).dept;
    return (
      <span className="dept-tree-node">
        <span>{`${node.name}(${node.member_count})`}</span>
        {(canCreate || canUpdate || canDelete) && (
          <Space size={0} className="dept-tree-actions">
            {canCreate && (
              <Button
                type="text"
                size="small"
                icon={<PlusOutlined />}
                aria-label="新建子部门"
                onClick={(e) => {
                  e.stopPropagation();
                  onCreateChild(node);
                }}
              />
            )}
            {canUpdate && (
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                aria-label="编辑部门"
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(node);
                }}
              />
            )}
            {canDelete && (
              <Popconfirm
                title="确认删除该部门?"
                onConfirm={() => onDelete(node)}
              >
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  aria-label="删除部门"
                  onClick={(e) => e.stopPropagation()}
                />
              </Popconfirm>
            )}
          </Space>
        )}
      </span>
    );
  }

  return (
    <div>
      {canCreate && (
        <Button type="primary" block style={{ marginBottom: 12 }} onClick={onCreateRoot}>
          新建部门
        </Button>
      )}
      <Tree
        treeData={treeData}
        titleRender={renderTitle}
        selectedKeys={selectedId ? [selectedId] : []}
        defaultExpandAll
        blockNode
        onSelect={(keys) => {
          const key = keys[0];
          if (typeof key === "string") onSelect(key);
        }}
      />
    </div>
  );
}
```

- [ ] **Step 5: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/departments/DeptTreePanel.test.tsx && npm run typecheck`
Expected: 全部通过;typecheck 零错误

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/departments/DeptTreePanel.tsx frontend/src/pages/departments/dept.css frontend/src/pages/departments/DeptTreePanel.test.tsx
git commit -m "feat(frontend): P0#2 部门树面板(节点含人数,悬停 CRUD 操作按权限显隐)"
```

---

## Task 4: DeptMembersPanel(选中部门成员列表)

**Files:**
- Create: `frontend/src/pages/departments/DeptMembersPanel.tsx`
- Test: `frontend/src/pages/departments/DeptMembersPanel.test.tsx`

**Interfaces:**
- Consumes: `DepartmentNode`、`UserResponse`(Task 1 / 既有)
- Produces(Task 5 依赖):`DeptMembersPanel` props:
  ```ts
  {
    dept: DepartmentNode | null;   // null = 未选中,显示空态
    members: UserResponse[];
    total: number;
    page: number;
    loading: boolean;
    error: string | null;          // 含 403,Alert 展示
    onPageChange: (page: number) => void;
  }
  ```
  - 分页 pageSize 固定 20,`showTotal: (t) => `共 ${t} 条``

- [ ] **Step 1: 写失败测试 `frontend/src/pages/departments/DeptMembersPanel.test.tsx`**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DepartmentNode, UserResponse } from "../../types/api";
import DeptMembersPanel from "./DeptMembersPanel";

const dept: DepartmentNode = {
  id: "d1",
  name: "技术部",
  parent_id: null,
  member_count: 2,
  children: [],
};

const member: UserResponse = {
  id: "u1",
  email: "a@x.com",
  name: "张三",
  is_active: true,
  roles: [{ code: "employee", name: "普通员工" }],
  department: { id: "d1", name: "技术部" },
  manager: null,
};

const baseProps = {
  dept,
  members: [member],
  total: 1,
  page: 1,
  loading: false,
  error: null as string | null,
  onPageChange: vi.fn(),
};

describe("DeptMembersPanel", () => {
  it("未选中部门:空态提示,不渲染表格", () => {
    render(<DeptMembersPanel {...baseProps} dept={null} members={[]} total={0} />);
    expect(screen.getByText("请选择左侧部门查看成员")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("渲染成员行(姓名/邮箱/角色/状态)", () => {
    render(<DeptMembersPanel {...baseProps} />);
    expect(screen.getByText("张三")).toBeInTheDocument();
    expect(screen.getByText("a@x.com")).toBeInTheDocument();
    expect(screen.getByText("普通员工")).toBeInTheDocument();
    expect(screen.getByText("启用")).toBeInTheDocument();
  });

  it("error(含 403):Alert 展示,不白屏", () => {
    render(<DeptMembersPanel {...baseProps} error="无权查看该部门成员" />);
    expect(screen.getByText("无权查看该部门成员")).toBeInTheDocument();
  });

  it("翻页回调", async () => {
    const onPageChange = vi.fn();
    render(<DeptMembersPanel {...baseProps} total={40} onPageChange={onPageChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByTitle("2"));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/pages/departments/DeptMembersPanel.test.tsx`
Expected: FAIL,`Failed to resolve import "./DeptMembersPanel"`

- [ ] **Step 3: 实现 `frontend/src/pages/departments/DeptMembersPanel.tsx`**

```tsx
import { Alert, Empty, Table, Tag } from "antd";

import type { DepartmentNode, UserResponse } from "../../types/api";

interface Props {
  dept: DepartmentNode | null;
  members: UserResponse[];
  total: number;
  page: number;
  loading: boolean;
  error: string | null;
  onPageChange: (page: number) => void;
}

export default function DeptMembersPanel({
  dept,
  members,
  total,
  page,
  loading,
  error,
  onPageChange,
}: Props) {
  if (!dept) {
    return <Empty description="请选择左侧部门查看成员" style={{ marginTop: 80 }} />;
  }

  const columns = [
    { title: "姓名", dataIndex: "name", key: "name" },
    { title: "邮箱", dataIndex: "email", key: "email" },
    {
      title: "角色",
      key: "roles",
      render: (_: unknown, u: UserResponse) =>
        u.roles.map((r) => <Tag key={r.code}>{r.name}</Tag>),
    },
    {
      title: "状态",
      key: "status",
      render: (_: unknown, u: UserResponse) =>
        u.is_active ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag>,
    },
  ];

  return (
    <div>
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Table<UserResponse>
        rowKey="id"
        columns={columns}
        dataSource={members}
        loading={loading}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          showTotal: (t) => `共 ${t} 条`,
          onChange: onPageChange,
        }}
      />
    </div>
  );
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/departments/DeptMembersPanel.test.tsx && npm run typecheck`
Expected: 全部通过;typecheck 零错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/departments/DeptMembersPanel.tsx frontend/src/pages/departments/DeptMembersPanel.test.tsx
git commit -m "feat(frontend): P0#2 部门成员面板(分页表格,空态与 403 Alert)"
```

---

## Task 5: DepartmentPage + 路由 + 菜单

**Files:**
- Create: `frontend/src/pages/departments/DepartmentPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/menu.tsx`
- Test: `frontend/src/pages/departments/DepartmentPage.test.tsx`

**Interfaces:**
- Consumes: `DeptFormModal`(Task 2)、`DeptTreePanel`(Task 3)、`DeptMembersPanel`(Task 4)、api `listDeptTree/deleteDepartment/listDeptMembers`(Task 1)、`useAuthStore.hasPermission`、`findNode`(Task 2)
- Produces: 路由 `/departments`;菜单项 `{ key: "/departments", label: "部门管理", icon: <ApartmentOutlined />, permission: "department:list" }`

- [ ] **Step 1: 写失败测试 `frontend/src/pages/departments/DepartmentPage.test.tsx`**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/departments", () => ({
  listDeptTree: vi.fn(),
  createDepartment: vi.fn(),
  updateDepartment: vi.fn(),
  deleteDepartment: vi.fn(),
  listDeptMembers: vi.fn(),
}));

import { deleteDepartment, listDeptMembers, listDeptTree } from "../../api/departments";
import { useAuthStore } from "../../store/auth";
import type { CurrentUser, DepartmentNode, UserResponse } from "../../types/api";
import DepartmentPage from "./DepartmentPage";

const adminUser: CurrentUser = {
  id: "a1",
  email: "admin@x.com",
  name: "管理员",
  is_active: true,
  roles: [{ code: "admin", name: "管理员" }],
  department: null,
  manager: null,
  permissions: [
    "department:list",
    "department:members",
    "department:create",
    "department:update",
    "department:delete",
  ],
};

const tree: DepartmentNode[] = [
  {
    id: "d1",
    name: "技术部",
    parent_id: null,
    member_count: 1,
    children: [{ id: "d2", name: "前端组", parent_id: "d1", member_count: 0, children: [] }],
  },
  { id: "d5", name: "市场部", parent_id: null, member_count: 0, children: [] },
];

const member: UserResponse = {
  id: "u1",
  email: "a@x.com",
  name: "张三",
  is_active: true,
  roles: [],
  department: { id: "d1", name: "技术部" },
  manager: null,
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/departments"]}>
      <Routes>
        <Route path="/departments" element={<DepartmentPage />} />
        <Route path="/" element={<div>首页占位</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  useAuthStore.setState({ token: "tok", user: adminUser });
  vi.mocked(listDeptTree).mockResolvedValue(tree);
  vi.mocked(listDeptMembers).mockResolvedValue({ items: [member], total: 1, page: 1, page_size: 20 });
});

describe("DepartmentPage", () => {
  it("无 department:list 权限:跳回首页", () => {
    useAuthStore.setState({ user: { ...adminUser, permissions: [] } });
    renderPage();
    expect(screen.getByText("首页占位")).toBeInTheDocument();
    expect(listDeptTree).not.toHaveBeenCalled();
  });

  it("树渲染,默认选中第一个根部门并拉取其成员", async () => {
    renderPage();
    expect(await screen.findByText("技术部(1)")).toBeInTheDocument();
    expect(screen.getByText("前端组(0)")).toBeInTheDocument();
    await waitFor(() =>
      expect(listDeptMembers).toHaveBeenCalledWith("d1", { page: 1, page_size: 20 })
    );
    expect(await screen.findByText("张三")).toBeInTheDocument();
  });

  it("切换选中部门:重新拉取该部门成员", async () => {
    vi.mocked(listDeptMembers).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    renderPage();
    await screen.findByText("技术部(1)");
    const user = userEvent.setup();
    await user.click(screen.getByText("市场部(0)"));
    await waitFor(() =>
      expect(listDeptMembers).toHaveBeenCalledWith("d5", { page: 1, page_size: 20 })
    );
  });

  it("成员接口 403:Alert 展示不白屏", async () => {
    const { ApiError } = await import("../../api/client");
    vi.mocked(listDeptMembers).mockRejectedValue(new ApiError("FORBIDDEN", "无权查看该部门成员"));
    renderPage();
    expect(await screen.findByText("无权查看该部门成员")).toBeInTheDocument();
  });

  it("删除部门:调 deleteDepartment 并重新拉树", async () => {
    vi.mocked(deleteDepartment).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText("市场部(0)");
    const user = userEvent.setup();
    // 删除未选中的"市场部"(树顺序:技术部、前端组、市场部,删除按钮第 3 个)
    await user.click(screen.getAllByRole("button", { name: "删除部门" })[2]);
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    await waitFor(() => expect(deleteDepartment).toHaveBeenCalledWith("d5"));
    // 删除后重新拉树
    await waitFor(() => expect(listDeptTree).toHaveBeenCalledTimes(2));
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/pages/departments/DepartmentPage.test.tsx`
Expected: FAIL,`Failed to resolve import "./DepartmentPage"`

- [ ] **Step 3: 实现 `frontend/src/pages/departments/DepartmentPage.tsx`**

```tsx
import { useCallback, useEffect, useState } from "react";
import { Alert, Card, message } from "antd";
import { Navigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { deleteDepartment, listDeptMembers, listDeptTree } from "../../api/departments";
import { useAuthStore } from "../../store/auth";
import type { DepartmentNode, UserResponse } from "../../types/api";
import { findNode } from "../../utils/deptTree";
import DeptFormModal from "./DeptFormModal";
import DeptMembersPanel from "./DeptMembersPanel";
import DeptTreePanel from "./DeptTreePanel";

const PAGE_SIZE = 20;

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : "网络异常,请稍后重试";
}

export default function DepartmentPage() {
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const allowed = hasPermission("department:list");
  const canCreate = hasPermission("department:create");
  const canUpdate = hasPermission("department:update");
  const canDelete = hasPermission("department:delete");

  const [tree, setTree] = useState<DepartmentNode[]>([]);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [members, setMembers] = useState<UserResponse[]>([]);
  const [membersTotal, setMembersTotal] = useState(0);
  const [membersPage, setMembersPage] = useState(1);
  const [membersLoading, setMembersLoading] = useState(false);
  const [membersError, setMembersError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editingDept, setEditingDept] = useState<DepartmentNode | null>(null);
  const [presetParentId, setPresetParentId] = useState<string | null>(null);

  const fetchTree = useCallback(async () => {
    setTreeError(null);
    try {
      const data = await listDeptTree();
      setTree(data);
      setSelectedId((prev) => {
        if (prev) return prev;
        return data.length > 0 ? data[0].id : null;
      });
    } catch (e) {
      setTreeError(errMsg(e));
    }
  }, []);

  useEffect(() => {
    if (allowed) void fetchTree();
  }, [allowed, fetchTree]);

  const fetchMembers = useCallback(async (deptId: string, page: number) => {
    setMembersLoading(true);
    setMembersError(null);
    try {
      const resp = await listDeptMembers(deptId, { page, page_size: PAGE_SIZE });
      setMembers(resp.items);
      setMembersTotal(resp.total);
    } catch (e) {
      setMembers([]);
      setMembersTotal(0);
      setMembersError(errMsg(e));
    } finally {
      setMembersLoading(false);
    }
  }, []);

  useEffect(() => {
    if (allowed && selectedId) void fetchMembers(selectedId, membersPage);
  }, [allowed, selectedId, membersPage, fetchMembers]);

  function onSelectDept(id: string) {
    if (id === selectedId) return;
    setSelectedId(id);
    setMembersPage(1);
  }

  function openCreate(parentId: string | null) {
    setEditingDept(null);
    setPresetParentId(parentId);
    setFormOpen(true);
  }

  function openEdit(node: DepartmentNode) {
    setEditingDept(node);
    setPresetParentId(null);
    setFormOpen(true);
  }

  async function onDelete(node: DepartmentNode) {
    try {
      await deleteDepartment(node.id);
      message.success("已删除");
      if (node.id === selectedId) {
        setSelectedId(null);
        setMembers([]);
        setMembersTotal(0);
      }
      await fetchTree();
    } catch (e) {
      message.error(errMsg(e));
    }
  }

  if (!allowed) {
    return <Navigate to="/" replace />;
  }

  const selectedDept = selectedId ? findNode(tree, selectedId) : null;

  return (
    <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
      <Card title="部门" style={{ width: 340, flexShrink: 0 }}>
        {treeError && (
          <Alert type="error" message={treeError} showIcon style={{ marginBottom: 16 }} />
        )}
        <DeptTreePanel
          tree={tree}
          selectedId={selectedId}
          canCreate={canCreate}
          canUpdate={canUpdate}
          canDelete={canDelete}
          onSelect={onSelectDept}
          onCreateRoot={() => openCreate(null)}
          onCreateChild={(node) => openCreate(node.id)}
          onEdit={openEdit}
          onDelete={(node) => void onDelete(node)}
        />
      </Card>
      <Card title="成员" style={{ flex: 1 }}>
        <DeptMembersPanel
          dept={selectedDept}
          members={members}
          total={membersTotal}
          page={membersPage}
          loading={membersLoading}
          error={membersError}
          onPageChange={setMembersPage}
        />
      </Card>
      <DeptFormModal
        open={formOpen}
        tree={tree}
        editing={editingDept}
        presetParentId={presetParentId}
        onClose={() => setFormOpen(false)}
        onSuccess={() => {
          message.success(editingDept ? "已保存" : "已创建");
          void fetchTree();
        }}
      />
    </div>
  );
}
```

- [ ] **Step 4: 修改 `frontend/src/App.tsx`**

import 追加 `import DepartmentPage from "./pages/departments/DepartmentPage";`,children 数组在 `{ path: "users", ... }` 后追加:

```tsx
      { path: "departments", element: <DepartmentPage /> },
```

- [ ] **Step 5: 修改 `frontend/src/components/menu.tsx`**

import 改为 `import { ApartmentOutlined, HomeOutlined, TeamOutlined } from "@ant-design/icons";`,`MENU_ITEMS` 在 `/users` 项后追加:

```ts
  { key: "/departments", label: "部门管理", icon: <ApartmentOutlined />, permission: "department:list" },
```

- [ ] **Step 6: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/departments/DepartmentPage.test.tsx && npm test && npm run typecheck`
Expected: 新测试全部通过;全量测试(45 + 新增)全绿;typecheck 零错误

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/departments/DepartmentPage.tsx frontend/src/pages/departments/DepartmentPage.test.tsx frontend/src/App.tsx frontend/src/components/menu.tsx
git commit -m "feat(frontend): P0#2 部门管理页(左树右表)与路由、菜单接入"
```

---

## Task 6: UserOrgModal + 用户管理"归属"入口

**Files:**
- Create: `frontend/src/pages/users/UserOrgModal.tsx`
- Modify: `frontend/src/pages/users/UserListPage.tsx`
- Test: `frontend/src/pages/users/UserOrgModal.test.tsx`
- Test: `frontend/src/pages/users/UserListPage.test.tsx`(追加 1 个用例)

**Interfaces:**
- Consumes: `updateUserOrg`(Task 1)、`listDeptTree`、`listDeptMembers`(Task 1)、`toTreeSelectData`(Task 2)、`UserResponse`、`ApiError`、`useAuthStore`
- Produces: `UserOrgModal` props(与 RoleAssignModal 同构):`{ user: UserResponse | null; onClose: () => void; onSuccess: () => void }`,`user=null` 即关闭
  - 打开时:`listDeptTree()` 拉部门树;预填 `department_id = user.department?.id`、`manager_id = user.manager?.id`;有部门时拉该部门成员作为上级候选(`listDeptMembers(deptId, {page: 1, page_size: 100})`,排除用户自己)
  - 切换部门:清空已选上级,重新拉候选;清空部门:上级候选清空
  - 提交:`updateUserOrg(user.id, { department_id: values.department_id ?? null, manager_id: values.manager_id ?? null })`

- [ ] **Step 1: 写失败测试 `frontend/src/pages/users/UserOrgModal.test.tsx`**

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/departments", () => ({
  listDeptTree: vi.fn(),
  listDeptMembers: vi.fn(),
}));
vi.mock("../../api/users", () => ({
  updateUserOrg: vi.fn(),
}));

import { ApiError } from "../../api/client";
import { listDeptMembers, listDeptTree } from "../../api/departments";
import { updateUserOrg } from "../../api/users";
import type { DepartmentNode, UserResponse } from "../../types/api";
import UserOrgModal from "./UserOrgModal";

const tree: DepartmentNode[] = [
  { id: "d1", name: "技术部", parent_id: null, member_count: 2, children: [] },
  { id: "d5", name: "市场部", parent_id: null, member_count: 1, children: [] },
];

const target: UserResponse = {
  id: "u1",
  email: "a@x.com",
  name: "张三",
  is_active: true,
  roles: [],
  department: { id: "d1", name: "技术部" },
  manager: { id: "u2", name: "王主管" },
};

const d1Members: UserResponse[] = [
  { id: "u1", email: "a@x.com", name: "张三", is_active: true, roles: [], department: null, manager: null },
  { id: "u2", email: "b@x.com", name: "王主管", is_active: true, roles: [], department: null, manager: null },
];

const d5Members: UserResponse[] = [
  { id: "u9", email: "c@x.com", name: "李市场", is_active: true, roles: [], department: null, manager: null },
];

function deptFormItem() {
  return within(screen.getByText("所属部门").closest(".ant-form-item") as HTMLElement);
}
function managerFormItem() {
  return within(screen.getByText("直属上级").closest(".ant-form-item") as HTMLElement);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listDeptTree).mockResolvedValue(tree);
  vi.mocked(listDeptMembers).mockImplementation(async (id: string) =>
    id === "d1"
      ? { items: d1Members, total: 2, page: 1, page_size: 100 }
      : { items: d5Members, total: 1, page: 1, page_size: 100 }
  );
});

describe("UserOrgModal", () => {
  it("打开:预填部门与上级;上级候选排除用户自己", async () => {
    render(<UserOrgModal user={target} onClose={() => {}} onSuccess={() => {}} />);
    expect(await deptFormItem().findByText("技术部")).toBeInTheDocument();
    await waitFor(() => expect(listDeptMembers).toHaveBeenCalledWith("d1", { page: 1, page_size: 100 }));
    expect(await managerFormItem().findByText("王主管")).toBeInTheDocument();
    // 候选排除自己:打开上级下拉
    const user = userEvent.setup();
    await user.click(managerFormItem().getByRole("combobox"));
    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByText("王主管")).toBeInTheDocument();
    expect(within(listbox).queryByText("张三")).not.toBeInTheDocument();
  });

  it("切换部门:清空已选上级并重新拉候选", async () => {
    render(<UserOrgModal user={target} onClose={() => {}} onSuccess={() => {}} />);
    await managerFormItem().findByText("王主管");
    const user = userEvent.setup();
    await user.click(deptFormItem().getByRole("combobox"));
    const treeDropdown = await screen.findByRole("tree");
    await user.click(within(treeDropdown).getByText("市场部"));
    await waitFor(() => expect(listDeptMembers).toHaveBeenCalledWith("d5", { page: 1, page_size: 100 }));
    // 已选上级被清空
    expect(managerFormItem().queryByText("王主管")).not.toBeInTheDocument();
  });

  it("提交:updateUserOrg 参数正确并触发 onSuccess/onClose", async () => {
    vi.mocked(updateUserOrg).mockResolvedValue(target);
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    render(<UserOrgModal user={target} onClose={onClose} onSuccess={onSuccess} />);
    await managerFormItem().findByText("王主管");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() =>
      expect(updateUserOrg).toHaveBeenCalledWith("u1", { department_id: "d1", manager_id: "u2" })
    );
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("清空部门与上级提交:显式 null(清空语义)", async () => {
    vi.mocked(updateUserOrg).mockResolvedValue({ ...target, department: null, manager: null });
    render(<UserOrgModal user={target} onClose={() => {}} onSuccess={() => {}} />);
    await managerFormItem().findByText("王主管");
    const user = userEvent.setup();
    // 清空部门
    const deptSelector = deptFormItem().getByText("技术部").closest(".ant-select-selector") as HTMLElement;
    await user.hover(deptSelector);
    await user.click(deptSelector.parentElement!.querySelector(".ant-select-clear") as HTMLElement);
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() =>
      expect(updateUserOrg).toHaveBeenCalledWith("u1", { department_id: null, manager_id: null })
    );
  });

  it("失败(422 上级校验):显示 ApiError.message,不关闭", async () => {
    vi.mocked(updateUserOrg).mockRejectedValue(new ApiError("VALIDATION_ERROR", "直属上级须属于同一部门"));
    const onClose = vi.fn();
    render(<UserOrgModal user={target} onClose={onClose} onSuccess={() => {}} />);
    await managerFormItem().findByText("王主管");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("直属上级须属于同一部门")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: 追加用例到 `frontend/src/pages/users/UserListPage.test.tsx`**

`vi.mock("../../api/users", ...)` 的工厂对象追加 `updateUserOrg: vi.fn()`;新增 `vi.mock("../../api/departments", () => ({ listDeptTree: vi.fn(), listDeptMembers: vi.fn() }));`;`vi.mock("./UserFormModal", ...)` 之后追加 `vi.mock("./UserOrgModal", () => ({ default: () => null }));`。describe 内追加:

```tsx
  it("归属:admin 可见入口,点击打开 UserOrgModal", async () => {
    renderPage();
    await screen.findByText("张三");
    expect(screen.getByRole("button", { name: "归属" })).toBeInTheDocument();
  });
```

(UserOrgModal 被 mock 为 null,此处只验证入口显隐与权限;交互由 UserOrgModal.test.tsx 覆盖。)

- [ ] **Step 3: 运行确认失败**

Run: `cd frontend && npx vitest run src/pages/users/UserOrgModal.test.tsx src/pages/users/UserListPage.test.tsx`
Expected: FAIL,`Failed to resolve import "./UserOrgModal"`

- [ ] **Step 4: 实现 `frontend/src/pages/users/UserOrgModal.tsx`**

```tsx
import { useEffect, useMemo, useState } from "react";
import { Alert, Form, Modal, Select, TreeSelect } from "antd";

import { ApiError } from "../../api/client";
import { listDeptMembers, listDeptTree } from "../../api/departments";
import { updateUserOrg } from "../../api/users";
import type { DepartmentNode, UserResponse } from "../../types/api";
import { toTreeSelectData } from "../../utils/deptTree";

interface Props {
  user: UserResponse | null;
  onClose: () => void;
  onSuccess: () => void;
}

interface OrgFormValues {
  department_id?: string;
  manager_id?: string;
}

export default function UserOrgModal({ user, onClose, onSuccess }: Props) {
  const [form] = Form.useForm<OrgFormValues>();
  const [tree, setTree] = useState<DepartmentNode[]>([]);
  const [candidates, setCandidates] = useState<UserResponse[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const deptId = Form.useWatch("department_id", form);

  useEffect(() => {
    if (!user) return;
    setError(null);
    setCandidates([]);
    void listDeptTree()
      .then(setTree)
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试")
      );
  }, [user]);

  useEffect(() => {
    if (!user || !deptId) {
      setCandidates([]);
      return;
    }
    listDeptMembers(deptId, { page: 1, page_size: 100 })
      .then((resp) => setCandidates(resp.items.filter((m) => m.id !== user.id)))
      .catch(() => setCandidates([]));
  }, [user, deptId]);

  const treeData = useMemo(() => toTreeSelectData(tree), [tree]);

  async function onFinish(values: OrgFormValues) {
    if (!user) return;
    setSubmitting(true);
    setError(null);
    try {
      await updateUserOrg(user.id, {
        department_id: values.department_id ?? null,
        manager_id: values.manager_id ?? null,
      });
      onSuccess();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      title={`设置归属:${user?.name ?? ""}`}
      open={user !== null}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Form<OrgFormValues>
        key={user?.id ?? "none"}
        form={form}
        layout="vertical"
        onFinish={onFinish}
        preserve={false}
        initialValues={
          user
            ? {
                department_id: user.department?.id ?? undefined,
                manager_id: user.manager?.id ?? undefined,
              }
            : undefined
        }
      >
        <Form.Item name="department_id" label="所属部门">
          <TreeSelect
            treeData={treeData}
            allowClear
            placeholder="不选则无部门"
            treeDefaultExpandAll
            onChange={() => form.setFieldsValue({ manager_id: undefined })}
          />
        </Form.Item>
        <Form.Item name="manager_id" label="直属上级">
          <Select
            allowClear
            placeholder="先从部门成员中选择"
            options={candidates.map((m) => ({ value: m.id, label: m.name }))}
            disabled={!deptId}
            showSearch
            optionFilterProp="label"
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
```

- [ ] **Step 5: 修改 `frontend/src/pages/users/UserListPage.tsx`**

- import 追加 `import UserOrgModal from "./UserOrgModal";`
- state 追加 `const [orgEditing, setOrgEditing] = useState<UserResponse | null>(null);`
- "分配角色"按钮后追加("归属"按 `user:update` 显隐):

```tsx
          {hasPermission("user:update") && (
            <Button type="link" size="small" onClick={() => setOrgEditing(u)}>
              归属
            </Button>
          )}
```

- `RoleAssignModal` 后追加:

```tsx
      <UserOrgModal
        user={orgEditing}
        onClose={() => setOrgEditing(null)}
        onSuccess={() => {
          message.success("归属已更新");
          void fetchList(page, search);
        }}
      />
```

- [ ] **Step 6: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/users/UserOrgModal.test.tsx src/pages/users/UserListPage.test.tsx && npm test && npm run typecheck && npm run build`
Expected: 全部通过;全量测试全绿;typecheck 零错误;build 成功

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/users/UserOrgModal.tsx frontend/src/pages/users/UserOrgModal.test.tsx frontend/src/pages/users/UserListPage.tsx frontend/src/pages/users/UserListPage.test.tsx
git commit -m "feat(frontend): P0#2 用户归属弹窗(部门+直属上级)与用户管理入口"
```

---

## Task 7: 全量验收(自动化门禁 + 浏览器实测)

**Files:**
- Modify: `docs/superpowers/specs/2026-07-25-frontend-org-structure-design.md`(§8 勾选)
- Create: `.superpowers/sdd/acceptance/*.png`(验收截图,gitignored 目录,不提交)

- [ ] **Step 1: 自动化门禁**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: 全部测试通过(P0#1 既有 + 本期新增,只增不减);typecheck 零错误;build 成功

- [ ] **Step 2: 启动后端与 dev server**

```bash
docker compose up -d db
cd backend && uvicorn app.main:app --port 8000 &   # 后台;若已运行则跳过
cd frontend && NODE_OPTIONS=--dns-result-order=ipv4first npx vite --port 5173 &   # 后台
```

验证:`curl -s http://localhost:8000/docs -o /dev/null -w "%{http_code}"` 返回 200;`curl -s http://localhost:5173/` 返回含 `<div id="root">`。
清理前置:浏览器 `evaluate_script` 清 localStorage 残留 token。再检查数据残留:

```bash
ADMIN_TOKEN=$(curl -s -X POST http://localhost:5173/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"admin@company.com","password":"Admin123!"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s http://localhost:5173/api/v1/departments -H "Authorization: Bearer $ADMIN_TOKEN"
```

若有前次验收残留部门,按叶子→根顺序 `curl -X DELETE` 清理;若 `e2e.mgr@company.com` 用户已存在(前次中断残留),直接复用(步骤 13 的分配角色/归属是覆盖式,幂等)。

- [ ] **Step 3: 浏览器实测(chrome-devtools 驱动,每场景截图到 `.superpowers/sdd/acceptance/`)**

严格按顺序执行;每步先 `take_snapshot` 拿 uid,操作后核对页面文本,再 `take_screenshot` 存档。已含值输入框替换文本用 click → Control+A → `type_text`。

1. **admin 登录 + 部门页渲染**:`http://localhost:5173/login` 用 `admin@company.com` / `Admin123!` 登录 → 菜单含"部门管理" → 进入 → 树区为空(首次)且右侧空态"请选择左侧部门查看成员"。截图 `01-dept-empty.png`
2. **新建根部门**:点"新建部门",名称 `技术部`,不选父部门 → 树出现"技术部(0)"并默认选中,右侧成员 0 条。截图 `02-dept-root-created.png`
3. **新建子部门**:悬停"技术部"点 + ,名称 `前端组`(父部门预填"技术部")→ 树出现"前端组(0)"。截图 `03-dept-child-created.png`
4. **同级重名 409**:再建一个 `前端组`(父=技术部)→ 弹窗内 Alert 显示错误,不关闭。截图 `04-dept-dup-409.png`;取消
5. **编辑改名**:编辑"前端组" → 改 `前端一组` → 树更新。截图 `05-dept-renamed.png`
6. **TreeSelect 移动部门**:新建根部门 `市场部`;编辑"前端一组",父部门改选"市场部" → 树中"前端一组"挂到"市场部"下。截图 `06-dept-moved.png`
7. **移动防环(前端排除 + 后端兜底)**:编辑"市场部"打开父部门下拉 → 候选中**无**"市场部"与"前端一组"(自身及后代已被前端排除)。截图 `07-dept-move-excluded.png`;再用 curl 验证后端兜底——从 `GET /departments` 取"市场部"与"前端一组"的 id,执行:
   ```bash
   curl -s -X PATCH http://localhost:5173/api/v1/departments/<市场部id> -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"parent_id":"<前端一组id>"}'
   ```
   预期 409 错误信封(移动成环)。输出存 `07-dept-cycle-409.txt`
8. **删除空部门**:删除"前端一组"(Popconfirm 确定)→ 树移除。截图 `08-dept-deleted.png`
9. **删除有员工的部门 409**:先到用户管理给 `张测试2`(e2e.emp@company.com)归属"技术部";回部门页删除"技术部" → `message.error` 409 提示,树不变。截图 `09-dept-delete-409.png`
10. **成员列表**:选中"技术部" → 右侧成员表出现"张测试2"。截图 `10-dept-members.png`
11. **归属成功(部门+直属上级)**:先给 `demo.user@company.com`(李演示2)归属"技术部";再给 `张测试2` 归属:部门"技术部",上级选"李演示2" → 成功,用户列表"部门"列显示"技术部"。截图 `11-org-success.png`
12. **上级跨部门 422**:把李演示2的归属改到"市场部"(此时张测试2的上级仍指向李演示2,形成跨部门);再打开张测试2的"归属"弹窗,不改任何字段直接确定 → Modal 内 Alert 显示 422 错误(上级须同部门),不关闭。截图 `12-org-manager-422.png`;取消后把张测试2的上级清空保存,恢复正常
13. **manager 视角准备**:admin 新建用户 `e2e.mgr@company.com` / `Mgr12345!` 姓名 `赵主管`,分配角色"部门主管(manager)",归属"技术部"
14. **manager 登录**:退出,`e2e.mgr@company.com` 登录 → 菜单含"部门管理",进入 → 树节点**无** CRUD 按钮、顶部无"新建部门";选中"技术部"成员列表正常(含张测试2、赵主管)。截图 `13-manager-dept.png`
15. **manager 看其他部门 403**:manager 选中"市场部"(李演示2所在,赵主管无数据范围)→ 成员区 Alert 403 错误提示,不白屏。截图 `14-manager-403.png`
16. **employee 视角**:退出,`demo.user@company.com` / `DemoNew123!` 登录(employee,无 department:list)→ 菜单**无**"部门管理";地址栏直访 `http://localhost:5173/departments` → 跳回 `/`。截图 `15-employee-redirect.png`
17. 停止 vite 与 uvicorn(自己启动的进程;db 容器可留)

- [ ] **Step 4: 勾选 spec §8**

`docs/superpowers/specs/2026-07-25-frontend-org-structure-design.md` §8 全部 `- [ ]` 改 `- [x]`(仅 §8 内)。

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-07-25-frontend-org-structure-design.md
git commit -m "test(frontend): P0#2 组织架构前端全量验收通过,勾选 spec 验收标准"
```
