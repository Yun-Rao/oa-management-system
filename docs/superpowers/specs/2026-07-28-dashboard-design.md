# P2 数据看板(后端)设计文档

- 日期:2026-07-28
- 状态:已评审(用户逐节确认)
- 依据:`docs/prd.md` §3.5(数据看板模块)、§7(P2 可选,管理层查看)
- 前置:P0/P1 已完成(用户/RBAC/组织/请假/通知/报销,详见各 spec)

## 1. 目标与范围

为管理层提供实时统计数据的后端查询 API:部门请假统计、部门报销统计、审批时效统计。

**做**:单一聚合端点 `GET /api/v1/dashboard`,实时 SQL 聚合,无快照表。
**不做**:前端页面(后续分支)、报销/请假的金额额度分析、两级审批时长拆分、导出、定时物化(本期数据量小,YAGNI)。

## 2. 架构方案

单聚合端点(方案 A):看板是唯一消费场景,一次请求返回三段统计;month 解析与 Manager 部门作用域在 service 内只写一遍。预聚合快照(方案 C)排除——数据量小,实时聚合足够。

分层镜像 expense 模块:`api/v1 → services → repositories → models`(无新表、无迁移)。

## 3. API 契约

### `GET /api/v1/dashboard`

- **Query**:`month=YYYY-MM`,缺省 = 当前月;格式校验 `^\d{4}-(0[1-9]|1[0-2])$`,非法 → 422
- **权限**:`require_permission("dashboard:view")`;service 内 `"dashboard:view_all" not in perms → department_id = user.department_id`(镜像 `department_service.list_members` 的 `user:list` 覆盖模式);本人无部门时统计为空集
- **响应** `DashboardSummaryResponse`:

```json
{
  "month": "2026-07",
  "leave_stats": [
    { "department_id": "uuid", "department_name": "技术部",
      "request_count": 5, "total_days": 11.5 }
  ],
  "expense_stats": [
    { "department_id": "uuid", "department_name": "技术部",
      "request_count": 8, "total_amount": 12345.60 }
  ],
  "approval_durations": [
    { "category": "leave",   "completed_count": 12, "avg_hours": 20.4 },
    { "category": "expense", "completed_count": 9,  "avg_hours": 45.1 }
  ]
}
```

**契约要点**:

| 取舍 | 决定 |
|---|---|
| 零数据部门 | 不出现在 leave_stats / expense_stats 数组中(YAGNI);Manager 视角数组最多一行(本部门) |
| total_amount | JSON number(Decimal 序列化,与既有 `ExpenseResponse.amount` 一致) |
| avg_hours | 保留 1 位小数;当月该类别无完成单时 `completed_count=0, avg_hours=null` |
| total_days | 允许 0.5 粒度(跨月切分/未来半天假),保留 1 位小数 |
| approval_durations | 固定两行(leave/expense),Admin 全局口径,Manager 本部门口径 |

## 4. 统计口径

### 4.1 leave_stats(部门请假统计)

- 只统计 `status = "approved"`
- 归属:假期区间 `[start_date, end_date]` 与当月**有交集**即计入申请人所在部门
- `request_count`:与当月有交集的申请笔数;一笔跨月假在两个月份各计 1 次("人次"语义,刻意如此)
- `total_days`:每笔按 `min(end_date, 月末) - max(start_date, 月初) + 1` 切分后求和(当前按整天计)

### 4.2 expense_stats(部门报销统计)

- 只统计 `status = "approved"`
- 归属:`created_at` 落在当月(报销无区间概念,创建月即归属月;上月创建本月审批通过 → 计上月)
- `request_count` 笔数;`total_amount` = `sum(amount)`(Numeric(12,2))

### 4.3 approval_durations(审批时效)

- 总体口径:当月内**终审完成**的单(`approved` 或 `rejected`;`cancelled` 不计——审批未真正处理)
- "当月完成"判定:该单 history 中终态行的 `created_at` 落在当月
- 时长 = 终态行 `created_at` − 申请 `created_at`(小时);`avg_hours` = 类别内平均值
- 报销两级:时长覆盖 L1+L2 全程(创建→终态),不拆分级数(后续迭代)
- Manager 视角:三段统计全部过滤为"申请人属于本部门"的单

