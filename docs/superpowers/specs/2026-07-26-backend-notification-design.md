# 消息通知模块(后端)— 设计文档

- 版本:v1.0
- 日期:2026-07-26
- 状态:已确认
- 对应 PRD:docs/prd.md §3.4(P1 模块之一)
- 前置模块:请假审批(docs/superpowers/specs/2026-07-24-leave-approval-design.md,通知触发点挂在其 create/approve/reject 上)

---

## 1. 范围

**本期做**:后端 API——站内消息(通知)的生成与查询:请假审批三个触发点(新待审批→审批人;通过/驳回→申请人)同步生成通知;通知列表(已读/未读筛选+分页)、未读数、标记已读(单条/全部)。

**本期不做**:
- 前端消息中心 UI / 角标轮询(后续前端任务)
- 报销审批的通知触发点(P1 报销模块开发时复用本模块 NotificationService,ref_type="expense")
- 撤回通知(PRD 未要求;审批人待办列表实时查询,撤回单自然消失)
- 邮件/短信通知(PRD 明确本期不做)
- WebSocket/SSE 实时推送(轮询即可满足;实时性 = 前端轮询间隔)
- 通知删除(历史通知长期保留,只增读态)

## 2. 关键决策

| 决策点 | 结论 |
|---|---|
| 通知创建方式 | 同步、与审批动作同一 db session/事务:leave_service 在 create/approve/reject 成功后调用 NotificationService,通知行随动作一起提交,原子同生同死 |
| 与请假 spec 的关系 | 请假 spec 预留"leave_status_history 即 P1 通知模块的数据源";本设计在此基础上明确为:通知在动作发生点由 service 直接生成(数据即在手),不做从 history 回读派生的异步流程 |
| 实时性 | 不做服务端推送;前端轮询 `GET /notifications/unread-count`(间隔由前端定,建议 30s) |
| 触发场景 | 严格 PRD 两个:新待审批→审批人;通过/驳回→申请人。撤回不通知 |
| 通知内容 | 写入时预渲染中文 title + content(无 i18n);类型中文映射后端内置常量(事假/病假/年假/调休,与前端 LEAVE_TYPE_MAP 一致) |
| 跳转 | ref_type + ref_id(本期恒为 "leave" + 请假单 id),前端凭此打开详情;后端不存 URL |
| 权限 | 无新权限点:登录即可读写自己的通知(get_current_user);seed 不变 |
| 越权语义 | 标记非本人通知 → 403 FORBIDDEN(对齐请假详情越权惯例);不存在 → 404 NOT_FOUND |
| 读态 | read_at 可空时间戳,null=未读;标记已读幂等(已读仍 200,read_at 保持首次时间) |

## 3. 数据模型

### notifications(新建)

```
id          UUID 主键
user_id     UUID FK → users.id, ON DELETE RESTRICT(接收人;留痕,不随用户删除)
type        String(30):leave_submitted / leave_approved / leave_rejected
title       String(100):新的待审批任务 / 请假申请已通过 / 请假申请已驳回
content     String(500):预渲染全文(见 §4 模板)
ref_type    String(20):本期恒 "leave"
ref_id      UUID:请假单 id(无外键,通用引用,为 P1 报销留扩展)
read_at     DateTime 可空(NULL = 未读)
created_at  DateTime,server_default=func.now()
索引:(user_id, read_at) 复合索引
```

### 规则

- 通知只 INSERT + read_at 单字段更新,无删除接口,符合"消息中心可查看历史"
- 不挂 TimestampMixin(追加式表,语义同 leave_status_history,另加 read_at 列)
- ORM 关系:`Notification.user`,`lazy="selectin"`,与现有风格一致(响应只需接收人,序列化不展开 user)

## 4. 触发点与内容模板

| 时机(leave_service 内) | 接收人 | type | title | content 模板 |
|---|---|---|---|---|
| create_leave 成功 | 审批人(approver_id) | leave_submitted | 新的待审批任务 | `{applicant_name} 提交了 {start} ~ {end} 的{type_label}申请,待您审批` |
| approve_leave 成功 | 申请人 | leave_approved | 请假申请已通过 | `您 {start} ~ {end} 的{type_label}申请已通过` |
| reject_leave 成功 | 申请人 | leave_rejected | 请假申请已驳回 | `您 {start} ~ {end} 的{type_label}申请已被驳回:{reason}` |
| cancel_leave 成功 | —(不通知) | | | |

- 日期格式 `YYYY-MM-DD`;type_label ∈ 事假/病假/年假/调休
- 三个调用点都在对应动作成功(状态迁移完成)之后、同一 session 内,随动作一起 commit;若通知插入失败,整个动作回滚(宁可动作失败重试,不出现"审批成功但通知丢失")
- 请假类型中文映射常量放 notification 模块(service 或 schemas 旁),后端自有,不依赖前端

## 5. API 设计

全部挂 `/api/v1`,需 JWT(get_current_user,无权限点)。路由前缀 `/notifications`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/notifications` | 我的通知列表,`is_read`(bool,可省=全部)+ page/page_size 分页,按 created_at 倒序 |
| GET | `/notifications/unread-count` | 未读数 `{count}`,前端轮询角标用 |
| POST | `/notifications/{id}/read` | 标记已读(幂等),返回该通知 |
| POST | `/notifications/read-all` | 全部标已读,返回 `{updated: n}`(本次新置已读的条数) |

### 设计细则

- 列表响应沿用既有分页约定:items / total / page / page_size;page ≥ 1,page_size ≤ 100
- `NotificationResponse{id, type, title, content, ref_type, ref_id, read_at, created_at}`
- 所有接口只操作/返回当前用户自己的通知;不存在 → 404;非本人 → 403

## 6. 错误处理

沿用现有全局异常体系(`{"error":{code,message}}`)。

| 场景 | HTTP | code |
|---|---|---|
| 通知不存在 | 404 | NOT_FOUND |
| 标记非本人通知 | 403 | FORBIDDEN |
| 未登录 | 401 | 沿用现有 |

## 7. 测试策略

pytest + httpx AsyncClient,测试库 SQLite(沿用现有 conftest 基础设施)。

- **触发点集成测**:提交请假 → 审批人 1 条未读(leave_submitted,content 含申请人名/日期/类型);通过 → 申请人 1 条(leave_approved);驳回 → 申请人 1 条(leave_rejected,content 含驳回原因);撤回 → 双方均无新增通知
- **API 集成测**:4 接口正反路径;is_read 筛选;分页;unread-count 随动作/标记变化;read 幂等(重复标记 read_at 不变);read-all 返回正确 updated 且再次调用 updated=0;非本人 403;不存在 404;未登录 401
- **同事务原子性**:通知与审批动作在同一提交中(测试:动作成功后通知立即可查,无需额外提交/刷新)
- **迁移验证**:`alembic check` 无漂移、downgrade+replay 可逆

## 8. 部署影响

一次 Alembic 迁移(1 张新表)。seed 不变、无新依赖、无配置变更、无新服务。

## 9. 验收标准(对齐 PRD §3.4)

- [x] 有新的待审批任务时,审批人收到站内通知
- [x] 申请被通过/驳回时,申请人收到站内通知(驳回通知含原因)
- [x] 通知可标记已读/未读,支持单条与全部标记
- [x] 用户可在消息中心(列表接口)查看历史通知(含全部读态)
- [x] 未读数接口可供前端轮询角标
