# 前端 P0#2 组织架构 — 设计文档

- 日期:2026-07-25
- 关联:PRD §3.2、后端 spec `2026-07-24-org-structure-design.md`、前端 spec `2026-07-25-frontend-foundation-design.md`、`2026-07-25-frontend-auth-rbac-design.md`

## 1. 范围

**本期做**(全部在前端 `frontend/` 内):

- 部门管理页:左树右表单页——部门树 CRUD(新建/改名/移动/删除)+ 选中部门人员列表
- 用户管理页追加"归属"操作:设置用户部门与直属上级(`PATCH /users/{id}/org`)
- 对应 api 层(`api/departments.ts`、`api/users.ts` 追加)与组件级测试

**本期不做**:

- 拖拽移动部门(编辑弹窗内 TreeSelect 选父部门代替)
- 人员调动历史留痕(后端不做)
- 查看子部门人员穿透(后端 Manager 数据范围仅直属本部门)
- 用户创建时设置部门(后端契约:创建接口不扩展,归属统一走 `/users/{id}/org`)

## 2. 关键决策

| 决策点 | 结论 |
|---|---|
| 页面形态 | 单页左树右表:左侧部门树(CRUD),右侧选中部门人员列表 |
| 人员归属入口 | 用户管理页行操作追加"归属"按钮,弹窗编辑;部门页人员列表只读 |
| Manager 视角 | 与 admin 同一页面:CRUD 按钮按权限点隐藏;看其他部门成员由后端 403 兜底,页内 Alert |
| 移动部门 | 编辑弹窗内 TreeSelect 重选父部门(候选排除自身与后代);防环后端校验兜底 |
| 服务器数据管理 | 页面内 `useState` + `useEffect`,无新依赖(沿用 P0#1) |
| 树数据 | `GET /departments` 一次性返回整棵嵌套树,不分页(后端契约,量级几十~几百) |

## 3. 后端接口契约(已与 `backend/app/schemas`、`backend/app/api/v1` 核对)

全部经统一 axios client(baseURL `/api/v1`,错误信封 → `ApiError(code, message)`)。

| 方法 | 路径 | 请求 | 响应 | 权限 |
|---|---|---|---|---|
| POST | `/departments` | `{name(1-100), parent_id?}` | `DepartmentResponse`,201 | department:create |
| GET | `/departments` | — | `DepartmentNode[]` 嵌套树 | department:list |
| PATCH | `/departments/{id}` | `{name?, parent_id?}` | `DepartmentResponse` | department:update |
| DELETE | `/departments/{id}` | — | 204 | department:delete |
| GET | `/departments/{id}/members?page&page_size` | — | `UserListResponse` | department:members(+数据范围) |
| PATCH | `/users/{id}/org` | `{department_id?, manager_id?}` | `UserResponse` | user:update |

```ts
// types/api.ts 追加
interface DepartmentNode {
  id: string;
  name: string;
  parent_id: string | null;
  member_count: number;
  children: DepartmentNode[];
}
interface DepartmentResponse { id: string; name: string; parent_id: string | null }
interface UserOrgUpdate { department_id?: string | null; manager_id?: string | null }
```

错误码(沿用后端):同级重名/有员工或子部门禁删/移动成环 → 409 `CONFLICT`;上级不在同部门/上级是自己/无部门设上级 → 422 `VALIDATION_ERROR`;越权看成员 → 403 `FORBIDDEN`。前端不区分 code,统一展示 `e.message`。

## 4. 页面与组件

```
路由(App.tsx 追加,/departments 挂在 RequireAuth/MainLayout 下)
└── /departments  DepartmentPage  前置检查 department:list,无权限 <Navigate to="/" replace />

src/pages/departments/
├── DepartmentPage.tsx      左树右表布局;选中部门 state;CRUD 成功后刷新树(+成员)
├── DeptTreePanel.tsx       AntD Tree(整棵树,节点标题含 member_count);
│                           顶部"新建部门"按钮;节点悬停操作:新建子部门/编辑/删除
│                           (按 department:create/update/delete 显隐,manager 全隐藏)
├── DeptMembersPanel.tsx    选中部门的成员 Table(分页 page_size 20,复用列:姓名/邮箱/角色/状态);
│                           未选中部门时显示空态提示;403 时 Alert
└── DeptFormModal.tsx       新建/编辑复用:名称必填(1-100);
                           编辑模式含 TreeSelect 选父部门(可清空=根部门,
                           候选树排除自身及后代节点)

src/pages/users/
└── UserOrgModal.tsx        "归属"弹窗:TreeSelect 选部门(可清空)+ Select 选直属上级;
                           上级候选 = 所选部门成员(listDeptMembers 拉取),排除用户自己;
                           切换部门时清空已选上级;提交 {department_id, manager_id}

UserListPage 修改:
- 行操作追加"归属"按钮(按 user:update 显隐,admin 可见)
- "部门"列已有(P0#1),无需改动

menu.tsx:MENU_ITEMS 追加
  { key: "/departments", label: "部门管理", icon: <ApartmentOutlined />, permission: "department:list" }
```

### 交互细节

**DepartmentPage**
- 状态:`tree/selectedId/members/membersTotal/membersPage/loading`,进入页面拉整棵树,默认选中第一个根节点
- 树 CRUD 成功:`message.success` + 重新拉树(保持选中部门;若被删的是选中部门则清空选中)
- 成员列表:选中部门变化或翻页时拉取;失败(含 403)`Alert` 不白屏

**DeptTreePanel**
- 节点标题:`名称(member_count)`;删除用 Popconfirm 确认,409 时 `message.error(e.message)`
- 树默认展开全部节点(量级小)

**DeptFormModal**
- 新建:名称 + 父部门(TreeSelect,默认填入"新建子部门"入口的父节点;顶部入口则为空=根)
- 编辑:名称 + 父部门 TreeSelect(候选排除自身及后代,防环前端提示;后端 409 兜底)
- 失败:Modal 顶部 `Alert` 显示 `ApiError.message`,不关闭

**UserOrgModal**
- 打开时预填当前 `department` / `manager`;部门 TreeSelect 数据来自 `listDeptTree()`
- 选中部门变化 → 重新拉该部门成员作为上级候选(排除自己);上级可清空
- 保存:`updateUserOrg(id, {department_id, manager_id})`,成功 `message.success` + 刷新列表
- 失败:Modal 内 `Alert` 显示 `ApiError.message`(含 422 上级校验),不关闭

## 5. api 层

新建 `api/departments.ts`:`listDeptTree()`、`createDepartment({name, parent_id?})`、`updateDepartment(id, {name?, parent_id?})`、`deleteDepartment(id)`、`listDeptMembers(id, {page, page_size})` —— 纯函数,直接 `client` 调用,不 try/catch。

`api/users.ts` 追加:

```ts
export async function updateUserOrg(id: string, body: UserOrgUpdate): Promise<UserResponse> {
  const { data } = await client.patch<UserResponse>(`/users/${id}/org`, body);
  return data;
}
```

## 6. 错误处理

- 页面层统一 `catch`:ApiError → 展示 `e.message`;其余已被拦截器归为 UNKNOWN(沿用 P0#1)
- 409/422 业务错误(重名/禁删/成环/上级校验)全部依赖后端错误信封透出,前端不做 code 分支
- 字段级校验(部门名 1-100)前端 Form rules 完成

## 7. 测试策略

沿用 P0#1 测试基建(zhCN `ConfigProvider` 包装、jsdom polyfill、axios-mock-adapter、真实 store + `setState` 预置)。

| 测试文件 | 覆盖 |
|---|---|
| `api/departments.test.ts` | URL/方法/参数正确(tree、create、update、delete、members 分页),错误信封透传;`updateUserOrg` 归 `api/users.test.ts` 追加 |
| `pages/departments/DepartmentPage.test.tsx` | 无 department:list 权限跳回;树渲染+默认选中;成员列表渲染;选中切换重新拉取 |
| `pages/departments/DeptFormModal.test.tsx` | 新建/编辑两模式校验与提交参数;编辑候选排除自身及后代;失败显示错误不关闭 |
| `pages/users/UserOrgModal.test.tsx` | 预填;切换部门清空上级;提交参数(含清空语义);失败显示错误不关闭 |

## 8. 验收标准

**自动化门禁:**

- [ ] `npm test` 全绿(P0#1 45 + 本期新增)
- [ ] `tsc --noEmit` 零错误,`vite build` 成功

**浏览器实测(由执行 Agent 使用 chrome-devtools 驱动真实浏览器完成,非人工点检;前置:后端 :8000 + dev server :5173 代理;截图存档至 `.superpowers/sdd/acceptance/`):**

- [ ] admin 进部门管理页:树渲染(含 member_count),默认选中根部门,右侧成员列表渲染
- [ ] 新建根部门/子部门成功,树即时刷新;同级重名 → 错误提示
- [ ] 编辑部门改名生效;TreeSelect 移动部门到另一父节点生效;移动到自身后代 → 409 错误提示
- [ ] 删除空部门成功;删除有员工的部门 → 409 错误提示
- [ ] 用户管理"归属":为用户设置部门+直属上级成功,列表部门列更新;上级选其他部门的人 → 422 错误提示
- [ ] manager 账号(seed 或验收创建)登录:菜单有"部门管理",无 CRUD 按钮;查看本部门成员正常;查看其他部门成员 → 403 错误提示
- [ ] 无 department:list 权限账号(employee)登录:菜单无"部门管理",直访 /departments 跳回首页
- [ ] 每个场景截图存档至 `.superpowers/sdd/acceptance/`,作为验收证据