## 5. 分层与文件

| 层 | 文件 | 职责 |
|---|---|---|
| API | `backend/app/api/v1/dashboard.py`(新建) | 路由;month 解析/校验;`require_permission("dashboard:view")`;`main.py` 注册 |
| Service | `backend/app/services/dashboard_service.py`(新建) | `DashboardService(db).get_summary(month: date, user: User)`;计算月首/月末;判定部门作用域;组装响应 |
| Repository | `backend/app/repositories/dashboard_repository.py`(新建) | `leave_stats(month_start, month_end, department_id)` / `expense_stats(...)` / `approval_durations(...)`,纯 SQL 聚合返回行元组 |
| Schema | `backend/app/schemas/dashboard.py`(新建) | `DashboardSummaryResponse` / `LeaveStatItem` / `ExpenseStatItem` / `ApprovalDurationItem` |

时效实现提示(spec 只锁口径,不锁实现):终态行取每单 history 中 `to_status ∈ 终态` 的 `max(created_at)`,子查询 join 回本单求平均;请假终态 `{approved, rejected}`,报销终态 `{approved, rejected}`。

## 6. 权限与 seed

只追加,不动既有映射:

- 新权限点 2 个:`dashboard:view`「查看数据看板」、`dashboard:view_all`「查看全公司看板」
- seed:admin 隐式全量(既有逻辑自动覆盖);manager 追加 `dashboard:view`(**不含** view_all);employee 不变
- `tests/conftest.py` `ALL_PERMISSIONS` 追加同样 2 条;`test_seed.py` 期望集合同步更新(admin 含两点、manager 含 view 不含 view_all、employee 不含)

## 7. 错误语义

| 场景 | 状态码 |
|---|---|
| 未登录 | 401 |
| 无 `dashboard:view` | 403 |
| month 格式非法(如 `2026-13`、`abc`) | 422 |

## 8. 测试策略

内存 SQLite + conftest 工厂 + httpx AsyncClient,镜像既有风格。

**Repository 层**(`test_dashboard_repository.py`,口径锁死在这层):
- leave:当月内/当月外/跨月切分(7/30–8/2 → 7 月 2 天、8 月 2 天)、rejected/pending 不计、多天求和、按部门分组、department_id 过滤
- expense:approved 计入、pending/rejected 不计、创建月归属(上月创建本月审批 → 计上月)、金额求和
- durations:当月完成的 approved/rejected 计入、cancelled 不计、上月完成不计、leave/expense 分类、平均小时精确断言(构造固定 created_at 与 history 时间)、无完成单 count=0

**Service 层**(`test_dashboard_service.py`):
- Admin(持 view_all)多部门;Manager(仅 view)只见本部门;Manager 无 department_id → 空集
- month 缺省 = 当前月(monkeypatch 当前日期)
- durations 同样受本部门过滤

**API 层**(`test_dashboard_api.py`):
- 200 全字段契约(department_name、avg_hours 小数、total_amount number)
- month 非法 → 422;无权限 → 403;未登录 → 401
- 无完成单时 `avg_hours=null`

**seed 测试**:期望集合更新(admin 全量含两点、manager 含 view 不含 view_all、employee 不含)。

## 9. 部署影响

无:无新表、无迁移、无新依赖、无新环境变量。`dashboard:view`/`dashboard:view_all` 由 seed 幂等补齐(既有环境重跑 `python -m scripts.seed` 即可)。

## 10. 验收标准

- [ ] `GET /api/v1/dashboard` 按 §3 契约返回三段统计,month 缺省本月、非法 422
- [ ] 请假统计口径符合 §4.1(approved、跨月切分、人次跨月各计)
- [ ] 报销统计口径符合 §4.2(approved、创建月归属)
- [ ] 审批时效口径符合 §4.3(终态完成月、含驳回不含撤回、不拆级别)
- [ ] Admin 全量、Manager 仅本部门、无权限 403、未登录 401
- [ ] seed 重跑幂等补齐两个新权限点;全量 pytest 绿(既有 247 + 新增,无回归)
