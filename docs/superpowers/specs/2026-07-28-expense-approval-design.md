# 报销审批模块(后端)— 设计文档

- 版本:v1.0
- 日期:2026-07-28
- 状态:已确认
- 对应 PRD:docs/prd.md §3.3.2(P1 模块,含二级审批)
- 前置模块:请假审批(同构参照)、消息通知(docs/superpowers/specs/2026-07-26-backend-notification-design.md,复用 NotificationService,ref_type="expense")

---

## 1. 范围

**本期做**:后端 API——报销申请提交(金额/类型/说明/附件凭证)、一级(部门主管)审批、超阈值二级(HR/Admin 权限池)审批、驳回/撤回、我的申请/待我审批/全部记录查询、附件鉴权下载、各触发点站内通知。

**本期不做**:
- 前端报销页面(后续独立 spec)
- 报销单编辑/删除(审批记录只可追加,PRD 审计要求)
- 代理审批(PRD Open Question,本期不做)
- 金额统计/报表(P2 数据看板范畴)
- OSS 对象存储(PRD Open Question 既定:本期本地存储)
- 阈值的管理后台配置界面(本期环境变量即可)

## 2. 关键决策

| 决策点 | 结论 |
|---|---|
| 总体结构 | 对称复制请假模式:expense_requests + expense_status_history(只追加)双表,repository 乐观锁 transition,service 动作点生成通知(只 db.add,同事务 commit) |
| 二级审批人 | 权限池:任何持有 `expense:approve_l2` 权限的用户(HR/Admin)均可审批;`pending_l2` 时 `approver_id` 置 NULL 表达"池待领",实际审批人记录在 history.actor_id |
| 阈值配置 | `Settings.EXPENSE_L2_THRESHOLD: Decimal = 2000`,`.env` 可覆盖;判定只发生在 L1 approve 动作点(submit 一律转 pending_l1,无分支),取审批当时配置值——运行期改阈值后,L1 未审的在途单按新值判定,已终审单不受影响 |
| 报销类型 | 固定枚举 5 类:travel / office / entertainment / transport / other,String(20) 存储,中文映射常量放 notification 模块(与 LEAVE_TYPE_LABELS 同级加 EXPENSE_TYPE_LABELS) |
| 金额 | Numeric(12,2),> 0,无上限 |
| 附件 | 必填 1~5 个,仅 jpg/jpeg/png/pdf,单文件 ≤ 5MB(魔数嗅探,不轻信 content_type);一体 multipart 提交(单请求带表单字段+文件);先落盘后写库,DB 失败删除已写文件,无孤儿;下载走鉴权接口,不暴露磁盘路径 |
| 撤回 | 支持:申请人在 pending_l1/pending_l2 可撤回;撤回不通知(同请假) |
| 二级通知 | L1 通过且需二级时,扇出通知所有持 `expense:approve_l2` 权限的用户 |
| 通知原子性 | 沿用通知模块既定约束:notify_leave_*/notify_expense_* 只 db.add() 不 commit,commit 由 ExpenseRepository.create/transition 完成;transition 并发失败(rowcount=0)rollback 时挂起通知一并丢弃 |
| 自审拦截 | 申请人不能审自己的单:L1 天然不可能(approver 是主管);L2 显式校验 `applicant_id != current_user.id`(防 Admin 自审) |

## 3. 数据模型

### expense_requests(新建,挂 TimestampMixin)

```
id            UUID 主键(client 端 default=uuid.uuid4,service 显式生成——通知 ref_id 需要)
applicant_id  UUID FK → users.id, ON DELETE RESTRICT, index(申请人)
type          String(20):travel / office / entertainment / transport / other
amount        Numeric(12,2),> 0
reason        String(500)(说明)
status        String(20), index:pending_l1 / pending_l2 / approved / rejected / cancelled
approver_id   UUID FK → users.id, ON DELETE RESTRICT, index,可空
              (pending_l1 = 直属主管;转入 pending_l2 置 NULL 表达权限池;终态保留最后一级语义不设回)
关系:applicant / approver(lazy="selectin"),history(back_populates,按 created_at 升序),attachments
```

### expense_status_history(新建,只追加,不挂 TimestampMixin)

```
id          UUID 主键
request_id  UUID FK → expense_requests.id, ON DELETE RESTRICT, index
from_status String(20) 可空(创建时 NULL)
to_status   String(20)
actor_id    UUID FK → users.id, ON DELETE RESTRICT(动作人;二级审批实际审批人在此留痕)
comment     String(500) 可空(驳回原因)
created_at  DateTime,server_default=func.now()
```

