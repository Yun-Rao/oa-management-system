# 前端 P0#1 用户认证+RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在前端地基之上实现 P0#1 用户认证+RBAC 前端:真登录页、修改密码、用户管理(列表/搜索/新建/编辑/启停/分配角色),并以组件级测试与浏览器实测验收。

**Architecture:** 页面内 `useState`+`useEffect` 管服务器数据(无新运行时依赖);api 层纯函数走地基统一 axios client;AntD Table + Modal 标准交互;React Testing Library 做组件级测试;验收由执行 Agent 用 chrome-devtools 驱动真实浏览器逐场景截图。

**Tech Stack:** React 18 + TS(strict) + AntD 5.29 + Zustand + React Router 6 + Vitest + @testing-library/react + axios-mock-adapter

**Spec:** `docs/superpowers/specs/2026-07-25-frontend-auth-rbac-design.md`(验收标准见 §8)

## Global Constraints

- 每步 TDD:先写失败测试 → 确认失败 → 实现 → 确认通过 → 提交
- 提交只 `git add` 明确列出的文件,**严禁** `git add .` / `git add -A`
- 所有 npm/npx/vitest 命令在 `frontend/` 目录下执行;git 命令在仓库根执行;Shell 为 git bash(Windows),用 Unix 语法
- 设计决策级变更必须同步 spec;实现细节修复不动 spec
- 不修改 `backend/` 下任何文件
- api 层不做 try/catch;错误信封由 `client` 拦截器统一转 `ApiError(code, message)`,页面层捕获后取 `e.message`
- 组件成功提示用 antd 静态 `message.success/error`(可接受无上下文警告)
- antd `Modal` 用 `destroyOnHidden`(5.25+ 替代已废弃的 `destroyOnClose`)
- 后端接口契约(以 `backend/app/schemas` 为准,TS 类型严格对齐):
  - `GET /users?page&page_size&keyword?` → `{items: UserResponse[], total, page, page_size}`;`UserResponse {id: string, email, name, is_active, roles: [{code,name}], department: {id,name} | null, manager: {id,name} | null}`
  - `POST /users {email, name, password}`;`PATCH /users/{id} {email?, name?}`;`PATCH /users/{id}/status {is_active}`;`PUT /users/{id}/roles {role_codes: string[]}`
  - `GET /roles` → `[{code, name, description: string|null, permissions: [{code,name}]}]`
  - `POST /auth/change-password {old_password, new_password}` → 204 无响应体
- Seed 账号(浏览器验收用):admin `admin@company.com` / `Admin123!`;角色 employee 仅有 `leave:create, leave:list`(无 `user:list`)
- 本机 vite 代理需 `NODE_OPTIONS=--dns-result-order=ipv4first`(localhost 解析 ::1 而后端绑 127.0.0.1 会挂起)
- 浏览器实测**严禁禁用 admin 账号**(只对验收创建的测试用户做启停)

---

## Task 1: 组件测试基础设施

**Files:**
- Modify: `frontend/package.json`(devDependencies 加 3 个)
- Modify: `frontend/vite.config.ts`(test.setupFiles)
- Create: `frontend/src/test/setup.ts`

**Interfaces:**
- Produces(后续任务依赖): jest-dom 匹配器(`toBeInTheDocument` 等)、jsdom polyfill(`matchMedia`、`ResizeObserver`)

- [ ] **Step 1: 修改 `frontend/package.json`**

`devDependencies` 中追加(保持字母序,加在 `@types/react-dom` 之后、`@vitejs/plugin-react` 之前):

```json
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.2",
```

- [ ] **Step 2: 创建 `frontend/src/test/setup.ts`**

```ts
import "@testing-library/jest-dom/vitest";

if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof window.ResizeObserver;
}
```

- [ ] **Step 3: 修改 `frontend/vite.config.ts`(整体替换)**

```ts
/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
  },
});
```

- [ ] **Step 4: 安装依赖**

Run: `cd frontend && npm install`
Expected: 成功,`package-lock.json` 更新

- [ ] **Step 5: 验证既有测试不受影响**

Run: `cd frontend && npm test && npm run typecheck`
Expected: 地基 11 个测试全过;`tsc --noEmit` 零错误

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src/test/setup.ts
git commit -m "test(frontend): 引入 Testing Library 与 jsdom polyfill 测试基建"
```

---

## Task 2: 类型追加 + api 层(users / roles / changePassword)

**Files:**
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/src/api/users.ts`
- Create: `frontend/src/api/roles.ts`
- Modify: `frontend/src/api/auth.ts`
- Test: `frontend/src/api/users.test.ts`
- Test: `frontend/src/api/roles.test.ts`

