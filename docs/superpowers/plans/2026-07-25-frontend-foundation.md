# 前端地基 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建前端工程地基:Vite + React + TS + AntD 脚手架、统一 axios 实例、Zustand 鉴权 store、路由守卫与主布局骨架,为三个 P0 模块前端开发提供基础设施。

**Architecture:** SPA(Vite dev server 代理 `/api` → `localhost:8000`);所有请求经统一 axios 实例(baseURL `/api/v1`,token 注入/401 处理/错误信封规范化);Zustand 管鉴权状态(token 持久化 localStorage,刷新后 fetchMe 恢复);React Router v6 + RequireAuth 守卫;主布局菜单按权限点过滤。

**Tech Stack:** Vite 5、React 18、TypeScript(strict)、Ant Design 5、Zustand、React Router 6、axios、Vitest + jsdom + axios-mock-adapter

**Spec:** `docs/superpowers/specs/2026-07-25-frontend-foundation-design.md`(验收标准见 §8)

**执行纪律(继承后端模块):**
- 每步 TDD:先写失败测试 → 确认失败 → 实现 → 确认通过 → 提交
- 提交只 `git add` 明确列出的文件,**严禁** `git add .` / `git add -A`
- 所有命令(npm/npx/vitest)在 `frontend/` 目录下执行,git 命令在仓库根执行
- 设计决策级变更必须同步 spec;实现细节修复不动 spec
- Shell 为 git bash(Windows),用 Unix 语法;`.gitignore` 已含 `node_modules/` 与 `dist/`,无需改动

**与 spec 的一处偏差(实现细节级):** spec §3 目录树中菜单配置写作 `components/menu.ts`,因文件内含 JSX(icon),实际为 `components/menu.tsx`。

**后端接口契约(已与 backend/app/schemas 核对,TS 类型以此为准):**
- `POST /auth/login` 请求 `{email, password}` → `TokenResponse {access_token: str, token_type: str, expires_in: int}`
- `GET /auth/me` → `MeResponse {id: uuid, email: str, name: str, is_active: bool, roles: [{code, name}], department: {id, name} | null, manager: {id, name} | null, permissions: [str]}`
- 业务错误信封:`{"error": {"code": "...", "message": "..."}}`

---

## Task 1: Vite 工程脚手架

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`(占位,Task 4 替换)

- [ ] **Step 1: 创建 `frontend/package.json`**

```json
{
  "name": "oa-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@ant-design/icons": "^5.5.1",
    "antd": "^5.21.0",
    "axios": "^1.7.7",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2",
    "zustand": "^4.5.5"
  },
  "devDependencies": {
    "@types/react": "^18.3.10",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.2",
    "axios-mock-adapter": "^2.0.0",
    "jsdom": "^25.0.1",
    "typescript": "^5.6.2",
    "vite": "^5.4.8",
    "vitest": "^2.1.2"
  }
}
```

- [ ] **Step 2: 创建 `frontend/vite.config.ts`**

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
  },
});
```

- [ ] **Step 3: 创建 `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["vitest/globals"]
  },
  "include": ["src", "vite.config.ts"]
}
```

- [ ] **Step 4: 创建 `frontend/index.html`**

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>OA 管理系统</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: 创建 `frontend/src/main.tsx` 与 `frontend/src/App.tsx`(占位版)**

