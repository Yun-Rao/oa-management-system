# 前端 P0#1 用户认证 + RBAC — 设计文档

关联:PRD §3.1、后端 spec `2026-07-24-auth-rbac-design.md`、前端地基 spec `2026-07-25-frontend-foundation-design.md`

## 1. 范围

**本期做**(全部在前端 `frontend/` 内):

- 真登录页(替换地基占位页):居中卡片,邮箱+密码登录
- 修改密码:顶栏下拉新增入口,Modal 表单
- 用户管理页(Admin):列表 + 关键字搜索 + 分页 + 新建/编辑/启用禁用 + 分配角色
- 对应 api 层(`api/users.ts`、`api/roles.ts`、`api/auth.ts` 追加 changePassword)与组件级测试

**本期不做**:

- 组织架构相关字段的编辑(department/manager 归 P0#2 前端,用户表只读展示部门列)
- 角色本身的 CRUD(后端无此接口,角色为 seed 内置)
- 注册/忘记密码(后端明确不做)
- 单元格级行内编辑、批量操作

## 2. 关键决策

| 决策点 | 结论 |
|---|---|
| 服务器数据管理 | 页面内 `useState` + `useEffect`,无新依赖(YAGNI,与地基轻量风格一致) |
| 登录页布局 | 居中卡片(纯色/淡渐变背景 + 系统名 + 表单) |
| 用户管理交互 | Table + Modal(新建/编辑复用一个 FormModal;分配角色独立 Modal) |
| 修改密码入口 | MainLayout 顶栏用户下拉,新增"修改密码"菜单项 |
| 权限控制 | 菜单项按 `user:list` 过滤;页面直访由前端 `<Navigate>` 前置拦截 + 后端 403 兜底 |
| 角色分配保存 | PUT 整体替换 `role_codes`(对齐后端设计) |
| 测试深度 | 组件级:`@testing-library/react` + `user-event` + `jest-dom`,api 层延续 axios-mock-adapter |

## 3. 后端接口契约(已与 `backend/app/schemas` 核对)

全部经统一 axios client(baseURL `/api/v1`,错误信封 → `ApiError(code, message)`)。

| 方法 | 路径 | 请求 | 响应 | 权限 |
|---|---|---|---|---|
| POST | `/auth/change-password` | `{old_password, new_password(8-72)}` | 204 无体 | 登录 |
| GET | `/users?page&page_size&keyword?` | — | `UserListResponse` | user:list |
| POST | `/users` | `{email, name(1-100), password(8-72)}` | `UserResponse` | user:create |
| PATCH | `/users/{id}` | `{email?, name?}` | `UserResponse` | user:update |
| PATCH | `/users/{id}/status` | `{is_active}` | `UserResponse` | user:disable |
| PUT | `/users/{id}/roles` | `{role_codes: string[]}` | `UserResponse` | role:assign |
| GET | `/roles` | — | `RoleResponse[]` | role:list |

```ts
// types/api.ts 追加
interface UserResponse {
  id: string; email: string; name: string; is_active: boolean;
  roles: RoleBrief[];                 // 复用现有 { code, name }
  department: DepartmentBrief | null; // 复用现有 { id, name }
  manager: UserBrief | null;          // 复用现有 { id, name }
}
interface UserListResponse { items: UserResponse[]; total: number; page: number; page_size: number }
interface PermissionBrief { code: string; name: string }
interface RoleResponse { code: string; name: string; description: string | null; permissions: PermissionBrief[] }
```

## 4. 页面与组件

```
路由(App.tsx 追加,/users 挂在 RequireAuth/MainLayout 下)
├── /login   LoginPage     公开;已登录访问跳 /
└── /users   UserListPage  前置检查 user:list,无权限 <Navigate to="/" replace />

src/pages/
├── LoginPage.tsx                 整体替换占位版
└── users/
    ├── UserListPage.tsx          搜索 + Table(分页受控)+ 行操作 + "新建用户"
    ├── UserFormModal.tsx         创建/编辑复用(创建模式多"初始密码"字段)
    └── RoleAssignModal.tsx       打开时拉 listRoles,Checkbox.Group,PUT 整体替换

src/components/
└── ChangePasswordModal.tsx       旧/新/确认密码;MainLayout 顶栏下拉新增入口

menu.tsx:MENU_ITEMS 追加
  { key: "/users", label: "用户管理", icon: <TeamOutlined />, permission: "user:list" }
```

### 交互细节

**LoginPage**
- 提交 → `useAuthStore.login(email, password)` → 成功 `navigate("/", { replace: true })`
- 失败 → 页内 `Alert` 显示 `ApiError.message`(后端统一"邮箱或密码错误");提交中按钮 loading 禁用
- `token` 已存在时 `<Navigate to="/" replace />`

**UserListPage**
- 状态:`items/total/page/pageSize/keyword/loading`,单一 `fetchList()` 供初次、搜索、翻页、操作成功后复用
- 搜索:输入框回车或点按钮,重置到第 1 页;`page_size` 默认 20
- 列:姓名、邮箱、角色(Tag 列表)、部门、状态(Tag 启用/禁用)、操作(编辑 / 分配角色 / 启用|禁用)
- 启用禁用:`Popconfirm` 确认 → `setUserStatus` → `message.success` + 刷新当前页
- 新建/编辑/分配角色成功:`message.success` + 刷新当前页
- 拉取失败(含 403):页内 `Alert` 错误态,不白屏

**UserFormModal**
- 创建:邮箱(必填+格式)、姓名(必填 1-100)、初始密码(必填 8-72)
- 编辑:邮箱、姓名(同校验),无密码字段;提交只带变更语义的全量两字段(后端两字段均可选)
- 失败:Modal 顶部 `Alert` 显示 `ApiError.message`,不关闭

**RoleAssignModal**
- 打开时并行 `listRoles()`;初始勾选用户现有 `roles[].code`
- 保存:`assignRoles(userId, 选中 codes)`(可为空数组 = 清空角色)

**ChangePasswordModal**
- 旧密码必填;新密码 8-72;确认新密码需一致(全部前端 Form rules)
- 成功:`message.success` + 关闭清空;失败:Modal 内 `Alert` 显示 `ApiError.message`

## 5. api 层

`api/auth.ts` 追加:

```ts
export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  await client.post("/auth/change-password", { old_password: oldPassword, new_password: newPassword });
}
```

新建 `api/users.ts`:`listUsers({page, page_size, keyword?})`、`createUser`、`updateUser`、`setUserStatus`、`assignRoles` —— 纯函数,直接 `client` 调用,不 try/catch。

新建 `api/roles.ts`:`listRoles()`。

## 6. 错误处理

- 页面层统一 `catch`:ApiError → 展示 `e.message`;其余已被拦截器归为 UNKNOWN
- 登录接口 401 不跳登录页(地基已豁免);其他请求 401 由拦截器清态跳登录,页面不处理
- 字段级校验(邮箱格式/密码长度/确认一致)全部前端 Form rules 完成,不打后端

## 7. 测试策略

新增 devDependencies:`@testing-library/react`、`@testing-library/user-event`、`@testing-library/jest-dom`。

新建 `src/test/setup.ts`:jsdom 下 antd 所需 polyfill(`matchMedia`、`ResizeObserver`),在 `vite.config.ts` 的 `test.setupFiles` 注册。

| 测试文件 | 覆盖 |
|---|---|
| `api/users.test.ts` + `api/roles.test.ts` | URL/方法/参数正确(query、body、路径 id),错误信封透传 |
| `pages/LoginPage.test.tsx` | 提交调 store.login;成功跳 /;失败显示错误;已登录跳 / |
| `pages/users/UserListPage.test.tsx` | 渲染行;搜索触发 fetchList 带 keyword;禁用流程(Popconfirm 确认 → setUserStatus 参数);打开分配弹窗勾选保存 → assignRoles 参数 |
| `pages/users/UserFormModal.test.tsx` | 创建/编辑两模式校验与提交参数;失败显示错误不关闭 |
| `components/ChangePasswordModal.test.tsx` | 确认密码不一致不提交;成功调 changePassword |

组件测试 mock api 层(`vi.mock`),不启动真实请求;store 用真实 `useAuthStore` 并 `setState` 预置。

## 8. 验收标准

**自动化门禁:**

- [ ] `npm test` 全绿(地基 11 + 本期新增)
- [ ] `tsc --noEmit` 零错误,`vite build` 成功

**浏览器实测(由执行 Agent 使用 chrome-devtools 驱动真实浏览器完成,非人工点检;前置:后端 :8000 + dev server :5173 代理):**

- [ ] 错误密码登录:页面显示"邮箱或密码错误",不跳转
- [ ] admin 登录成功:跳转首页,顶栏显示用户名,菜单含"用户管理"
- [ ] 用户管理:列表渲染;关键字搜索过滤;翻页;新建用户后出现在列表
- [ ] 编辑用户姓名生效;禁用某用户后,该用户登录被 401 拒绝;为其分配角色后该用户 `GET /auth/me` 权限点变化
- [ ] 非 admin(无 user:list)登录:菜单无"用户管理",直访 /users 跳回首页
- [ ] 顶栏"修改密码":改密成功后旧密码登录失败、新密码可登录
- [ ] 每个场景截图存档至 `.superpowers/sdd/`(或执行会话指定的验收目录),作为验收证据
