# 用户认证 + RBAC 权限模块 — 设计文档

- 版本:v1.0
- 日期:2026-07-24
- 状态:已确认
- 对应 PRD:docs/prd.md §3.1(P0 模块之一)

---

## 1. 范围

**本期做**:后端 API——用户认证(登录/JWT)、用户管理、角色分配、RBAC 权限校验基础设施。

**本期不做**:
- 前端页面(后端核心模块完成后统一开发)
- 组织架构(department_id/manager_id 字段下个模块再以迁移添加)
- 公开注册接口(账号仅由 Admin 创建)
- Refresh Token(仅 Access Token,过期重新登录)
- Celery/Redis(本期无异步任务需求,不提前引入)

## 2. 关键决策

| 决策点 | 结论 |
|---|---|
| 登录凭证 | 仅邮箱 + 密码 |
| Token 策略 | 单个 JWT Access Token,24 小时过期 |
| 权限校验粒度 | 权限点校验(`资源:动作` 字符串),非角色名校验 |
| 账号创建 | 仅 Admin 通过用户管理接口创建,无公开注册 |
| 初始数据 | `scripts/seed.py` 脚本创建内置角色/权限点和首个 admin |
| 代码结构 | 经典三层:路由层 / 业务逻辑层 / 数据层 |
| 密码哈希 | bcrypt(passlib) |
| 测试数据库 | SQLite + aiosqlite,避免测试依赖 Docker |

## 3. 项目结构

```
backend/
├── app/
│   ├── api/v1/          # 路由层:参数解析、调用 service、返回响应
│   │   ├── auth.py
│   │   ├── users.py
│   │   └── roles.py
│   ├── services/        # 业务逻辑层
│   ├── repositories/    # 数据层:SQLAlchemy 查询封装
│   ├── models/          # ORM 模型
│   ├── schemas/         # Pydantic 请求/响应模型
│   ├── core/            # 配置、安全(JWT/bcrypt)、依赖注入、异常
│   └── main.py
├── tests/
├── scripts/seed.py
├── alembic/
└── requirements.txt
```

## 4. 数据模型

```
users
  id               UUID 主键
  email            String 唯一索引,登录凭证
  hashed_password  String (bcrypt)
  name             String 真实姓名
  is_active        Boolean 默认 true,禁用后无法登录
  created_at / updated_at

roles                          permissions
  id    UUID 主键               id    UUID 主键
  code  String 唯一 (如 admin)   code  String 唯一 (如 user:create)
  name  String (如 管理员)       name  String (如 创建用户)
  description                  description

user_roles (user_id, role_id)              多对多
role_permissions (role_id, permission_id)  多对多
```

### 内置数据(seed 脚本)

| 角色 | 权限点 |
|---|---|
| admin | user:create / user:list / user:update / user:disable / role:list / role:assign |
| manager | 无专属权限点(占位,为审批模块预留) |
| employee | 无特殊权限点,基础登录访问 |

权限校验通过 FastAPI 依赖注入实现:`require_permission("user:create")`。

## 5. API 设计

全部挂在 `/api/v1` 下,除登录外都需要 JWT。

### 认证

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/auth/login` | 邮箱+密码登录,返回 `{access_token, token_type, expires_in}` | 公开 |
| GET | `/auth/me` | 当前用户信息 + 角色 + 权限点列表 | 登录 |
| POST | `/auth/change-password` | 修改自己的密码(需提供旧密码) | 登录 |

### 用户管理

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/users` | 创建用户(邮箱、姓名、初始密码) | user:create |
| GET | `/users` | 用户列表,分页 + 按姓名/邮箱搜索 | user:list |
| PATCH | `/users/{id}` | 编辑用户(姓名、邮箱) | user:update |
| PATCH | `/users/{id}/status` | 启用/禁用 | user:disable |

### 角色管理

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/roles` | 角色列表(含每个角色的权限点) | role:list |
| PUT | `/users/{id}/roles` | 给用户分配角色(整体替换,传角色 code 数组) | role:assign |

### 设计细则

- 登录失败统一返回 `401 邮箱或密码错误`,不区分用户不存在/密码错误,防账号枚举
- 禁用用户不删数据;禁用后已有 Token 在下次请求时因 `is_active=False` 被 401 拒绝
- 角色分配用整体替换(PUT),简化并发处理
- 管理员不能移除自己的 admin 角色(防系统锁死)
- 密码长度限制 8–72 字符(bcrypt 仅取前 72 字节,不限制上限会造成静默截断弱化)

## 6. 错误处理

统一错误响应格式,全局异常处理器转换所有业务异常:

```json
{ "error": { "code": "NOT_FOUND", "message": "用户不存在" } }
```

| 场景 | HTTP | code |
|---|---|---|
| 未带 Token / Token 过期 / 用户已禁用 | 401 | UNAUTHORIZED |
| 已登录但无权限点 | 403 | FORBIDDEN |
| 登录失败 | 401 | INVALID_CREDENTIALS |
| 请求参数校验失败 | 422 | VALIDATION_ERROR(Pydantic 默认格式) |
| 资源不存在 | 404 | NOT_FOUND |
| 唯一性冲突(邮箱已存在) | 409 | CONFLICT |

业务层抛自定义异常,路由层不 try/except,由全局处理器统一映射。

## 7. 配置管理

`.env` + pydantic-settings,提供 `.env.example`,密钥不入库:

- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `JWT_EXPIRE_MINUTES`(默认 1440,即 24 小时)
- `SEED_ADMIN_EMAIL`
- `SEED_ADMIN_PASSWORD`

## 8. 测试策略

pytest + httpx AsyncClient,测试库 SQLite。

- **Service 层单测**:密码校验、Token 生成/过期、用户 CRUD、角色分配、禁用逻辑、防自我降级
- **API 集成测**:每个接口正反路径——未登录 401、无权限 403、正常流程 200
- 重点覆盖 PRD 验收标准:密码不明文存储、Token 过期后 401、未登录访问业务接口 401
- repository 层不单独测,通过 service 测试覆盖

## 9. 部署形态

`docker-compose.yml`:PostgreSQL + 后端两个服务。本地开发可 `uvicorn` 直连本地 Postgres,或用 compose 起库。

## 10. 验收标准(对齐 PRD §3.1)

- [ ] 密码使用 bcrypt 加密存储,任何接口/日志不输出明文
- [ ] Token 设置过期时间,过期后请求返回 401
- [ ] 未登录访问任何业务接口返回 401
- [ ] Admin 可创建/编辑/禁用用户、分配角色
- [ ] 用户可自行修改密码