`src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

`src/App.tsx`:

```tsx
export default function App() {
  return <div>OA 管理系统</div>;
}
```

- [ ] **Step 6: 安装依赖**

Run: `cd frontend && npm install`
Expected: 成功生成 `node_modules/` 与 `package-lock.json`(耗时数分钟属正常)

- [ ] **Step 7: 验证构建与类型检查**

Run: `cd frontend && npm run build`
Expected: `tsc --noEmit` 零错误,`vite build` 成功输出 `dist/`

- [ ] **Step 8: 验证 dev server 可启动**

Run: `cd frontend && npx vite --port 5173`(后台运行,`curl -s http://localhost:5173/` 返回含 `<div id="root">` 的 HTML 后停止)
Expected: 返回 index.html 内容

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/tsconfig.json frontend/index.html frontend/src/main.tsx frontend/src/App.tsx
git commit -m "feat(frontend): Vite + React + TS + AntD 工程脚手架"
```

---

## Task 2: 类型定义 + axios 实例

**Files:**
- Create: `frontend/src/types/api.ts`
- Create: `frontend/src/api/client.ts`
- Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- Produces(后续任务依赖): `TOKEN_KEY`、`ApiError {code, message}`、`navigation.toLogin()`、`onUnauthorized(fn)`、`client`(axios 实例,baseURL `/api/v1`)、`CurrentUser`、`LoginResponse`、`ApiErrorBody`

- [ ] **Step 1: 写失败测试 `frontend/src/api/client.test.ts`**

```ts
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/api/client.test.ts`
Expected: FAIL,`Failed to resolve import "./client"`

- [ ] **Step 3: 创建 `frontend/src/types/api.ts`**

```ts
export interface RoleBrief {
  code: string;
  name: string;
}

export interface DepartmentBrief {
  id: string;
  name: string;
}

export interface UserBrief {
  id: string;
  name: string;
}

export interface CurrentUser {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  roles: RoleBrief[];
  department: DepartmentBrief | null;
  manager: UserBrief | null;
  permissions: string[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}
```

- [ ] **Step 4: 创建 `frontend/src/api/client.ts`**

```ts
import axios from "axios";

export const TOKEN_KEY = "oa_token";

export class ApiError extends Error {
  code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
  }
}

// 可替换的导航实现,便于测试(jsdom 不支持真实跳转)
export const navigation = {
  toLogin: () => {
    window.location.href = "/login";
  },
};

// 401 时由 auth store 注册的回调(清空内存态,避免 client → store 循环依赖)
let unauthorizedHandler: (() => void) | null = null;
export function onUnauthorized(fn: () => void): void {
  unauthorizedHandler = fn;
}

export const client = axios.create({
  baseURL: "/api/v1",
  timeout: 10000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error)) {
      const resp = error.response;
      if (resp?.status === 401) {
        localStorage.removeItem(TOKEN_KEY);
        unauthorizedHandler?.();
        const isLoginRequest = (resp.config.url ?? "").includes("/auth/login");
        if (!isLoginRequest && window.location.pathname !== "/login") {
          navigation.toLogin();
        }
      }
      const body: unknown = resp?.data;
      if (
        typeof body === "object" &&
        body !== null &&
        "error" in body &&
        typeof (body as { error?: { code?: unknown } }).error?.code === "string"
      ) {
        const { code, message } = (body as { error: { code: string; message: string } })
          .error;
        return Promise.reject(new ApiError(code, message));
      }
    }
    return Promise.reject(new ApiError("UNKNOWN", "网络异常,请稍后重试"));
  }
);
```

注意:
- token 直接读写 localStorage,不 import store——否则 client → store → api/auth → client 形成循环依赖
- `navigation` 对象便于测试 spy;`onUnauthorized` 回调由 store 注册

- [ ] **Step 5: 运行确认通过**

Run: `cd frontend && npx vitest run src/api/client.test.ts`
Expected: PASS(6 个用例)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat(frontend): 类型定义与 axios 实例(token 注入/401 处理/错误信封)"
```

---

## Task 3: auth API + 鉴权 store

**Files:**
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/store/auth.ts`
- Test: `frontend/src/store/auth.test.ts`

**Interfaces:**
- Consumes: `client`、`TOKEN_KEY`、`onUnauthorized`、`ApiError`(Task 2)、`CurrentUser`、`LoginResponse`(Task 2)
- Produces: `useAuthStore`(Zustand hook,state `{token, user}`,actions `login(email, password)`、`fetchMe()`、`logout()`、`hasPermission(code)`);`authApi.login` / `authApi.getMe`

- [ ] **Step 1: 写失败测试 `frontend/src/store/auth.test.ts`**

```ts
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/store/auth.test.ts`
Expected: FAIL,`Failed to resolve import "./auth"`

- [ ] **Step 3: 创建 `frontend/src/api/auth.ts`**

```ts
import { client } from "./client";
import type { CurrentUser, LoginResponse } from "../types/api";

