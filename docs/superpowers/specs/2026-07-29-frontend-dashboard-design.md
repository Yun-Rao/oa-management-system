# P2 数据看板(前端)设计文档

- 日期:2026-07-29
- 状态:已评审(用户逐节确认)
- 依据:`docs/prd.md` §3.5(数据看板)、§7(P2);后端契约 `docs/superpowers/specs/2026-07-28-dashboard-design.md`
- 前置:P0/P1 前端已全部完成(用户/组织/请假/通知/报销);后端 dashboard API 已上线(spec §10 全勾选)

## 1. 目标与范围

为管理层(`dashboard:view` 持有者:Admin、Manager)提供数据看板前端页面:部门请假统计、部门报销统计、审批时效统计,支持按月切换。

**做**:`/dashboard` 独立页面 + 菜单项「数据看板」;MonthPicker 切月(默认当前月);三段统计的汇总卡片 + 明细表渲染。

**不做**:图表库(纯 antd,零新依赖);导出;两级审批时长拆分;趋势/环比;首页概要卡片;任何后端改动(契约已冻结,见后端 spec §3)。

## 2. 架构方案

页面壳 + 三 Section(方案 B):`DashboardPage` 持有 month 状态、拉数、错误展示,`LeaveStatsSection` / `ExpenseStatsSection` / `DurationSection` 纯展示。与 expenses 模块「页面壳 + Panel」同构,每个 Section 独立可测。

排除:单文件整页(文件过大、违反单一职责);Section 再拆子组件(三段统计都简单,YAGNI);引入 @ant-design/plots 等图表库(打破零新增依赖约束,包体积 +~1MB,表格已满足管理层查数需求)。

镜像既有模块惯例:页面本地态、无新 store;`api/dashboard.ts` 单函数;类型追加到 `types/api.ts` 末尾;菜单/路由接线方式与 expenses 完全一致。

## 3. 接口契约

### `GET /api/v1/dashboard?month=YYYY-MM`

- **Query**:`month` 可省(后端默认当前月);前端切换月份时必传,格式 `YYYY-MM`
- **权限**:`dashboard:view`;Admin(`dashboard:view_all`)返回全部门多行;Manager 仅本部门(≤1 行);employee 无权限 → 403(前端不进页,见 §5)
- **响应** `DashboardSummary`:

```json
{
  "month": "2026-07",
  "leave_stats": [
    { "department_id": "uuid", "department_name": "技术部",
      "request_count": 5, "total_days": 11.5 }
  ],
  "expense_stats": [
    { "department_id": "uuid", "department_name": "技术部",
      "request_count": 8, "total_amount": "12345.60" }
  ],
  "approval_durations": [
    { "category": "leave",   "completed_count": 12, "avg_hours": 20.4 },
    { "category": "expense", "completed_count": 9,  "avg_hours": null }
  ]
}
```

**前端类型要点**:

| 字段 | TS 类型 | 展示 |
|---|---|---|
| `total_amount` | `string`(Decimal 序列化,与 ExpenseItem.amount 一致) | `¥{total_amount}` 直拼,不做浮点转换 |
| `total_days` | `number` | 原值(后端已保留 1 位小数) |
| `avg_hours` | `number \| null` | `{avg_hours} 小时`;`null` → `—` |
| `request_count` / `completed_count` | `number` | 原值 |
| 响应 `month` | `string` | 仅展示参考,不回写 month 状态(单向流) |

> **唯一浮点例外**:报销汇总卡片的「总金额合计」= 各行 `Number(total_amount)` 求和后 `toFixed(2)`(展示层合计,不回传、不参与其他计算);明细行仍逐字渲染后端字符串。

## 4. 单元表

| 单元 | 文件 | 职责 |
|---|---|---|
| api | `frontend/src/api/dashboard.ts`(新建) | `getDashboard(month?: string): Promise<DashboardSummary>`;month 省略时不带参数 |
| 类型 | `frontend/src/types/api.ts`(末尾追加) | `LeaveStatItem` / `ExpenseStatItem` / `ApprovalDurationItem` / `DashboardSummary` |
| 页面壳 | `frontend/src/pages/dashboard/DashboardPage.tsx`(新建) | `month: Dayjs` 本地态;`getDashboard` 拉取(cancelled 清理);MonthPicker;loading;错误 Alert;无 `dashboard:view` → `<Navigate to="/" replace />`;分发三 Section |
| 请假 Section | `frontend/src/pages/dashboard/LeaveStatsSection.tsx`(新建) | Props `{ stats: LeaveStatItem[] }`;汇总 Statistic(总人次/总天数)+ 部门明细 Table |
| 报销 Section | `frontend/src/pages/dashboard/ExpenseStatsSection.tsx`(新建) | Props `{ stats: ExpenseStatItem[] }`;汇总 Statistic(总笔数/总金额 ¥)+ 部门明细 Table |
| 时效 Section | `frontend/src/pages/dashboard/DurationSection.tsx`(新建) | Props `{ durations: ApprovalDurationItem[] }`;请假/报销两张 Statistic 卡片:完成单数 + 平均时效 |
| 菜单 | `frontend/src/components/menu.tsx`(改) | expenses 行后追加 `{ key: "/dashboard", label: "数据看板", icon: <BarChartOutlined />, permission: "dashboard:view" }` |
| 路由 | `frontend/src/App.tsx`(改) | import + expenses 路由后追加 `{ path: "dashboard", element: <DashboardPage /> }` |

