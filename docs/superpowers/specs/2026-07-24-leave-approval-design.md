# 请假审批模块 — 设计文档

- 版本:v1.0
- 日期:2026-07-24
- 状态:已确认
- 对应 PRD:docs/prd.md §3.3.1、§3.3.3(P0 模块之三)
- 前置模块:组织架构管理(docs/superpowers/specs/2026-07-24-org-structure-design.md,依赖"直属上级"关系)

---

## 1. 范围

**本期做**:后端 API——请假申请(提交/撤回/查看)、审批(通过/驳回/待办列表)、三类查询(我的申请/待我审批/全部记录+筛选)、状态变更留痕。

**本期不做**:
- 假期额度限制(PRD §6 已知技术债,后续迭代)
- 通知代码(状态历史表供 P1 消息通知模块对接生成站内消息)
- 销假(审批通过后撤销)
- 报销审批(P1 模块)
- 代理审批、审批人离职/变动后的在途单处理(PRD §6 已知技术债)
- 前端页面(后端核心模块完成后统一开发)

## 2. 关键决策

| 决策点 | 结论 |
|---|---|
| 状态与审计存储 | 申请单当前状态 + 状态变更历史表(只追加),方案 A |
| 时间粒度 | 按天(start_date / end_date 均为 Date) |
| 请假类型 | personal 事假 / sick 病假 / annual 年假 / compensatory 调休,String(20) 存储便于扩展 |
| 审批人 | 提交时刻快照申请人直属上级(approver_id),后续换部门/换上级不影响在途单 |
| 无直属上级 | 提交直接 422 拒绝,提示联系管理员设置上级,不做兜底流转 |
| 审批权限 | 仅 approver_id 本人可审批,admin 不代批(admin 走全部记录查询) |
| 撤回 | 仅申请人本人、仅 pending 状态,状态变为 canceled(留痕) |
| 通知 | 本期不写通知代码;leave_status_history 即 P1 通知模块的数据源 |

## 3. 数据模型

### leave_requests(新建,申请单,存当前状态)

```
id           UUID 主键
applicant_id UUID FK → users.id, ON DELETE RESTRICT(留痕,不随用户删除)
type         String(20):personal / sick / annual / compensatory
start_date   Date
end_date     Date
reason       String(500)
status       String(20):pending / approved / rejected / canceled,默认 pending
approver_id  UUID FK → users.id, ON DELETE RESTRICT,提交时快照直属上级
created_at / updated_at(TimestampMixin 复用)
索引:applicant_id、approver_id、status
```

### leave_status_history(新建,状态历史,只 INSERT 不 UPDATE/DELETE)

```
id          UUID 主键
request_id  UUID FK → leave_requests.id, ON DELETE RESTRICT
from_status String(20) 可空(创建时 NULL → pending)
to_status   String(20)
actor_id    UUID FK → users.id, ON DELETE RESTRICT(操作人:申请人或审批人)
comment     String(500) 可空(驳回时必填原因,其余场景空)
created_at  DateTime(追加式表,无 updated_at)
索引:request_id
```

### 规则

- 审批记录永不删除(全部 FK RESTRICT),状态变更只追加历史行,符合 PRD"只能追加新状态、可追溯"
- ORM 关系:`LeaveRequest.applicant/approver/history`、`LeaveStatusHistory.request/actor`,均 `lazy="selectin"`,与现有风格一致
- `LeaveRequest` 挂 TimestampMixin;`LeaveStatusHistory` 只有 created_at,不挂 mixin

## 4. 状态机与业务规则

### 状态机

```
pending ──审批人通过──→ approved(终态)
   │────审批人驳回──→ rejected(终态,必须填驳回原因)
   │────申请人撤回──→ canceled(终态)
```

- 三个终态不可再变更;对已终态单据的任何操作 → 409 CONFLICT
- 每次状态迁移向 leave_status_history 追加一行(创建申请时记 NULL → pending)
- 状态迁移在 repository 层以条件 UPDATE(WHERE status = from_status)原子执行,并发重复审批/撤回时后到的请求得到 409

### 业务规则

| 规则 | 校验层 | 违反时 |
|---|---|---|
| start_date ≤ end_date | service | 422 VALIDATION_ERROR |
| 同一申请人时间区间不重叠(仅 pending/approved 单参与检查;rejected/canceled 不阻塞) | service | 409 CONFLICT |
| 撤回仅申请人本人、仅 pending | service | 403 / 409 |
| 审批仅 approver_id 本人 | service | 403 FORBIDDEN |
| 驳回必须填原因 | service | 422 VALIDATION_ERROR |
| 提交时申请人必须有直属上级 | service | 422 VALIDATION_ERROR("未设置直属上级,无法提交请假申请") |