export async function login(email: string, password: string): Promise<LoginResponse> {
  const { data } = await client.post<LoginResponse>("/auth/login", { email, password });
  return data;
}

export async function getMe(): Promise<CurrentUser> {
  const { data } = await client.get<CurrentUser>("/auth/me");
  return data;
}
```

- [ ] **Step 4: 创建 `frontend/src/store/auth.ts`**

```ts
import { create } from "zustand";

import { TOKEN_KEY, onUnauthorized } from "../api/client";
import * as authApi from "../api/auth";
import type { CurrentUser } from "../types/api";

interface AuthState {
  token: string | null;
  user: CurrentUser | null;
  login: (email: string, password: string) => Promise<void>;
  fetchMe: () => Promise<void>;
  logout: () => void;
  hasPermission: (code: string) => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem(TOKEN_KEY),
  user: null,

  async login(email, password) {
    const resp = await authApi.login(email, password);
    localStorage.setItem(TOKEN_KEY, resp.access_token);
    set({ token: resp.access_token });
    await get().fetchMe();
  },

  async fetchMe() {
    const user = await authApi.getMe();
    set({ user });
  },

  logout() {
    localStorage.removeItem(TOKEN_KEY);
    set({ token: null, user: null });
  },

  hasPermission(code) {
    return get().user?.permissions.includes(code) ?? false;
  },
}));

// 401 时清空内存态(client.ts 已负责清 localStorage 与跳转)
onUnauthorized(() => {
  useAuthStore.setState({ token: null, user: null });
});
```

- [ ] **Step 5: 运行确认通过**

Run: `cd frontend && npx vitest run src/store/auth.test.ts`
Expected: PASS(5 个用例)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/auth.ts frontend/src/store/auth.ts frontend/src/store/auth.test.ts
git commit -m "feat(frontend): auth API 与 Zustand 鉴权 store"
```

---

## Task 4: 路由守卫 + 主布局 + 占位页

**Files:**
- Create: `frontend/src/components/RequireAuth.tsx`
- Create: `frontend/src/components/menu.tsx`
- Create: `frontend/src/components/MainLayout.tsx`
- Create: `frontend/src/pages/LoginPage.tsx`
- Create: `frontend/src/pages/HomePage.tsx`
- Modify: `frontend/src/App.tsx`(整体替换)
- Modify: `frontend/src/main.tsx`(加 AntD ConfigProvider)

**Interfaces:**
- Consumes: `useAuthStore`(Task 3)
- Produces: `MainLayout`(后续模块在其 `children` 下加子路由)、`RequireAuth`、`MENU_ITEMS`(后续模块追加条目)、`/login` 与 `/` 路由

- [ ] **Step 1: 创建 `frontend/src/components/RequireAuth.tsx`**

```tsx
import { useEffect, useState, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { Spin } from "antd";

import { useAuthStore } from "../store/auth";

export default function RequireAuth({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (token && !user) {
      setLoading(true);
      useAuthStore
        .getState()
        .fetchMe()
        .catch(() => useAuthStore.getState().logout())
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }
    return () => {
      cancelled = true;
    };
  }, [token, user]);

  if (!token) {
    return <Navigate to="/login" replace />;
  }
  if (loading || !user) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          height: "100vh",
        }}
      >
        <Spin size="large" />
      </div>
    );
  }
  return <>{children}</>;
}
```

- [ ] **Step 2: 创建 `frontend/src/components/menu.tsx`**

```tsx
import { HomeOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";

export interface MenuItemConfig {
  key: string;
  label: string;
  icon: ReactNode;
  permission: string | null;
}

export const MENU_ITEMS: MenuItemConfig[] = [
  { key: "/", label: "首页", icon: <HomeOutlined />, permission: null },
];
```

