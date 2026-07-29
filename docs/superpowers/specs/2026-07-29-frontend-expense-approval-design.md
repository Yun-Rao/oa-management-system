# 报销审批模块(前端)— 设计文档

- 版本:v1.0
- 日期:2026-07-29
- 状态:已确认
- 对应 PRD:docs/prd.md §3.3.2(报销审批)+ §3.3.3(审批记录查询)
- 前置模块:报销审批后端(docs/superpowers/specs/2026-07-28-expense-approval-design.md,已上线);消息通知前端(docs/superpowers/specs/2026-07-29-frontend-notification-design.md,已上线,本期接通其 §6 预留的 expense 跳转分支)

---

## 1. 范围

**本期做**:
- (后端附加) `ExpenseResponse` 的 `applicant_id`/`approver_id` 键替换为 `applicant: UserBrief`、`approver: UserBrief | None`,与 `LeaveResponse` 对齐——旧键从 JSON 移除,非纯新增;全仓检索确认无其他消费方,同步更新后端 spec §6
- `/expenses` 路由 + 「报销审批」菜单项(permission `expense:list`)
- 三 Tab 页面:我的申请 / 待我审批 / 全部记录(按权限过滤)
- 新建报销 Modal:类型/金额/说明 + 1~5 个附件(jpg/jpeg/png/pdf,单个 ≤5MB),一体 multipart 提交
- 报销详情 Modal:描述列表、附件点击鉴权下载、history Timeline、二级审批状态展示(当前第几级/审批人)
- 审批操作:通过 / 驳回(驳回原因弹窗)/ 撤回
- 通知联动:消息中心 `ref_type="expense"` 通知点击 → 跳转 `/expenses` 自动打开详情弹窗

**本期不做**:
- 报销单编辑/删除(后端不支持,审计要求)
- 金额统计/报表(P2 数据看板范畴)
- 附件图片内联预览(统一点击下载)
- 阈值配置管理界面(后端环境变量即可)
- 抽象请假/报销共享审批组件(等第三个审批类模块出现时再评估)

## 2. 关键决策

| 决策点 | 结论 |
|---|---|
| 总体结构 | 方案 A:纯镜像请假前端模块,`pages/expenses/` 下 1:1 同构新建,不改请假模块任何文件;差异点(金额/附件/二级状态)集中在模块自己的 Panel/Modal 内部 |
| 表单形态 | Modal 弹窗(镜像 LeaveFormModal),antd Upload 前端预校验,FormData 一体提交 |
| 附件展示 | 详情 Modal 内文件名列表,点击走鉴权接口 blob 下载;不做内联预览 |
| 金额处理 | 后端 Decimal 序列化为字符串,前端展示直接字符串 + `¥` 前缀;表单 `amount` 以字符串塞 FormData,全程不做浮点转换 |
| 二级审批展示 | 状态 Tag 五级中文映射 + 详情 Modal「当前审批」行(L1 显示主管姓名,L2 显示 HR/Admin 权限池,终态显示 —)+ history Timeline 呈现每级 actor/时间/驳回原因 |
| 通知联动 | NotificationsPage 的 `ref_type` 分发加 `"expense"` 分支,镜像 `openLeaveId` 模式生产 `openExpenseId` state;未知类型仍降级为仅标记已读 |
| 后端姓名字段 | `ExpenseResponse` 的 `applicant_id`/`approver_id` 键替换为 `applicant: UserBrief`、`approver: UserBrief | None`(对齐 `LeaveResponse`),否则表格「申请人」列与「当前审批·主管姓名」无数据源;为键替换而非纯新增,全仓无其他消费旧键的调用方 |
| 状态管理 | 无新 store;列表/筛选/分页全部页面本地态(镜像 leaves/notifications 模式) |
| 权限门控 | 菜单 `expense:list`;页面无 `expense:list` → `<Navigate to="/" />`;Tab 按权限过滤;操作按钮按权限与状态渲染 |

## 3. 后端接口(既有,直接消费)