重叠判定:区间为闭区间,含共同日期即重叠(如 8/1–8/3 与 8/3–8/5 重叠;8/1–8/3 与 8/4–8/5 不重叠)。即存在同申请人的单据 s,s.status ∈ {pending, approved} 且 NOT (s.end_date < new.start_date OR s.start_date > new.end_date)。

## 5. 权限模型

新增权限点(seed 更新,幂等):

| 权限点 | 说明 | admin | manager | employee |
|---|---|---|---|---|
| `leave:create` | 提交/撤回自己的请假申请 | ✓ | ✓ | ✓ |
| `leave:list` | 查看我的申请 | ✓ | ✓ | ✓ |
| `leave:approve` | 待我审批列表 + 审批操作 | ✓ | ✓ | |
| `leave:list_all` | 全部审批记录(含筛选) | ✓ | | |

seed 角色权限映射更新:admin 全部;manager 追加 leave:create、leave:list、leave:approve;employee 追加 leave:create、leave:list。

## 6. API 设计

全部挂 `/api/v1`,均需 JWT。路径用 `/leaves`,为 P1 报销(`/expenses`)留对称命名。

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/leaves` | 提交申请(type, start_date, end_date, reason),approver 自动快照直属上级 | leave:create |
| POST | `/leaves/{id}/cancel` | 撤回(仅本人、仅 pending) | leave:create |
| GET | `/leaves/mine` | 我的申请,分页 + status 筛选 | leave:list |
| GET | `/leaves/todo` | 待我审批(status=pending 且 approver=我),分页 | leave:approve |
| POST | `/leaves/{id}/approve` | 通过(仅审批人本人) | leave:approve |
| POST | `/leaves/{id}/reject` | 驳回(仅审批人本人,reason 必填) | leave:approve |
| GET | `/leaves` | 全部记录,筛选:department_id / status / type / 日期区间,分页 | leave:list_all |
| GET | `/leaves/{id}` | 详情,含完整状态历史 | leave:list + 数据归属 |

### 设计细则

- 详情接口权限点为 leave:list,再走数据归属校验:申请人本人、该单审批人、或持 leave:list_all 者可看,其余 403
- 响应包含 applicant、approver 概要(id + name,复用 UserBrief);详情额外含 history 数组(按时间升序)
- 列表分页沿用现有约定:page ≥ 1,page_size ≤ 100,响应含 items / total / page / page_size
- `GET /leaves` 的 department_id 筛选 = 按申请人所属部门过滤

## 7. 错误处理

沿用现有全局异常体系(`{"error":{code,message}}`)。

| 场景 | HTTP | code |
|---|---|---|
| start_date > end_date / 驳回无原因 / 无直属上级提交 | 422 | VALIDATION_ERROR |
| 时间区间重叠 / 单据已终态仍操作 | 409 | CONFLICT |
| 非本人撤回 / 非审批人审批 / 无权查看详情 | 403 | FORBIDDEN |
| 单据不存在 | 404 | NOT_FOUND |
| 未登录 / 无权限点 | 401 / 403 | 沿用现有 |

## 8. 测试策略

pytest + httpx AsyncClient,测试库 SQLite(沿用现有 conftest 基础设施,新增 make_leave 等工厂)。

- **Service 层单测**:时间倒挂、区间重叠(pending/approved 阻塞、rejected/canceled 不阻塞、含共同日期算重叠、首尾相接不算重叠)、状态机全部迁移与非法迁移、撤回权限、审批人校验、驳回原因必填、无上级 422、快照语义(提交后换上级,原审批人仍可审批)
- **API 集成测**:8 接口正反路径 + 鉴权矩阵(401 未登录 / 403 无权限点 / 403 越权)、历史记录随每次变更追加、详情接口三种身份可见性
- **迁移验证**:`alembic check` 无漂移、downgrade+replay 可逆
- **seed 测试**:新权限点幂等写入;admin/manager/employee 角色权限集合正确更新

## 9. 部署影响

一次 Alembic 迁移(2 张新表)+ seed 重跑。无新服务、无配置变更、无新依赖。

## 10. 验收标准(对齐 PRD §3.3.1、§3.3.3)

- [x] 员工可提交请假申请(类型/起止日期/原因),审批人自动为直属上级
- [x] 开始时间不能晚于结束时间(422)
- [x] 同一员工同一时间段不能重复提交,区间不重叠(409)
- [x] 审批人可通过/驳回(驳回必填原因),状态变更全程留痕不可删
- [x] 待审批申请可由本人撤回
- [x] 我的申请 / 待我审批 / 全部记录(admin,可按部门/状态/类型/时间筛选)三类查询可用
