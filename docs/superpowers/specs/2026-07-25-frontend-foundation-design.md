# 前端地基 — 设计文档

- 日期:2026-07-25
- 状态:已确认
- 上游:[PRD](../../prd.md)、[auth-rbac 设计](2026-07-24-auth-rbac-design.md)(API 契约/错误信封)

## 1. 范围

搭建前端工程地基,为后续三个 P0 模块(用户认证+RBAC、组织架构、请假审批)的前端开发提供可复用基础设施。

**做:**
- Vite + React 18 + TypeScript + Ant Design 5 工程脚手架
- dev server 代理 `/api` → `http://localhost:8000`
- 统一 axios 实例(token 注入、401 处理、错误信封解析)
- Zustand 鉴权 store(token/用户/权限点,持久化恢复)
- React Router 路由 + 登录守卫
- 主布局骨架(侧边菜单 + 顶栏),菜单按权限点过滤
- 占位登录页 / 占位首页

**不做(留给各 P0 循环):**
- 真登录页(归 P0#1 用户认证+RBAC)
- 任何业务页面(用户/角色/部门/请假)
- 按钮级权限的实际使用(基础设施提供 `hasPermission`,使用在业务模块)
- 单元测试以外的 E2E 测试

## 2. 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 构建工具 | Vite 5 | 快,React 官方推荐 |
| 语言 | TypeScript(strict) | 与后端 Pydantic schema 对应的类型,接口错误编译期暴露 |
| 组件库 | Ant Design 5 | OA 后台重度依赖 Table/Form/DatePicker/Modal,开箱即用;README 已定 React |
| 状态管理 | Zustand | README 已定;轻量,适合鉴权这类全局状态 |
| 请求库 | axios | 拦截器机制契合 token 注入与统一错误处理 |
| token 存储 | localStorage | 与后端 JWT 24h 过期匹配;刷新后 fetchMe 恢复会话 |
| 包管理 | npm | 标准,无额外要求 |

## 3. 目录结构

沿用现有 `src/{api,components,pages,store}` 骨架:

```
frontend/
├── index.html
├── package.json
├── vite.config.ts            # react 插件 + server.proxy /api → localhost:8000
├── tsconfig.json
└── src/
    ├── main.tsx              # 入口:AntD ConfigProvider(zhCN)+ RouterProvider
    ├── App.tsx               # 路由表
    ├── api/
    │   ├── client.ts         # axios 实例 + 拦截器
    │   └── auth.ts           # login() / getMe() 接口函数
    ├── store/
    │   └── auth.ts           # Zustand 鉴权 store
    ├── components/
    │   ├── MainLayout.tsx    # 侧边菜单 + 顶栏(用户名/退出)
    │   ├── RequireAuth.tsx   # 无 token → Navigate /login
    │   └── menu.ts           # 菜单配置(path/label/icon/permission)
    ├── pages/
    │   ├── LoginPage.tsx     # 占位(P0#1 替换)
    │   └── HomePage.tsx      # 占位首页
    └── types/
        └── api.ts            # 与后端 schema 对应的 TS 类型
```

## 4. 核心模块设计

### 4.1 api/client.ts

- `baseURL: "/api/v1"`,超时 10s
- 请求拦截器:auth store 有 token 则加 `Authorization: Bearer <token>`
- 响应拦截器:
  - 2xx 直接返回 data
  - 401 → 清空 auth store,跳转 `/login`(避免循环:登录请求自身的 401 不跳转)
  - 业务错误(400/403/404/409/422 且响应体为 `{"error":{code,message}}`)→ 抛出规范化 `ApiError {code, message}`
  - 其他(网络错误/5xx/非信封格式)→ 抛出 `ApiError {code: "UNKNOWN", message: "网络异常,请稍后重试"}`

### 4.2 store/auth.ts(Zustand)

```ts
interface AuthState {
  token: string | null;              // 初始从 localStorage 读
  user: CurrentUser | null;          // id/name/email/roles/permissions
  login(email: string, password: string): Promise<void>;  // 调 api/auth.login → 存 token → fetchMe
  fetchMe(): Promise<void>;         // GET /auth/me 填充 user
  logout(): void;                   // 清 token + user + localStorage
  hasPermission(code: string): boolean;
}
```

- token 变更即写 localStorage;`logout` 清除
- 应用启动时若有 token 无 user,`RequireAuth` 内触发 `fetchMe` 恢复会话;fetchMe 401 时由拦截器清态跳登录

### 4.3 路由

| 路径 | 组件 | 守卫 |
|---|---|---|
| `/login` | LoginPage(占位) | 无 |
| `/` | MainLayout → HomePage(占位) | RequireAuth |

后续模块在 MainLayout 下加子路由。`RequireAuth`:无 token → `<Navigate to="/login">`;有 token 无 user → 触发 fetchMe 并显示加载态。

### 4.4 菜单配置(components/menu.ts)

```ts
{ key: "/", label: "首页", icon: <HomeOutlined />, permission: null }
```

`MainLayout` 按 `hasPermission(permission)` 过滤(permission 为 null 恒显示)。P0 模块只追加条目,不改布局代码。

### 4.5 types/api.ts

与后端 schema 对齐:`CurrentUser {id, name, email, roles, permissions}`、`LoginResponse {access_token, token_type, expires_in}`、`ApiErrorBody {error: {code, message}}`。后续模块在此追加各自类型。

## 5. 错误处理

- 统一在 client 拦截器规范化为 `ApiError`,页面/调用方用 AntD `message.error(err.message)` 提示
- 表单级字段错误由业务模块自行处理(P0#1 起)
- 占位页不展示错误 UI,仅保证拦截器逻辑有单测覆盖

## 6. 测试策略

Vitest + jsdom:

- `store/auth.test.ts`:login 成功(存 token + fetchMe)/ 失败(抛 ApiError,不存 token)、logout 清态、hasPermission 命中/未命中/无 user
- `api/client.test.ts`:401 清态跳登录、错误信封解析为 ApiError、非信封错误归为 UNKNOWN
- 质量门:`tsc --noEmit` 零错误、`vite build` 成功
- 冒烟:dev server 启动,代理打到真实后端(`/api/v1/auth/login` 错误凭据返回 401 信封)

## 7. 环境要求

- Node.js ≥ 18,npm
- 后端按 README 起在 :8000(docker compose db + alembic + seed + uvicorn)

## 8. 验收标准

- [ ] `npm run dev` 启动,访问 `/` 无 token 时跳转 `/login` 占位页
- [ ] dev server 代理 `/api/v1/*` 到 :8000(可用 curl 经 5173 端口验证)
- [ ] `npm test` 全绿(store + client 单测)
- [ ] `tsc --noEmit` 零错误,`vite build` 成功
- [ ] 主布局渲染侧边菜单(仅"首页")与顶栏,退出按钮清态跳登录
- [ ] 有 token 时刷新页面自动 fetchMe 恢复用户(可在 DevTools 手工置 token 验证)
