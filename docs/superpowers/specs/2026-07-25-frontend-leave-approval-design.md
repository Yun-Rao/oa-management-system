# 前端 P0#3 请假审批 — 设计文档

- 日期:2026-07-25
- 关联:PRD §3.3.1、§3.3.3,后端 spec `2026-07-24-leave-approval-design.md`(后端已完成),前端 spec `2026-07-25-frontend-foundation-design.md`、`2026-07-25-frontend-auth-rbac-design.md`、`2026-07-25-frontend-org-structure-design.md`

## 1. 范围

**本期做**(全部在前端 `frontend/` 内):

- 请假审批页 `/leaves`:Tabs 三视图——我的申请 / 待我审批 / 全部记录,按权限点显隐
- 我的申请:新建申请弹窗、status 筛选、撤回(pending)、详情
- 待我审批:通过 / 驳回(必填原因)、详情
- 全部记录(admin):部门 / 状态 / 类型 / 日期区间筛选、详情
- 详情弹窗:单据字段 + 状态变更历史时间线
- 对应 api 层(`api/leaves.ts`)与组件级测试

**本期不做**:

- 假期额度校验(后端不做,PRD §6 技术债)
- 销假、代理审批(后端不做)
- 审批通知(后端留 history 表供 P1 对接)
- 报销审批(P1)

## 2. 关键决策