全部挂 `/api/v1`,分页约定 `items/total/page/page_size`,page ≥ 1,page_size ≤ 100。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/expenses` | expense:create | multipart/form-data:type/amount/reason 字段 + files(1~5);201 返回 ExpenseResponse |
| GET | `/expenses/mine` | expense:list | 我的申请,status/type 过滤 + 分页,created_at 倒序 |
| GET | `/expenses/todo` | expense:approve 或 expense:approve_l2 | 待办:L1 权限→自己的 pending_l1;L2 权限→全部 pending_l2;两者都有→合并倒序 |
| GET | `/expenses` | expense:list_all | 全部记录,部门/状态/类型/时间过滤 + 分页 |
| GET | `/expenses/{id}` | expense:list + 可见性 | 详情含 history[](含 actor 姓名)与 attachments[](id/filename/content_type/size_bytes) |
| GET | `/expenses/{id}/attachments/{att_id}` | 同详情可见性 | 鉴权下载(FileResponse) |
| POST | `/expenses/{id}/cancel` | expense:create + 本人 | 撤回,仅 pending_l1/pending_l2 |
| POST | `/expenses/{id}/approve` | 分级校验 | 当前级通过 |
| POST | `/expenses/{id}/reject` | 分级校验 | 驳回,reason 必填 |

**响应形状**:

```ts
ExpenseResponse { id, type, amount, reason, status, applicant: { id, name }, approver: { id, name } | null, created_at, updated_at }
ExpenseDetailResponse = ExpenseResponse + {
  history: [{ id, from_status, to_status, actor: { id, name }, comment, created_at }],
  attachments: [{ id, filename, content_type, size_bytes, created_at }],
}
```

> 注:`applicant`/`approver` 姓名字段为本期后端附加改动(见 §2),替换原 `applicant_id`/`approver_id`(与 `LeaveResponse` 同形,后者也只有姓名对象);`approver` 在 pending_l2(权限池)时为 `null`。

- `type` ∈ travel / office / entertainment / transport / other;`status` ∈ pending_l1 / pending_l2 / approved / rejected / cancelled
- `amount` 为去尾零十进制字符串(如 `"2000"`、`"1999.5"`)
- 错误沿用全局 `{"error":{code,message}}`:404 NOT_FOUND / 403 FORBIDDEN / 409 CONFLICT / 422 VALIDATION_ERROR

## 4. 架构与组件

镜像既有分层(api → pages/components),不改请假模块任何文件。

| 单元 | 文件 | 职责 |
|---|---|---|
| 后端字段 | 改 `backend/app/schemas/expense.py` | `ExpenseResponse` 的 `applicant_id/approver_id` 替换为 `applicant: UserBrief`、`approver: UserBrief | None`(与 `LeaveResponse` 同形);同步更新后端 spec `2026-07-28-expense-approval-design.md` §6 的响应形状描述与后端相关测试 |
| 类型 | `frontend/src/types/api.ts`(追加) | `ExpenseType`、`ExpenseStatus`、`ExpenseItem`、`ExpenseAttachment`、`ExpenseHistoryItem`、`ExpenseDetail`、`ExpenseListResponse` |
| api 层 | `frontend/src/api/expenses.ts` | `createExpense(form: FormData)` / `listMine({status?, type?, page, page_size})` / `listTodo({page, page_size})` / `listAll({department_id?, status?, type?, start_from?, end_to?, page, page_size})` / `getExpenseDetail(id)` / `downloadAttachment(expenseId, attId): Promise<Blob>` / `cancelExpense(id)` / `approveExpense(id)` / `rejectExpense(id, reason)`;错误沿用 `ApiError` |
| 菜单 | 改 `frontend/src/components/menu.tsx` | 追加 `{ key: "/expenses", label: "报销审批", icon: <PayCircleOutlined />, permission: "expense:list" }` |
| 路由 | 改 `frontend/src/App.tsx` | `/expenses` → `ExpensesPage`(RequireAuth 内,页面内做权限门控) |
| 页面壳 | `frontend/src/pages/expenses/ExpensesPage.tsx` | Card + Tabs(按权限过滤:我的申请 `expense:list` / 待我审批 `expense:approve` 或 `expense:approve_l2` / 全部记录 `expense:list_all`);无 `expense:list` → `<Navigate to="/" />`;读 `location.state?.openExpenseId` 渲染 `ExpenseDetailModal`,关闭 `navigate(".", { replace: true, state: null })` 清除 |
| 我的申请 | `frontend/src/pages/expenses/MyExpensesPanel.tsx` | 状态/类型筛选 + 分页表格(类型中文/金额 ¥/状态 Tag/创建时间);「新建报销」按钮开 ExpenseFormModal;pending_l1/pending_l2 行有「撤回」;行点击开详情 |
| 待我审批 | `frontend/src/pages/expenses/TodoExpensesPanel.tsx` | 待办表格(后端已合并 L1/L2 视角);行内「通过」(Popconfirm)/「驳回」(开 RejectModal);行点击开详情;操作成功重拉 |
| 全部记录 | `frontend/src/pages/expenses/AllExpensesPanel.tsx` | 部门/状态/类型/时间范围筛选 + 分页表格;行点击开详情 |
| 详情弹窗 | `frontend/src/pages/expenses/ExpenseDetailModal.tsx` | 描述列表(类型/金额/说明/状态/申请人/创建时间)+「当前审批」行 + 附件列表(文件名 + 大小,点击下载)+ history Timeline(每级 actor 姓名/时间/驳回原因) |
| 新建表单 | `frontend/src/pages/expenses/ExpenseFormModal.tsx` | type Select(差旅/办公/招待/交通/其他)+ amount InputNumber(min>0,精度 2)+ reason TextArea(≤500)+ Upload(1~5 个,jpg/jpeg/png/pdf,单个 ≤5MB,`beforeUpload` 预校验);成功 message + 关闭 + 通知父级重拉 |
| 驳回弹窗 | `frontend/src/pages/expenses/RejectModal.tsx` | 与请假版同构克隆,改调 `rejectExpense` |
| 通知联动 | 改 `frontend/src/pages/notifications/NotificationsPage.tsx` | 点击条目处 `ref_type` 分发:`"leave"` → `/leaves`(既有)、`"expense"` → `/expenses` 带 `{ openExpenseId: ref_id }`、未知 → 仅标记已读 |

**常量**:类型/状态中文映射与颜色放 `frontend/src/utils/expense.tsx`(EXPENSE_TYPE_MAP:差旅/办公/招待/交通/其他;EXPENSE_STATUS_MAP:待主管审批/待二级审批/已通过/已驳回/已撤回;另导出 `expenseTypeTag` / `expenseStatusTag` 渲染函数)。

## 5. 数据流

- 各 Panel 本地态管理 `items/total/page/filters/loading/error`;筛选或分页变化触发重拉(镜像 AllLeavesPanel 模式)
- 操作闭环:新建/撤回/通过/驳回成功 → message.success + 重拉当前列表;409(并发被抢审)→ message.error(后端 message)+ 同样重拉,让用户看到最新状态
- 详情弹窗:`expenseId: string | null` 受控,非 null 时挂载并按 id 拉详情;弹窗为纯展示(信息 + 附件 + Timeline),审批/驳回操作在「待我审批」面板行内触发,成功后重拉列表
- 附件下载:`downloadAttachment` 返回 Blob → `URL.createObjectURL` → 临时 `<a download={filename}>` 点击 → `revokeObjectURL`;鉴权由 axios 拦截器自带 Authorization,无需新机制
- 金额:展示 `¥{amount}`(字符串原样);表单 InputNumber 值 `toFixed(2)` 后转字符串塞 FormData

## 6. 扩展预留(不实现)

- 第三个审批类模块出现时,评估抽取共享审批表格/详情/驳回组件
- 附件图片内联预览(需 blob 鉴权加载层)
- 通知 `ref_type` 分发表如需更多类型,可从 if 分支重构为 map

## 7. 错误处理

沿用既有模式:api 层抛 `ApiError`,页面用 `App.useApp()` 的 message 提示。

| 场景 | 表现 |
|---|---|
| 列表加载失败 | Panel 内 Alert + 切换筛选/分页即重试 |
| 新建提交 422 | 表单前端预校验拦截大部分;后端 422 在 Modal 内 Alert 显示,不关弹窗、不清已填内容 |
| 通过/驳回/撤回 409 | message.error(后端 message)+ 重拉列表 |
| 详情 403/404 | Modal 内 Alert 显示后端 message |
| 附件下载失败 | message.error |
| 上传预校验失败 | `beforeUpload`:数量 >5、单文件 >5MB、扩展名不符 → message.error 并阻止加入 |

## 8. 测试策略

vitest + Testing Library + axios-mock-adapter,镜像既有结构,每个单元带 .test 文件;浏览器实测用 chrome-devtools MCP。

- **api 层**:9 个函数的 URL/方法/参数透传/返回拆包;`createExpense` 的 FormData 字段与文件;`downloadAttachment` 的 blob responseType
- **MyExpensesPanel**:渲染、筛选重拉、撤回按钮按状态显隐(pending 有/终态无)、撤回成功重拉
- **TodoExpensesPanel**:通过/驳回闭环、409 时 message + 重拉
- **AllExpensesPanel**:四个筛选条件参数透传
- **ExpenseDetailModal**:五级状态 Tag、「当前审批」行(L1 主管姓名 / L2 权限池 / 终态 —)、附件点击触发下载、Timeline 渲染 actor 与驳回原因
- **ExpenseFormModal**:必填校验、金额 >0、附件数量/大小/类型预校验拦截、multipart 提交内容
- **ExpensesPage**:携带 `openExpenseId` state 进入自动开详情弹窗、关闭清 state(镜像 LeavesPage 联动测试)
- **NotificationsPage**:`ref_type="expense"` 点击 → `markRead` + 跳转 `/expenses` 且 state 为 `{"openExpenseId": ref_id}`;未知 ref_type 不跳转(既有行为回归)

**浏览器验收**(截图存 `.superpowers/sdd/acceptance/`,`exp-` 前缀):

1. 员工新建 ≤2000 报销(带附件)→ 主管待办可见 → 主管通过 → 员工状态「已通过」且收到通知
2. 员工新建 >2000 报销 → 主管通过 → 状态「待二级审批」、「当前审批」显示第 2 级权限池 → Admin 待办可见 → 二级通过 → Timeline 两级留痕
3. 任一级驳回 → 状态「已驳回」,驳回原因在详情可见
4. 详情附件点击下载,文件可打开
5. 消息中心点击报销通知 → 跳转 `/expenses` 自动开详情弹窗,角标 -1
6. 无 `expense:list` 权限用户直接访问 `/expenses` → 重定向首页

## 9. 部署影响

后端:仅响应 schema 新增字段(applicant/approver 姓名对象,来自既有 ORM 关系),无数据库迁移、无新依赖、无配置项;需同步后端 spec §6。前端:纯新增,无新依赖(antd/zustand/axios/dayjs 均已存在),无环境变量。

## 10. 验收标准(对齐 PRD §3.3.2/§3.3.3)

- [x] 员工可提交含 1~5 个附件凭证的报销申请,金额/类型/说明齐全
- [x] 金额 ≤ 阈值主管审批即通过;> 阈值主管通过后流转二级,页面清晰展示当前第几级、审批人是谁
- [x] 任一级驳回流程终止,状态「已驳回」且驳回原因可见;撤回在审批中可用
- [x] 我的申请/待我审批/全部记录三视图按权限可见,全部记录可按部门/状态/类型/时间筛选
- [x] 附件凭证可在详情中鉴权下载
- [x] 消息中心点击报销通知可跳转 `/expenses` 并自动打开对应详情