### expense_attachments(新建)

```
id            UUID 主键
expense_id    UUID FK → expense_requests.id, ON DELETE CASCADE, index
filename      String(255):原始文件名(展示用)
stored_path   String(500):磁盘相对路径(相对 UPLOAD_DIR)
content_type  String(100)
size_bytes    Integer
created_at    DateTime,server_default=func.now()
```

### 配置项

```
Settings.EXPENSE_L2_THRESHOLD: Decimal = 2000   # 二级审批金额阈值(元)
Settings.UPLOAD_DIR: str = "uploads"            # 附件根目录(docker 挂 volume)
```

### 规则

- 状态历史只 INSERT,审批记录不可篡改、只能追加(PRD §4 数据一致性)
- `approver_id` 可空是权限池语义的落库表达:pending_l2 单不属于任何具体人,todo 按 status 查而非按 approver_id
- expense_attachments 随主表查询 selectin 加载;下载按 id 查库校验可见性

## 4. 状态机与审批流

```
submit( amount ≤ 阈值 / > 阈值 ) ──► pending_l1(approver_id = 主管)
pending_l1 ── L1 approve ──► amount ≤ 阈值:approved
                             amount > 阈值:pending_l2(approver_id=NULL,history 记 L1 通过)
pending_l2 ── L2 approve(权限池任一人) ──► approved
pending_l1 / pending_l2 ── reject(当前级,reason 必填) ──► rejected(流程终止)
pending_l1 / pending_l2 ── cancel(申请人) ──► cancelled
```

- transition 乐观锁:`UPDATE ... SET status=:to WHERE id=:id AND status=:from`,rowcount=0 → rollback + 409 ConflictError(同请假 LeaveRepository.transition)
- L1 审批校验:`expense:approve` 权限 + `approver_id == current_user.id`;L2 审批校验:`expense:approve_l2` 权限(不比对具体人)+ 非申请人本人
- "当前第几级、审批人是谁"由 status + approver + history 表达:pending_l1=第一级(主管,approver 字段);pending_l2=第二级(权限池,approver 为 NULL);history 依序记录每级动作人与时间(PRD §3.3.2 验收)

## 5. 通知触发点与内容模板

复用 NotificationService,新增 `notify_expense_*` 生成器(全部只 db.add,同事务),`ref_type="expense"`,`ref_id`=报销单 id。

| 时机(expense_service 内) | 接收人 | type | title | content 模板 |
|---|---|---|---|---|
| submit 成功 | 一级审批人(主管) | expense_submitted | 新的待审批任务 | `{applicant_name} 提交了 {amount} 元的{type_label}报销,待您审批` |
| L1 approve 且转入二级 | 所有持 expense:approve_l2 权限用户(扇出) | expense_pending_l2 | 新的待审批任务 | `{applicant_name} 的 {amount} 元{type_label}报销已通过主管审批,待您二级审批` |
| 终审通过(L1 直达或 L2) | 申请人 | expense_approved | 报销申请已通过 | `您 {amount} 元的{type_label}报销已通过` |
| 任一级 reject | 申请人 | expense_rejected | 报销申请已驳回 | `您 {amount} 元的{type_label}报销已被驳回:{reason}` |
| cancel | —(不通知) | | | |

- amount 格式化:去尾零的十进制字符串(如 `2000`、`1999.5`),与 pydantic Decimal 序列化一致
- type_label ∈ 差旅/办公/招待/交通/其他;EXPENSE_TYPE_LABELS 放 notification 模块
- content 超长截断:沿用通知模块 `_clamp_content`(500 字符),reject 模板含用户输入 reason,必须过截断
- 扇出实现:UserRepository 加 `list_by_permission(code)`,service 循环 db.add;权限池人数少,性能无忧

## 6. API 设计