| 决策点 | 结论 |
|---|---|
| 页面形态 | 单页 `/leaves` + AntD Tabs:我的申请(`leave:list`)/ 待我审批(`leave:approve`)/ 全部记录(`leave:list_all`),按权限显隐;默认激活第一个可见 Tab(全角色都有 `leave:list`,即默认"我的申请") |
| 提交/驳回入口 | 均用 Modal(沿用 P0#1/#2 弹窗模式),不另开路由页 |
| 审批操作 | 待我审批行内:通过 = Popconfirm 直接提交;驳回 = Modal 必填原因(后端 422 兜底) |
| 详情与留痕 | 各列表行"详情"按钮 → Modal:字段描述 + 状态历史 Timeline(时间升序,后端契约) |
| 部门筛选 | 全部记录 Tab 的部门候选 = `listDeptTree()` 整棵树 TreeSelect(admin 兼有 `department:list`) |
| 服务器数据管理 | 页面内 `useState` + `useEffect`,无新依赖(沿用 P0#1/#2) |
| 中文映射 | 类型/状态 → 文案 + Tag 颜色,集中 `utils/leave.ts`,面板与详情共用 |

## 3. 后端接口契约(已与 `backend/app/schemas/leave.py`、`backend/app/api/v1/leaves.py` 核对)

全部经统一 axios client(baseURL `/api/v1`,错误信封 → `ApiError(code, message)`)。

| 方法 | 路径 | 请求 | 响应 | 权限 |
|---|---|---|---|---|
| POST | `/leaves` | `{type, start_date, end_date, reason(1-500)}` | `LeaveResponse`,201 | leave:create |
| POST | `/leaves/{id}/cancel` | — | `LeaveResponse` | leave:create(仅本人+pending) |
| GET | `/leaves/mine?status&page&page_size` | — | `LeaveListResponse` | leave:list |
| GET | `/leaves/todo?page&page_size` | — | `LeaveListResponse` | leave:approve |
| POST | `/leaves/{id}/approve` | — | `LeaveResponse` | leave:approve(仅审批人) |
| POST | `/leaves/{id}/reject` | `{reason(1-500)}` | `LeaveResponse` | leave:approve(仅审批人) |
| GET | `/leaves?department_id&status&type&start_from&end_to&page&page_size` | — | `LeaveListResponse` | leave:list_all |
| GET | `/leaves/{id}` | — | `LeaveDetailResponse` | leave:list + 数据归属 |

```ts
// types/api.ts 追加
type LeaveType = "personal" | "sick" | "annual" | "compensatory";
type LeaveStatus = "pending" | "approved" | "rejected" | "canceled";
interface LeaveResponse {
  id: string; type: string; start_date: string; end_date: string;
  reason: string; status: string;
  applicant: UserBrief; approver: UserBrief; created_at: string;
}
interface LeaveHistoryItem {
  from_status: string | null; to_status: string;
  actor: UserBrief; comment: string | null; created_at: string;
}
interface LeaveDetailResponse extends LeaveResponse { history: LeaveHistoryItem[] }
interface LeaveListResponse { items: LeaveResponse[]; total: number; page: number; page_size: number }
```

错误码(沿用后端):时间倒挂/无直属上级/驳回无原因 → 422 `VALIDATION_ERROR`;区间重叠/已终态仍操作 → 409 `CONFLICT`;非本人撤回/非审批人审批/无权看详情 → 403 `FORBIDDEN`。前端不区分 code,统一展示 `e.message`。

## 4. 页面与组件

```
路由(App.tsx 追加,/leaves 挂在 RequireAuth/MainLayout 下)
└── /leaves  LeavesPage  前置检查 leave:list,无权限 <Navigate to="/" replace />

src/pages/leaves/
├── LeavesPage.tsx         Tabs 容器:三个 Tab 按 leave:list / leave:approve / leave:list_all 显隐;
│                          默认激活第一个可见 Tab
├── MyLeavesPanel.tsx      我的申请:status Select 筛选 + Table(类型/日期/原因/状态/审批人/创建时间/操作);
│                          顶部"新建申请"按钮;操作:撤回(仅 pending,Popconfirm)+ 详情
├── TodoLeavesPanel.tsx    待我审批:Table(申请人/类型/日期/原因/创建时间/操作);
│                          操作:通过(Popconfirm)/ 驳回(开 RejectModal)/ 详情
├── AllLeavesPanel.tsx     全部记录:筛选行(部门 TreeSelect + status + type + 日期区间 RangePicker)
│                          + Table(申请人/类型/日期/状态/审批人/操作:详情)
├── LeaveFormModal.tsx     新建申请:类型 Select(四枚举)+ 起止日期 RangePicker + 原因 TextArea(1-500)
├── RejectModal.tsx        驳回原因 TextArea(必填 1-500)
└── LeaveDetailModal.tsx   详情:Descriptions(类型/日期/原因/状态/申请人/审批人/创建时间)
                           + Timeline(状态历史,含操作人/时间/驳回原因 comment)

src/utils/leave.ts         LEAVE_TYPE_MAP / LEAVE_STATUS_MAP:{ label, color };
                           渲染辅助 <LeaveTypeTag> <LeaveStatusTag>(或函数返回 Tag)

menu.tsx:MENU_ITEMS 追加(位置:部门管理之后)
  { key: "/leaves", label: "请假审批", icon: <CalendarOutlined />, permission: "leave:list" }
```

### 交互细节

**LeavesPage**
- Tab 配置数组:`{ key, label, permission, panel }`,按 `hasPermission` 过滤;`activeKey` 受控,初始为第一个可见 Tab

**MyLeavesPanel**
- 状态:`items/total/page/statusFilter/loading/error`;进入与筛选/翻页变化时拉 `listMine`
- 新建成功:`message.success("已提交")` + 回第 1 页刷新
- 撤回成功:`message.success("已撤回")` + 刷新当前页;409(已终态)`message.error(e.message)`

**TodoLeavesPanel**
- 通过成功:`message.success("已通过")` + 刷新;驳回成功:`message.success("已驳回")` + 刷新
- 409(已被处理,如并发审批)`message.error(e.message)` + 刷新(后端条件 UPDATE 兜底)

**AllLeavesPanel**
- 筛选变更即回第 1 页重查;日期区间 = RangePicker → `start_from` / `end_to`(YYYY-MM-DD)
- 部门 TreeSelect 数据 `listDeptTree()`,可清空

**LeaveFormModal**
- 前端校验:类型必选;起止日期必选且 start ≤ end(RangePicker 天然有序);原因必填 1-500
- 失败(422 无上级 / 409 区间重叠):Modal 顶部 `Alert` 显示 `ApiError.message`,不关闭

**RejectModal**
- 原因必填(1-500);失败 Modal 内 `Alert`,不关闭

**LeaveDetailModal**
- 打开时 `getLeaveDetail(id)`;加载中 Spin;403(越权)Modal 内 `Alert`
- Timeline 项:`{to_status 中文}` + 操作人姓名 + 时间(YYYY-MM-DD HH:mm)+ comment(驳回原因,有则显示)

## 5. api 层

新建 `api/leaves.ts`,纯函数,直接 `client` 调用,不 try/catch:

```ts
createLeave(body: { type: LeaveType; start_date: string; end_date: string; reason: string }): Promise<LeaveResponse>
cancelLeave(id: string): Promise<LeaveResponse>
listMine(params: { status?: string; page: number; page_size: number }): Promise<LeaveListResponse>
listTodo(params: { page: number; page_size: number }): Promise<LeaveListResponse>
listAll(params: { department_id?: string; status?: string; type?: string; start_from?: string; end_to?: string; page: number; page_size: number }): Promise<LeaveListResponse>
getLeaveDetail(id: string): Promise<LeaveDetailResponse>
approveLeave(id: string): Promise<LeaveResponse>
rejectLeave(id: string, reason: string): Promise<LeaveResponse>
```

可选参数仅在有时放入 params(沿用 P0#1 `listUsers` 的展开写法)。

## 6. 错误处理

- 页面层统一 `catch`:ApiError → 展示 `e.message`;其余已被拦截器归为 UNKNOWN(沿用 P0#1)
- 列表操作(撤回/通过/驳回)409/403 → `message.error(e.message)`;表单类(新建/驳回原因)失败 → Modal 内 `Alert`
- 消息提示一律 `App.useApp()`(地基 spec §5,禁用静态 message)
- 字段级校验(原因 1-500、日期必选)前端 Form rules 完成

## 7. 测试策略

沿用测试基建(zhCN `ConfigProvider` + `<AntdApp>` 包装、jsdom polyfill、axios-mock-adapter、真实 store + `setState` 预置)。

| 测试文件 | 覆盖 |
|---|---|
| `api/leaves.test.ts` | 8 个接口 URL/方法/参数正确(含可选筛选参数展开),错误信封透传 |
| `utils/leave.test.ts` | 类型/状态映射齐全(四类型四状态),未知值兜底 |
| `pages/leaves/LeavesPage.test.tsx` | 无 leave:list 跳回;三权限组合的 Tab 显隐(employee 仅我的申请 / manager 两个 / admin 三个);默认激活第一个可见 Tab |
| `pages/leaves/MyLeavesPanel.test.tsx` | 列表渲染;status 筛选重查;pending 行有撤回、终态行无;撤回确认调接口;新建成功刷新 |
| `pages/leaves/TodoLeavesPanel.test.tsx` | 列表渲染;通过 Popconfirm 调接口;驳回弹窗必填校验与提交参数;409 提示 |
| `pages/leaves/AllLeavesPanel.test.tsx` | 筛选参数正确组装(部门/状态/类型/日期区间);筛选变更回第 1 页 |
| `pages/leaves/LeaveFormModal.test.tsx` | 校验(类型/日期/原因必填);提交参数(日期格式化 YYYY-MM-DD);422/409 失败 Alert 不关闭 |
| `pages/leaves/LeaveDetailModal.test.tsx` | 字段渲染;history Timeline 渲染(含驳回 comment);403 Alert |

## 8. 验收标准

**自动化门禁:**

- [ ] `npm test` 全绿(既有 92 + 本期新增)
- [ ] `tsc --noEmit` 零错误,`vite build` 成功

**浏览器实测(由执行 Agent 使用 chrome-devtools 驱动真实浏览器完成,非人工点检;前置:后端 :8000 + dev server :5173 代理;截图存档至 `.superpowers/sdd/acceptance/`):**

- [ ] 准备:admin 为测试员工设置直属上级(若未设);创建/已知密码的 employee 与 manager 账号
- [ ] employee 登录:菜单仅"请假审批"一个相关入口,页内仅"我的申请"Tab;新建申请成功,列表出现 pending 单
- [ ] employee 提交时间倒挂(前端 RangePicker 限制,用接口或绕过验证 422 由后端透出——以前端校验为主,不强制触发)
- [ ] employee 提交区间重叠申请 → 409 错误提示(Modal 内 Alert)
- [ ] employee 撤回 pending 单 → 状态变已撤回;终态行无撤回按钮
- [ ] manager 登录:"待我审批"Tab 可见该员工的单;驳回(填原因)→ 状态已驳回
- [ ] employee 再提交一单 → manager 通过 → 状态已通过
- [ ] 详情弹窗:状态历史完整(创建 → 撤回/驳回/通过),驳回单显示驳回原因
- [ ] admin:"全部记录"Tab,按状态筛选生效,按部门筛选生效;详情可看任意单
- [ ] 每场景截图存档至 `.superpowers/sdd/acceptance/`,作为验收证据