- [ ] **Step 3: 创建 `frontend/src/components/MainLayout.tsx`**

```tsx
import { Dropdown, Layout, Menu } from "antd";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuthStore } from "../store/auth";
import { MENU_ITEMS } from "./menu";

export default function MainLayout() {
  const user = useAuthStore((s) => s.user);
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const navigate = useNavigate();
  const location = useLocation();

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
              items: [{ key: "logout", label: "退出登录" }],
              onClick: ({ key }) => {
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
    </Layout>
  );
}
```

- [ ] **Step 4: 创建占位页 `frontend/src/pages/LoginPage.tsx` 与 `frontend/src/pages/HomePage.tsx`**

`LoginPage.tsx`:

```tsx
export default function LoginPage() {
  return <div>登录页(由 P0 用户认证模块实现)</div>;
}
```

`HomePage.tsx`:

```tsx
export default function HomePage() {
  return <h2>欢迎使用 OA 管理系统</h2>;
}
```

- [ ] **Step 5: 整体替换 `frontend/src/App.tsx`**

```tsx
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import MainLayout from "./components/MainLayout";
import RequireAuth from "./components/RequireAuth";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: (
      <RequireAuth>
        <MainLayout />
      </RequireAuth>
    ),
    children: [{ index: true, element: <HomePage /> }],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
```

- [ ] **Step 6: 修改 `frontend/src/main.tsx`(加 AntD 中文 locale)**

整体替换为:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";

import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN}>
      <App />
    </ConfigProvider>
  </React.StrictMode>
);
```

- [ ] **Step 7: 全量测试 + 类型检查 + 构建**

Run: `cd frontend && npm test && npm run build`
Expected: 11 个测试全过;`tsc --noEmit` 零错误;`vite build` 成功

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/RequireAuth.tsx frontend/src/components/menu.tsx frontend/src/components/MainLayout.tsx frontend/src/pages/LoginPage.tsx frontend/src/pages/HomePage.tsx frontend/src/App.tsx frontend/src/main.tsx
git commit -m "feat(frontend): 路由守卫、主布局骨架与占位页"
```

---

## Task 5: 全量验收

- [ ] **Step 1: 全量测试与构建**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: 全过、零类型错误、构建成功

- [ ] **Step 2: 代理冒烟(需后端在 :8000 运行)**

前置:`docker compose up -d db`,后端已迁移并 seed,`cd backend && uvicorn app.main:app`(若已在运行可跳过)

```bash
cd frontend && npx vite --port 5173 &   # 后台启动 dev server
sleep 5
curl -s -X POST http://localhost:5173/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"nobody@x.com","password":"wrong"}'
```

Expected: 返回 `{"error":{"code":"INVALID_CREDENTIALS","message":"邮箱或密码错误"}}`(HTTP 401),证明 dev server 代理与错误信封链路通。验证后停止 dev server(`kill %1` 或任务管理器)。

- [ ] **Step 3: 对照 spec §8 验收标准逐项确认并勾选**

`docs/superpowers/specs/2026-07-25-frontend-foundation-design.md` §8:

- `npm run dev` 启动,无 token 访问 `/` 跳 `/login` 占位页:Step 2 冒烟 + 路由守卫实现
- 代理 `/api/v1/*` 到 :8000:Step 2 curl 验证
- `npm test` 全绿:Step 1
- `tsc --noEmit` 零错误、`vite build` 成功:Step 1
- 主布局渲染侧边菜单(仅"首页")与顶栏,退出清态跳登录:Task 4 实现
- 有 token 刷新自动 fetchMe 恢复:RequireAuth 实现 + store 单测

将 §8 全部 `- [ ]` 改为 `- [x]`。

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-07-25-frontend-foundation-design.md
git commit -m "test(frontend): 前端地基全量验收通过,勾选 spec 验收标准"
```