全部挂 `/api/v1`,路由前缀 `/expenses`,静态段(`/mine`、`/todo`、`/attachments`)在 `/{expense_id}` 之前注册。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/expenses` | expense:create | multipart/form-data:type/amount/reason 字段 + files(1~5);201 返回 ExpenseResponse |
| GET | `/expenses/mine` | expense:list | 我的申请,status/type 过滤 + 分页,created_at 倒序 |
| GET | `/expenses/todo` | expense:approve 或 expense:approve_l2 | 待办:L1 权限→pending_l1 且 approver_id=我;L2 权限→全部 pending_l2;两者都有→合并按 created_at 倒序 |
| GET | `/expenses` | expense:list_all | 全部记录,部门/状态/类型/时间过滤 + 分页(Admin) |
| GET | `/expenses/{id}` | expense:list + 可见性 | 详情含 history + attachments;可见性:本人/当前级审批人(L1 比对 approver_id,L2 持 approve_l2)/list_all 持有人 |
| GET | `/expenses/{id}/attachments/{att_id}` | 同详情可见性 | 鉴权下载(FileResponse),att 必须属于该 expense |
| POST | `/expenses/{id}/cancel` | expense:create + 本人 | 撤回,仅 pending_l1/pending_l2 |
| POST | `/expenses/{id}/approve` | 见 §4 分级校验 | 当前级通过 |
| POST | `/expenses/{id}/reject` | 见 §4 分级校验 | 驳回,reason 必填 |

### 设计细则

- 分页约定沿用:items / total / page / page_size,page ≥ 1,page_size ≤ 100
- `ExpenseResponse{id, type, amount, reason, status, applicant_id, approver_id, created_at, updated_at}`;`ExpenseDetailResponse` 加 `history[]`(含 actor 姓名)与 `attachments[]`(id/filename/content_type/size_bytes,不含 stored_path)
- 新权限点 5 个:`expense:create` / `expense:list` / `expense:approve` / `expense:approve_l2` / `expense:list_all`;seed 追加:Admin 全量、部门主管 approve、员工 create+list(对齐请假 seed 惯例);`expense:approve_l2` 仅 Admin/HR 角色
- 附件限制在 schema/路由层校验:数量 1~5、单文件 ≤ 5MB、扩展名 + 魔数(jpeg FFD8、png 89504E47、pdf %PDF)
- 附件落盘:`{UPLOAD_DIR}/expenses/{expense_id}/{uuid4}.{ext}`;流程:校验 → 读文件落盘 → DB 事务(失败则删已写文件)→ commit;下载 404/403 语义同详情

## 7. 错误处理

沿用现有全局异常体系(`{"error":{code,message}}`)。

| 场景 | HTTP | code |
|---|---|---|
| 报销单/附件不存在 | 404 | NOT_FOUND |
| 越权(非本人/非当前级审批人/无权限点) | 403 | FORBIDDEN |
| 状态冲突(重复审批/已终态操作/并发 transition) | 409 | CONFLICT |
| 校验失败(金额≤0/类型非法/附件数量、类型、大小超限/驳回无原因) | 422 或 400 | VALIDATION_ERROR |
| 未登录 | 401 | 沿用现有 |

## 8. 测试策略

pytest + httpx AsyncClient,测试库内存 SQLite(沿用 conftest 基础设施,新增 make_expense 工厂;附件测试用 tmp_path 作 UPLOAD_DIR 隔离)。

- **模型层**:三表持久化往返;attachments 与主表关系加载
- **仓库层**:list_mine 过滤/分页/倒序;todo 双视角(L1 只看自己的 pending_l1,L2 看全部 pending_l2,双权限合并);transition 乐观锁
- **服务层**:阈值分支(≤2000 直达 approved、>2000 转 pending_l2 且 approver_id 置 NULL);L2 申请人自审拦截;notify_expense_* 文案(金额/类型/原因);扇出人数正确;cancel 不通知;reject 内容过 _clamp_content
- **API 层**:multipart 提交(含真实文件字节);附件数量/类型/大小 422;越权 403;未登录 401;下载鉴权(可见者 200,不可见 403);todo 合并视图
- **集成**:提交→L1→L2 全链路经 /notifications 接口断言通知送达(含二级扇出);重复审批 409 不产生重复通知;L1 通过后驳回仍正确终止
- **迁移**:downgrade+upgrade+check 可逆无漂移;全量 pytest 无回归

## 9. 部署影响

一次 Alembic 迁移(3 张新表)。seed 追加 5 个权限点及角色授权;新增 2 个配置项(阈值/上传目录,均有默认值);docker-compose 后端服务挂 uploads volume;无新 Python 依赖(文件处理用标准库 + FastAPI UploadFile)。

## 10. 验收标准(对齐 PRD §3.3.2)

- [ ] 金额 ≤ 阈值仅需主管审批即通过;> 阈值需主管通过后再经 HR/Admin 二级审批
- [ ] 任一级驳回流程终止,状态"已驳回";全部通过状态"已通过"
- [ ] 阈值可配置(环境变量,不写死在代码里)
- [ ] 二级审批场景下,可清晰区分当前处于第几级、审批人是谁
- [ ] 报销申请必含 1~5 张附件凭证,附件可鉴权下载
- [ ] 各触发点通知正确送达(提交→主管;转入二级→扇出权限池;通过/驳回→申请人;撤回不通知)