**Interfaces:**
- Consumes: `client`、`ApiError`(地基 `api/client.ts`)、`RoleBrief`、`DepartmentBrief`、`UserBrief`(地基 `types/api.ts`)
- Produces(后续任务依赖):
  - 类型 `UserResponse`、`UserListResponse`、`PermissionBrief`、`RoleResponse`(字段见 Global Constraints 契约)
  - `listUsers({page, page_size, keyword?}): Promise<UserListResponse>`(keyword 为空字符串/undefined 时**不传**该参数)
  - `createUser({email, name, password}): Promise<UserResponse>`
  - `updateUser(id, {email, name}): Promise<UserResponse>`
  - `setUserStatus(id, isActive: boolean): Promise<UserResponse>`
  - `assignRoles(id, roleCodes: string[]): Promise<UserResponse>`
  - `listRoles(): Promise<RoleResponse[]>`
  - `changePassword(oldPassword, newPassword): Promise<void>`

- [ ] **Step 1: 写失败测试 `frontend/src/api/users.test.ts`**

```ts
import MockAdapter from "axios-mock-adapter";
import { beforeEach, describe, expect, it } from "vitest";

import { client } from "./client";
import { assignRoles, createUser, listUsers, setUserStatus, updateUser } from "./users";

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
```

- [ ] **Step 2: 写失败测试 `frontend/src/api/roles.test.ts`**

```ts
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
```

- [ ] **Step 3: 运行确认失败**

Run: `cd frontend && npx vitest run src/api/users.test.ts src/api/roles.test.ts`
Expected: FAIL,`Failed to resolve import "./users"` / `"./roles"`

- [ ] **Step 4: 修改 `frontend/src/types/api.ts`(文件末尾追加)**

```ts
export interface UserResponse {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  roles: RoleBrief[];
  department: DepartmentBrief | null;
  manager: UserBrief | null;
}

export interface UserListResponse {
  items: UserResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface PermissionBrief {
  code: string;
  name: string;
}

export interface RoleResponse {
  code: string;
  name: string;
  description: string | null;
  permissions: PermissionBrief[];
}
```

- [ ] **Step 5: 创建 `frontend/src/api/users.ts`**

```ts
import { client } from "./client";
import type { UserListResponse, UserResponse } from "../types/api";

export interface ListUsersParams {
  page: number;
  page_size: number;
  keyword?: string;
}

export async function listUsers(params: ListUsersParams): Promise<UserListResponse> {
  const { page, page_size, keyword } = params;
  const { data } = await client.get<UserListResponse>("/users", {
    params: keyword ? { page, page_size, keyword } : { page, page_size },
  });
  return data;
}

export async function createUser(body: {
  email: string;
  name: string;
  password: string;
}): Promise<UserResponse> {
  const { data } = await client.post<UserResponse>("/users", body);
  return data;
}

export async function updateUser(
  id: string,
  body: { email?: string; name?: string }
): Promise<UserResponse> {
  const { data } = await client.patch<UserResponse>(`/users/${id}`, body);
  return data;
}

export async function setUserStatus(id: string, isActive: boolean): Promise<UserResponse> {
  const { data } = await client.patch<UserResponse>(`/users/${id}/status`, {
    is_active: isActive,
  });
  return data;
}

export async function assignRoles(id: string, roleCodes: string[]): Promise<UserResponse> {
  const { data } = await client.put<UserResponse>(`/users/${id}/roles`, {
    role_codes: roleCodes,
  });
  return data;
}
```

- [ ] **Step 6: 创建 `frontend/src/api/roles.ts`**

```ts
import { client } from "./client";
import type { RoleResponse } from "../types/api";

export async function listRoles(): Promise<RoleResponse[]> {
  const { data } = await client.get<RoleResponse[]>("/roles");
  return data;
}
```

- [ ] **Step 7: 修改 `frontend/src/api/auth.ts`(文件末尾追加)**

```ts
export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  await client.post("/auth/change-password", {
    old_password: oldPassword,
    new_password: newPassword,
  });
}
```

- [ ] **Step 8: 运行确认通过**

Run: `cd frontend && npx vitest run src/api/users.test.ts src/api/roles.test.ts && npm test && npm run typecheck`
Expected: 新增 9 个用例 PASS;全量 20 个全过;typecheck 零错误

- [ ] **Step 9: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/users.ts frontend/src/api/roles.ts frontend/src/api/auth.ts frontend/src/api/users.test.ts frontend/src/api/roles.test.ts
git commit -m "feat(frontend): 用户/角色/改密 api 层与类型定义"
```

---

## Task 3: 真登录页

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx`(整体替换占位版)
- Test: `frontend/src/pages/LoginPage.test.tsx`