## 5. 数据流与权限

- MonthPicker onChange → `setMonth` → useEffect(依赖 month)重拉,`cancelled` 标志防竞态(镜像 AllExpensesPanel);month 以 `Dayjs` 持有,请求时 `format("YYYY-MM")`
- Section 全部纯展示、无内部状态、无副作用
- 权限:菜单项 `permission: "dashboard:view"`(employee 不可见);直接访问 `/dashboard` 且无权限 → 重定向 `/`(镜像 ExpensesPage)
- Manager 视角不做特判:后端只返回本部门一行,同一渲染路径,汇总值自然等于明细值

## 6. 扩展预留

- 图表化:Section 已是独立组件,后续引入图表库时逐块替换内部渲染即可,页面壳与 api 层不动
- 更多统计维度(个人排行、趋势):后端契约扩展后加 Section,不动既有三个
- 本期不实现上述任何一项

## 7. 错误处理

| 场景 | 行为 |
|---|---|
| 拉取失败 | 页面顶部 `Alert`:`ApiError.message` 或「网络异常,请稍后重试」;保留上一次成功数据不清空 |
| 空数据月份 | 明细 Table antd 默认空态;汇总 Statistic 显示 0;`avg_hours=null` → `—` |
| 未来月份 | 不禁选(后端不限制,返回空集,少一个特判) |
| 无权限直接访问 | `<Navigate to="/" replace />` |

## 8. 测试策略

vitest + Testing Library + axios-mock-adapter / vi.mock,镜像既有模块风格。

- `api/dashboard.test.ts`:month 透传;month 省略时 params 为空
- `DashboardPage.test.tsx`(mock 三 Section + api):无 `dashboard:view` 重定向首页;默认以当前月拉取;切月份带新 `YYYY-MM` 参数重拉;失败显示错误 Alert
- `LeaveStatsSection.test.tsx`:多行汇总求和正确;空数组渲染空态且汇总为 0
- `ExpenseStatsSection.test.tsx`:金额 `¥` 直拼(字符串求和展示按后端值,不做浮点运算——汇总卡片逐行渲染后端值,合计行允许 `Number` 求和后 `toFixed(2)`,仅限展示层);空数组空态
- `DurationSection.test.tsx`:`avg_hours` 数值显示 `{x} 小时`;`null` 显示 `—`;两类别齐全
- 全量验收(Task 收尾):`npm test` 全绿 + `npm run typecheck` 0 errors + 后端 pytest 无回归;浏览器实测(chrome-devtools MCP):admin 全部门多行视图、manager 仅本部门一行、切月份重拉、employee 无菜单项且直接访问重定向首页;截图存 `.superpowers/sdd/acceptance/`(`dash-` 前缀)

## 9. 部署影响

无:纯前端新增,无新依赖、无环境变量;后端零改动;`dashboard:view` 权限已由既有 seed 覆盖(admin 全量、manager 含 view)。

## 10. 验收标准

- [x] `/dashboard` 页面按 §3 契约渲染三段统计,MonthPicker 切月重拉
- [x] Admin 见全部门多行;Manager 仅本部门;employee 无菜单项且直接访问重定向首页
- [x] 明细行 `total_amount` 字符串直拼 `¥` 展示;仅汇总卡片合计允许 `Number` 求和 + `toFixed(2)`(§3 唯一例外);`avg_hours=null` 显示 `—`
- [x] 空数据月份各 Section 正确空态;拉取失败 Alert 且保留旧数据
- [x] 前端全量测试 + typecheck 绿,后端无回归
- [x] 浏览器实测四视角(admin/manager/切月/employee)截图存 `.superpowers/sdd/acceptance/`(`dash-` 前缀)
