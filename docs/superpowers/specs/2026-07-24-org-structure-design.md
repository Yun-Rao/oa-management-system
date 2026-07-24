# 组织架构模块 — 设计文档

- 版本:v1.0
- 日期:2026-07-24
- 状态:已确认
- 对应 PRD:docs/prd.md §3.2(P0 模块之二)
- 前置模块:用户认证 + RBAC(docs/superpowers/specs/2026-07-24-auth-rbac-design.md)

---

## 1. 范围

**本期做**:后端 API——部门树管理(创建/编辑/移动/删除/查看)、人员归属(部门 + 直属上级)、部门人员列表(含 Manager 数据范围过滤)。

**本期不做**:
- 前端页面(后端核心模块完成后统一开发)
- 人员调动历史留痕(PRD §6 已知技术债,后续迭代)
- 「查看子部门人员」穿透(Manager 仅看直属本部门)
- 代理审批、审批流相关逻辑(下一个 P0 模块)
- Celery/Redis(无异步任务需求)

## 2. 关键决策

| 决策点 | 结论 |
|---|---|
| 部门树存储 | 邻接表(parent_id)+ PostgreSQL 递归 CTE 查询 |
| 直属上级与部门关系 | 必须在同一部门,service 层强校验 |
| department_id / manager_id | 均可空(避免"先有部门才能建用户"死锁) |
| 删除部门 | 有员工或有子部门均禁止(409) |
| Manager「仅本部门」 | 权限点 + service 层数据范围过滤 |
| 同级部门重名 | 禁止(409) |
| 人员调动留痕 | 本期不留痕,直接改当前值 |
| 设上级前提 | 必须先有部门(manager_id 与 department_id 绑定校验) |

## 3. 数据模型

### departments(新建)

```
id          UUID 主键
name        String(100) 同级下唯一
parent_id   UUID FK → departments.id,可空(空=根部门),ON DELETE RESTRICT
created_at / updated_at(TimestampMixin 复用)
索引:parent_id
```

### users(迁移加列)

```
department_id  UUID FK → departments.id,可空,ON DELETE RESTRICT(有员工禁删的 DB 兜底)
manager_id     UUID FK → users.id,可空,ON DELETE SET NULL(上级账号删除不阻塞)
两列均加索引
```

### 规则

- **同级唯一**:同一 parent_id 下 name 不重复。PG 部分唯一索引覆盖 `parent_id IS NOT NULL` 情形;根级(parent_id IS NULL)重名由应用层校验(NULL 不参与唯一约束)
- **防环**:移动部门时,目标父部门不能是自己的后代(递归 CTE 查后代集合)
- **同部门上级**:数据库 CHECK 无法表达跨行约束,由 service 层强制;两字段联动——设上级必须先有部门,换部门时必须同时换上级或清空上级
- **不能自己是自己的上级**
- ORM 关系:`Department.parent/children/members`、`User.department/manager`,均 `lazy="selectin"`,与现有风格一致

## 4. 权限模型

新增权限点(seed 更新,幂等):

| 权限点 | 说明 | admin | manager |
|---|---|---|---|
| `department:create` | 创建部门 | ✓ | |
| `department:update` | 编辑/移动部门 | ✓ | |
| `department:delete` | 删除部门 | ✓ | |
| `department:list` | 查看部门树 | ✓ | ✓ |
| `department:members` | 查看部门人员 | ✓ | ✓(仅本部门) |

## 5. API 设计

全部挂 `/api/v1`,均需 JWT。

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/departments` | 创建部门(name, parent_id 可空) | department:create |
| GET | `/departments` | 部门树,整棵嵌套返回,节点含 member_count | department:list |
| PATCH | `/departments/{id}` | 改名 / 移动(改 parent_id,防环校验) | department:update |
| DELETE | `/departments/{id}` | 删除(有员工或子部门 → 409) | department:delete |
| GET | `/departments/{id}/members` | 部门人员列表,分页 | department:members + 数据范围 |
| PATCH | `/users/{id}/org` | 设置/修改用户部门与直属上级 | user:update(复用) |

### 设计细则

- 部门量级为几十~几百,树接口一次性返回整棵嵌套树,不分页
- **数据范围过滤**(`GET /departments/{id}/members`):admin 可看任意部门;非 admin 仅当 `{id}` 等于自己的 `department_id` 时可看,否则 403
- `PATCH /users/{id}/org`:两字段可一起或单独改;`manager_id: null` 表示清空上级;上级必须是同部门的其他用户
- `/users`、`/auth/me` 响应补充 `department`、`manager` 概要(id + name)
- 用户创建接口(PRD 已存在)本期**不**扩展部门字段,人员归属统一走 `/users/{id}/org`,保持创建接口稳定

## 6. 错误处理

沿用现有全局异常体系(`{"error":{code,message}}`)。

| 场景 | HTTP | code |
|---|---|---|
| 同级部门重名 | 409 | CONFLICT |
| 删除有员工/子部门的部门 | 409 | CONFLICT |
| 移动形成环(目标是自己的后代) | 409 | CONFLICT |
| 上级不在同部门 / 上级是自己 / 无部门却设上级 | 422 | VALIDATION_ERROR |
| 部门/用户不存在 | 404 | NOT_FOUND |
| 非 admin 查看其他部门人员 | 403 | FORBIDDEN |
| 未登录 / 无权限点 | 401 / 403 | 沿用现有 |

## 7. 测试策略

pytest + httpx AsyncClient,测试库 SQLite(沿用现有 conftest 基础设施)。

- **Service 层单测**:同级重名、防环(含"移动到自己的后代")、删除校验(有员工/有子部门/空部门)、同部门上级校验、上级是自己、数据范围过滤(admin/manager/跨部门)
- **API 集成测**:每接口正反路径 + 鉴权矩阵(401 未登录 / 403 无权限点 / 403 manager 越权)
- **迁移验证**:现有用户 upgrade 后新列为 NULL;`alembic check` 无漂移
- **seed 测试**:新权限点幂等写入;admin/manager 角色权限集合正确更新
- 递归 CTE 在 SQLite 同样支持,测试库行为与 PG 一致

## 8. 部署影响

仅一次 Alembic 迁移 + seed 重跑。无新服务、无配置变更、无新依赖。

## 9. 验收标准(对齐 PRD §3.2)

- [ ] 部门支持树形结构(父部门/子部门)
- [ ] 删除部门前有员工或子部门则禁止(409)
- [ ] Admin 可创建/编辑/删除部门、分配人员归属与直属上级
- [ ] Manager 可查看本部门人员列表,越权查看其他部门返回 403
- [ ] 移动部门不能形成环