**Interfaces:**
- Consumes: `useAuthStore`(state `token`,action `login(email, password)`)、`ApiError`(地基)
- Produces: `/login` 真页面(Task 7 不动路由,App.tsx 已挂 LoginPage)

- [ ] **Step 1: 写失败测试 `frontend/src/pages/LoginPage.test.tsx`**

```tsx
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
```

注意:antd Button 中"登录"两个汉字之间会被插入空格,按钮可访问名为 `登 录`。

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/pages/LoginPage.test.tsx`
Expected: FAIL(占位页无表单,`getByLabelText("邮箱")` 抛错)

- [ ] **Step 3: 整体替换 `frontend/src/pages/LoginPage.tsx`**

```tsx
import { useState } from "react";
import { Alert, Button, Card, Form, Input } from "antd";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuthStore } from "../store/auth";

interface LoginFormValues {
  email: string;
  password: string;
}

export default function LoginPage() {
  const token = useAuthStore((s) => s.token);
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onFinish(values: LoginFormValues) {
    setSubmitting(true);
    setError(null);
    try {
      await useAuthStore.getState().login(values.email, values.password);
      navigate("/", { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  if (token) {
    return <Navigate to="/" replace />;
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #f0f5ff 0%, #f6f6f6 100%)",
      }}
    >
      <Card style={{ width: 380 }}>
        <h1 style={{ textAlign: "center", fontSize: 22, marginBottom: 24 }}>OA 管理系统</h1>
        {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
        <Form<LoginFormValues> layout="vertical" onFinish={onFinish}>
          <Form.Item
            name="email"
            label="邮箱"
            rules={[
              { required: true, message: "请输入邮箱" },
              { type: "email", message: "邮箱格式不正确" },
            ]}
          >
            <Input placeholder="name@company.com" autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: "请输入密码" }]}>
            <Input.Password placeholder="请输入密码" autoComplete="current-password" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={submitting}>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/LoginPage.test.tsx && npm test && npm run typecheck`
Expected: 新增 4 个用例 PASS;全量 24 个全过;typecheck 零错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx frontend/src/pages/LoginPage.test.tsx
git commit -m "feat(frontend): 真登录页(居中卡片,错误提示,已登录跳转)"
```

---

## Task 4: 修改密码 Modal + 顶栏入口

**Files:**
- Create: `frontend/src/components/ChangePasswordModal.tsx`
- Modify: `frontend/src/components/MainLayout.tsx`(下拉加"修改密码" + 挂 Modal)
- Test: `frontend/src/components/ChangePasswordModal.test.tsx`

**Interfaces:**
- Consumes: `changePassword(oldPassword, newPassword)`(Task 2)、`ApiError`(地基)
- Produces: `ChangePasswordModal({open, onClose})`,成功时内部 `message.success("密码修改成功")` 并调 `onClose`

- [ ] **Step 1: 写失败测试 `frontend/src/components/ChangePasswordModal.test.tsx`**

```tsx
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/components/ChangePasswordModal.test.tsx`
Expected: FAIL,`Failed to resolve import "./ChangePasswordModal"`

- [ ] **Step 3: 创建 `frontend/src/components/ChangePasswordModal.tsx`**

```tsx
import { useState } from "react";
import { Alert, Form, Input, Modal, message } from "antd";

import { changePassword } from "../api/auth";
import { ApiError } from "../api/client";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface PwdFormValues {
  oldPassword: string;
  newPassword: string;
  confirm: string;
}

export default function ChangePasswordModal({ open, onClose }: Props) {
  const [form] = Form.useForm<PwdFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onFinish(values: PwdFormValues) {
    setSubmitting(true);
    setError(null);
    try {
      await changePassword(values.oldPassword, values.newPassword);
      message.success("密码修改成功");
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      title="修改密码"
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Form<PwdFormValues> form={form} layout="vertical" onFinish={onFinish} preserve={false}>
        <Form.Item name="oldPassword" label="旧密码" rules={[{ required: true, message: "请输入旧密码" }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Form.Item
          name="newPassword"
          label="新密码"
          rules={[
            { required: true, message: "请输入新密码" },
            { min: 8, max: 72, message: "密码长度须为 8-72 位" },
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirm"
          label="确认新密码"
          dependencies={["newPassword"]}
          rules={[
            { required: true, message: "请再次输入新密码" },
            ({ getFieldValue }) => ({
              validator: (_, value: string) =>
                !value || getFieldValue("newPassword") === value
                  ? Promise.resolve()
                  : Promise.reject(new Error("两次输入的密码不一致")),
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
```

- [ ] **Step 4: 修改 `frontend/src/components/MainLayout.tsx`(整体替换)**

```tsx
import { useState } from "react";
import { Dropdown, Layout, Menu } from "antd";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuthStore } from "../store/auth";
import ChangePasswordModal from "./ChangePasswordModal";
import { MENU_ITEMS } from "./menu";

export default function MainLayout() {
  const user = useAuthStore((s) => s.user);
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const navigate = useNavigate();
  const location = useLocation();
  const [pwdOpen, setPwdOpen] = useState(false);

  const items = MENU_ITEMS.filter(
    (m) => m.permission === null || hasPermission(m.permission)
  ).map((m) => ({ key: m.key, icon: m.icon, label: m.label }));

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Layout.Sider theme="light">
        <div
          style={{
            height: 48,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 600,
          }}
        >
          OA 管理系统
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={items}
          onClick={({ key }) => navigate(key)}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Header
          style={{
            background: "#fff",
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            padding: "0 24px",
          }}
        >
          <Dropdown
            menu={{
              items: [
                { key: "change-password", label: "修改密码" },
                { key: "logout", label: "退出登录" },
              ],
              onClick: ({ key }) => {
                if (key === "change-password") setPwdOpen(true);
                if (key === "logout") {
                  useAuthStore.getState().logout();
                  navigate("/login");
                }
              },
            }}
          >
            <span style={{ cursor: "pointer" }}>{user?.name}</span>
          </Dropdown>
        </Layout.Header>
        <Layout.Content style={{ margin: 16 }}>
          <Outlet />
        </Layout.Content>
      </Layout>
      <ChangePasswordModal open={pwdOpen} onClose={() => setPwdOpen(false)} />
    </Layout>
  );
}
```

- [ ] **Step 5: 运行确认通过**

Run: `cd frontend && npx vitest run src/components/ChangePasswordModal.test.tsx && npm test && npm run typecheck`
Expected: 新增 3 个用例 PASS;全量 27 个全过;typecheck 零错误

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ChangePasswordModal.tsx frontend/src/components/ChangePasswordModal.test.tsx frontend/src/components/MainLayout.tsx
git commit -m "feat(frontend): 修改密码 Modal 与顶栏入口"
```

---

## Task 5: 用户表单 Modal(新建/编辑复用)

**Files:**
- Create: `frontend/src/pages/users/UserFormModal.tsx`
- Test: `frontend/src/pages/users/UserFormModal.test.tsx`

**Interfaces:**
- Consumes: `createUser`、`updateUser`(Task 2)、`UserResponse`(Task 2)、`ApiError`(地基)
- Produces: `UserFormModal({open, editing: UserResponse | null, onClose, onSuccess})`;`editing` 为 null 是创建模式(多"初始密码"字段);成功时调 `onSuccess()` 再调 `onClose()`,提示文案由父组件负责

- [ ] **Step 1: 写失败测试 `frontend/src/pages/users/UserFormModal.test.tsx`**

```tsx
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/pages/users/UserFormModal.test.tsx`
Expected: FAIL,`Failed to resolve import "./UserFormModal"`

- [ ] **Step 3: 创建 `frontend/src/pages/users/UserFormModal.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Alert, Form, Input, Modal } from "antd";

import { ApiError } from "../../api/client";
import { createUser, updateUser } from "../../api/users";
import type { UserResponse } from "../../types/api";

interface Props {
  open: boolean;
  editing: UserResponse | null;
  onClose: () => void;
  onSuccess: () => void;
}

interface UserFormValues {
  email: string;
  name: string;
  password?: string;
}

export default function UserFormModal({ open, editing, onClose, onSuccess }: Props) {
  const [form] = Form.useForm<UserFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setError(null);
      if (editing) {
        form.setFieldsValue({ email: editing.email, name: editing.name });
      }
    }
  }, [open, editing, form]);

  async function onFinish(values: UserFormValues) {
    setSubmitting(true);
    setError(null);
    try {
      if (editing) {
        await updateUser(editing.id, { email: values.email, name: values.name });
      } else {
        await createUser({ email: values.email, name: values.name, password: values.password! });
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
      title={editing ? "编辑用户" : "新建用户"}
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Form<UserFormValues> form={form} layout="vertical" onFinish={onFinish} preserve={false}>
        <Form.Item
          name="email"
          label="邮箱"
          rules={[
            { required: true, message: "请输入邮箱" },
            { type: "email", message: "邮箱格式不正确" },
          ]}
        >
          <Input autoComplete="off" />
        </Form.Item>
        <Form.Item
          name="name"
          label="姓名"
          rules={[
            { required: true, message: "请输入姓名" },
            { max: 100, message: "姓名最长 100 字" },
          ]}
        >
          <Input />
        </Form.Item>
        {!editing && (
          <Form.Item
            name="password"
            label="初始密码"
            rules={[
              { required: true, message: "请输入初始密码" },
              { min: 8, max: 72, message: "密码长度须为 8-72 位" },
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/users/UserFormModal.test.tsx && npm run typecheck`
Expected: 4 个用例 PASS;typecheck 零错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/users/UserFormModal.tsx frontend/src/pages/users/UserFormModal.test.tsx
git commit -m "feat(frontend): 用户新建/编辑复用表单 Modal"
```

---

## Task 6: 分配角色 Modal

**Files:**
- Create: `frontend/src/pages/users/RoleAssignModal.tsx`
- Test: `frontend/src/pages/users/RoleAssignModal.test.tsx`

**Interfaces:**
- Consumes: `listRoles()`、`assignRoles(id, roleCodes)`(Task 2)、`UserResponse`、`RoleResponse`(Task 2)、`ApiError`(地基)
- Produces: `RoleAssignModal({user: UserResponse | null, onClose, onSuccess})`;`user` 为 null 即关闭;成功时调 `onSuccess()` 再调 `onClose()`

- [ ] **Step 1: 写失败测试 `frontend/src/pages/users/RoleAssignModal.test.tsx`**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/roles", () => ({ listRoles: vi.fn() }));
vi.mock("../../api/users", () => ({ assignRoles: vi.fn() }));

import { ApiError } from "../../api/client";
import { listRoles } from "../../api/roles";
import { assignRoles } from "../../api/users";
import type { RoleResponse, UserResponse } from "../../types/api";
import RoleAssignModal from "./RoleAssignModal";

const roles: RoleResponse[] = [
  { code: "admin", name: "管理员", description: null, permissions: [] },
  { code: "employee", name: "普通员工", description: null, permissions: [] },
];

const target: UserResponse = {
  id: "u1",
  email: "a@x.com",
  name: "张三",
  is_active: true,
  roles: [{ code: "employee", name: "普通员工" }],
  department: null,
  manager: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listRoles).mockResolvedValue(roles);
});

describe("RoleAssignModal", () => {
  it("打开时拉取角色并初始勾选现有角色", async () => {
    render(<RoleAssignModal user={target} onClose={() => {}} onSuccess={() => {}} />);
    const employee = await screen.findByRole("checkbox", { name: /普通员工/ });
    const admin = screen.getByRole("checkbox", { name: /管理员/ });
    expect(employee).toBeChecked();
    expect(admin).not.toBeChecked();
  });

  it("保存:assignRoles 传整体替换后的 code 数组", async () => {
    vi.mocked(assignRoles).mockResolvedValue(target);
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    render(<RoleAssignModal user={target} onClose={onClose} onSuccess={onSuccess} />);
    const user = userEvent.setup();
    await screen.findByRole("checkbox", { name: /普通员工/ });
    await user.click(screen.getByRole("checkbox", { name: /管理员/ }));
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() => expect(assignRoles).toHaveBeenCalledOnce());
    const [id, codes] = vi.mocked(assignRoles).mock.calls[0];
    expect(id).toBe("u1");
    expect([...codes].sort()).toEqual(["admin", "employee"]);
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("保存失败:显示 ApiError.message,不关闭", async () => {
    vi.mocked(assignRoles).mockRejectedValue(new ApiError("FORBIDDEN", "无权限"));
    const onClose = vi.fn();
    render(<RoleAssignModal user={target} onClose={onClose} onSuccess={() => {}} />);
    const user = userEvent.setup();
    await screen.findByRole("checkbox", { name: /普通员工/ });
    await user.click(screen.getByRole("button", { name: "确 定" }));
    expect(await screen.findByText("无权限")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/pages/users/RoleAssignModal.test.tsx`
Expected: FAIL,`Failed to resolve import "./RoleAssignModal"`

- [ ] **Step 3: 创建 `frontend/src/pages/users/RoleAssignModal.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Alert, Checkbox, Modal, Spin } from "antd";

import { ApiError } from "../../api/client";
import { listRoles } from "../../api/roles";
import { assignRoles } from "../../api/users";
import type { RoleResponse, UserResponse } from "../../types/api";

interface Props {
  user: UserResponse | null;
  onClose: () => void;
  onSuccess: () => void;
}

export default function RoleAssignModal({ user, onClose, onSuccess }: Props) {
  const [roles, setRoles] = useState<RoleResponse[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    setError(null);
    setRoles(null);
    setSelected(user.roles.map((r) => r.code));
    listRoles()
      .then(setRoles)
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "网络异常,请稍后重试")
      );
  }, [user]);

  async function onOk() {
    if (!user) return;
    setSubmitting(true);
    setError(null);
    try {
      await assignRoles(user.id, selected);
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
      title={user ? `分配角色:${user.name}` : "分配角色"}
      open={user !== null}
      onCancel={onClose}
      onOk={onOk}
      confirmLoading={submitting}
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      {roles === null && !error ? (
        <Spin />
      ) : (
        <Checkbox.Group
          style={{ display: "flex", flexDirection: "column", gap: 8 }}
          value={selected}
          onChange={(vals) => setSelected(vals as string[])}
          options={(roles ?? []).map((r) => ({
            label: `${r.name}(${r.code})`,
            value: r.code,
          }))}
        />
      )}
    </Modal>
  );
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/users/RoleAssignModal.test.tsx && npm run typecheck`
Expected: 3 个用例 PASS;typecheck 零错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/users/RoleAssignModal.tsx frontend/src/pages/users/RoleAssignModal.test.tsx
git commit -m "feat(frontend): 分配角色 Modal(整体替换)"
```

---

## Task 7: 用户管理列表页 + 菜单 + 路由

**Files:**
- Create: `frontend/src/pages/users/UserListPage.tsx`
- Test: `frontend/src/pages/users/UserListPage.test.tsx`
- Modify: `frontend/src/components/menu.tsx`(追加"用户管理")
- Modify: `frontend/src/App.tsx`(追加 `/users` 子路由)

**Interfaces:**
- Consumes: `listUsers`、`setUserStatus`(Task 2)、`UserFormModal`(Task 5)、`RoleAssignModal`(Task 6)、`useAuthStore.hasPermission`(地基)、`UserResponse`(Task 2)
- Produces: `/users` 路由(权限 `user:list` 前置拦截);菜单项 `{ key: "/users", label: "用户管理", permission: "user:list" }`

- [ ] **Step 1: 写失败测试 `frontend/src/pages/users/UserListPage.test.tsx`**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/users", () => ({
  listUsers: vi.fn(),
  setUserStatus: vi.fn(),
  assignRoles: vi.fn(),
}));
vi.mock("../../api/roles", () => ({ listRoles: vi.fn() }));
vi.mock("./UserFormModal", () => ({ default: () => null }));

import { listRoles } from "../../api/roles";
import { assignRoles, listUsers, setUserStatus } from "../../api/users";
import { useAuthStore } from "../../store/auth";
import type { CurrentUser, UserResponse } from "../../types/api";
import UserListPage from "./UserListPage";

const adminUser: CurrentUser = {
  id: "a1",
  email: "admin@x.com",
  name: "管理员",
  is_active: true,
  roles: [{ code: "admin", name: "管理员" }],
  department: null,
  manager: null,
  permissions: ["user:list", "user:create", "user:update", "user:disable", "role:list", "role:assign"],
};

const row: UserResponse = {
  id: "u1",
  email: "a@x.com",
  name: "张三",
  is_active: true,
  roles: [{ code: "employee", name: "普通员工" }],
  department: { id: "d1", name: "技术部" },
  manager: null,
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/users"]}>
      <Routes>
        <Route path="/users" element={<UserListPage />} />
        <Route path="/" element={<div>首页占位</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  useAuthStore.setState({ token: "tok", user: adminUser });
  vi.mocked(listUsers).mockResolvedValue({ items: [row], total: 1, page: 1, page_size: 20 });
  vi.mocked(listRoles).mockResolvedValue([
    { code: "admin", name: "管理员", description: null, permissions: [] },
    { code: "employee", name: "普通员工", description: null, permissions: [] },
  ]);
});

describe("UserListPage", () => {
  it("无 user:list 权限:跳回首页", () => {
    useAuthStore.setState({ user: { ...adminUser, permissions: [] } });
    renderPage();
    expect(screen.getByText("首页占位")).toBeInTheDocument();
  });

  it("渲染列表行(姓名/邮箱/部门/状态)", async () => {
    renderPage();
    expect(await screen.findByText("张三")).toBeInTheDocument();
    expect(screen.getByText("a@x.com")).toBeInTheDocument();
    expect(screen.getByText("技术部")).toBeInTheDocument();
    expect(screen.getByText("启用")).toBeInTheDocument();
  });

  it("搜索:带 keyword 重新拉取并回到第 1 页", async () => {
    renderPage();
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("姓名或邮箱"), "张");
    await user.click(screen.getByRole("button", { name: "search" }));
    await waitFor(() =>
      expect(listUsers).toHaveBeenCalledWith({ page: 1, page_size: 20, keyword: "张" })
    );
  });

  it("禁用流程:Popconfirm 确认后调 setUserStatus(id, false)", async () => {
    vi.mocked(setUserStatus).mockResolvedValue({ ...row, is_active: false });
    renderPage();
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "禁 用" }));
    await user.click(await screen.findByRole("button", { name: "确 定" }));
    await waitFor(() => expect(setUserStatus).toHaveBeenCalledWith("u1", false));
  });

  it("分配角色:打开弹窗勾选保存,assignRoles 参数正确", async () => {
    renderPage();
    await screen.findByText("张三");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "分配角色" }));
    const adminBox = await screen.findByRole("checkbox", { name: /管理员/ });
    await user.click(adminBox);
    await user.click(screen.getByRole("button", { name: "确 定" }));
    await waitFor(() => expect(assignRoles).toHaveBeenCalledOnce());
    const [id, codes] = vi.mocked(assignRoles).mock.calls[0];
    expect(id).toBe("u1");
    expect([...codes].sort()).toEqual(["admin", "employee"]);
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/pages/users/UserListPage.test.tsx`
Expected: FAIL,`Failed to resolve import "./UserListPage"`

- [ ] **Step 3: 创建 `frontend/src/pages/users/UserListPage.tsx`**

```tsx
import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Card, Input, Popconfirm, Space, Table, Tag, message } from "antd";
import { Navigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { listUsers, setUserStatus } from "../../api/users";
import { useAuthStore } from "../../store/auth";
import type { UserResponse } from "../../types/api";
import RoleAssignModal from "./RoleAssignModal";
import UserFormModal from "./UserFormModal";

const PAGE_SIZE = 20;

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : "网络异常,请稍后重试";
}

export default function UserListPage() {
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const allowed = hasPermission("user:list");

  const [items, setItems] = useState<UserResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<UserResponse | null>(null);
  const [assigning, setAssigning] = useState<UserResponse | null>(null);

  const fetchList = useCallback(async (p: number, kw: string) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listUsers({ page: p, page_size: PAGE_SIZE, ...(kw ? { keyword: kw } : {}) });
      setItems(resp.items);
      setTotal(resp.total);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (allowed) void fetchList(page, search);
  }, [allowed, page, search, fetchList]);

  function onSearch() {
    setPage(1);
    setSearch(input.trim());
  }

  async function onToggleStatus(u: UserResponse) {
    try {
      await setUserStatus(u.id, !u.is_active);
      message.success(u.is_active ? "已禁用" : "已启用");
      await fetchList(page, search);
    } catch (e) {
      message.error(errMsg(e));
    }
  }

  if (!allowed) {
    return <Navigate to="/" replace />;
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
      title: "部门",
      key: "department",
      render: (_: unknown, u: UserResponse) => u.department?.name ?? "-",
    },
    {
      title: "状态",
      key: "status",
      render: (_: unknown, u: UserResponse) =>
        u.is_active ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag>,
    },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, u: UserResponse) => (
        <Space>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setEditing(u);
              setFormOpen(true);
            }}
          >
            编辑
          </Button>
          <Button type="link" size="small" onClick={() => setAssigning(u)}>
            分配角色
          </Button>
          <Popconfirm
            title={u.is_active ? "确认禁用该用户?" : "确认启用该用户?"}
            onConfirm={() => void onToggleStatus(u)}
          >
            <Button type="link" size="small" danger={u.is_active}>
              {u.is_active ? "禁用" : "启用"}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="用户管理"
      extra={
        <Space>
          <Input.Search
            placeholder="姓名或邮箱"
            allowClear
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onSearch={onSearch}
            style={{ width: 240 }}
          />
          <Button
            type="primary"
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            新建用户
          </Button>
        </Space>
      }
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Table<UserResponse>
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p) => setPage(p),
        }}
      />
      <UserFormModal
        open={formOpen}
        editing={editing}
        onClose={() => setFormOpen(false)}
        onSuccess={() => {
          message.success(editing ? "已保存" : "已创建");
          void fetchList(page, search);
        }}
      />
      <RoleAssignModal
        user={assigning}
        onClose={() => setAssigning(null)}
        onSuccess={() => {
          message.success("角色已更新");
          void fetchList(page, search);
        }}
      />
    </Card>
  );
}
```

- [ ] **Step 4: 修改 `frontend/src/components/menu.tsx`(整体替换)**

```tsx
import { HomeOutlined, TeamOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";

export interface MenuItemConfig {
  key: string;
  label: string;
  icon: ReactNode;
  permission: string | null;
}

export const MENU_ITEMS: MenuItemConfig[] = [
  { key: "/", label: "首页", icon: <HomeOutlined />, permission: null },
  { key: "/users", label: "用户管理", icon: <TeamOutlined />, permission: "user:list" },
];
```

- [ ] **Step 5: 修改 `frontend/src/App.tsx`(整体替换)**

```tsx
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import MainLayout from "./components/MainLayout";
import RequireAuth from "./components/RequireAuth";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import UserListPage from "./pages/users/UserListPage";

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: (
      <RequireAuth>
        <MainLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <HomePage /> },
      { path: "users", element: <UserListPage /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
```

- [ ] **Step 6: 全量测试 + 类型检查 + 构建**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: 全量 39 个测试全过(地基 11 + Task2 9 + Task3 4 + Task4 3 + Task5 4 + Task6 3 + Task7 5);typecheck 零错误;build 成功

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/users/UserListPage.tsx frontend/src/pages/users/UserListPage.test.tsx frontend/src/components/menu.tsx frontend/src/App.tsx
git commit -m "feat(frontend): 用户管理列表页、菜单项与路由"
```

---

## Task 8: 全量验收(自动化门禁 + 浏览器实测)

**Files:**
- Modify: `docs/superpowers/specs/2026-07-25-frontend-auth-rbac-design.md`(§8 勾选)
- Create: `.superpowers/sdd/acceptance/*.png`(验收截图,gitignored 目录,不提交)

- [ ] **Step 1: 自动化门禁**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: 39 个测试全过;typecheck 零错误;build 成功

- [ ] **Step 2: 启动后端与 dev server**

```bash
docker compose up -d db
cd backend && uvicorn app.main:app --port 8000 &   # 后台;若已运行则跳过
cd frontend && NODE_OPTIONS=--dns-result-order=ipv4first npx vite --port 5173 &   # 后台
```

验证:`curl -s http://localhost:8000/docs -o /dev/null -w "%{http_code}"` 返回 200;`curl -s http://localhost:5173/` 返回含 `<div id="root">`。

- [ ] **Step 3: 浏览器实测(chrome-devtools 驱动,每场景截图到 `.superpowers/sdd/acceptance/`)**

严格按顺序执行;每步先 `take_snapshot` 拿 uid,操作后核对页面文本,再 `take_screenshot` 存档。

1. **登录失败**:打开 `http://localhost:5173/login`,填 `admin@company.com` / `wrongpass`,点登录 → 页面出现"邮箱或密码错误",仍在 /login。截图 `01-login-fail.png`
2. **admin 登录成功**:填 `admin@company.com` / `Admin123!` → 跳到 `/`,顶栏显示用户名,侧边菜单含"首页""用户管理"。截图 `02-admin-home.png`
3. **用户列表**:点"用户管理" → 表格渲染,至少含 admin 行;分页显示"共 N 条"。截图 `03-user-list.png`
4. **搜索**:搜索框输入 `admin` 回车 → 列表过滤为匹配行。截图 `04-user-search.png`
5. **新建用户**:点"新建用户",填邮箱 `e2e.emp@company.com`、姓名 `张测试`、初始密码 `Emp12345!`,确定 → 列表出现该行。截图 `05-user-created.png`
6. **分配角色**:该行点"分配角色" → 勾选"普通员工(employee)" → 确定 → 行内角色 Tag 出现"普通员工"。截图 `06-role-assigned.png`
7. **权限生效(API 证据)**:
   ```bash
   TOKEN=$(curl -s -X POST http://localhost:5173/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"e2e.emp@company.com","password":"Emp12345!"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
   curl -s http://localhost:5173/api/v1/auth/me -H "Authorization: Bearer $TOKEN"
   ```
   预期 `permissions` 含 `leave:create`、`leave:list`,**不含** `user:list`。输出存 `07-me-permissions.txt`
8. **编辑**:该行点"编辑",姓名改为 `张测试2` → 列表显示新姓名。截图 `08-user-edited.png`
9. **禁用**:该行点"禁用" → Popconfirm 确定 → 状态 Tag 变"禁用"。截图 `09-user-disabled.png`
10. **禁用后登录被拒**:`/login` 用 `e2e.emp@company.com` / `Emp12345!` → 显示"邮箱或密码错误"。截图 `10-disabled-login.png`
11. **启用 + 员工视角**:admin 重新启用该用户;退出登录;用 `e2e.emp@company.com` / `Emp12345!` 登录 → 菜单**无**"用户管理";地址栏直访 `http://localhost:5173/users` → 跳回 `/`。截图 `11-employee-home.png`、`12-employee-users-redirect.png`
12. **修改密码**:员工顶栏下拉 →"修改密码",旧 `Emp12345!` 新 `NewEmp123!` → 成功提示;退出登录;旧密码登录失败(截图 `13-old-pwd-fail.png`),新密码登录成功(截图 `14-new-pwd-ok.png`)
13. 停止 vite 与 uvicorn(自己启动的进程;db 容器可留)

- [ ] **Step 4: 勾选 spec §8**

`docs/superpowers/specs/2026-07-25-frontend-auth-rbac-design.md` §8 全部 `- [ ]` 改 `- [x]`(仅 §8 内)。

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-07-25-frontend-auth-rbac-design.md
git commit -m "test(frontend): P0#1 用户认证+RBAC 前端全量验收通过,勾选 spec 验收标准"
```
