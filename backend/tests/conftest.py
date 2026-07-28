import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from datetime import date

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models.base import Base
from app.models.department import Department
from app.models.leave import LeaveRequest
from app.models.expense import ExpenseAttachment, ExpenseRequest  # noqa: F401  # 注册进 metadata,create_all 用
from app.models.notification import Notification
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User

engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = async_sessionmaker(engine, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestSession() as session:
        yield session
    async with engine.connect() as conn:
        # SQLite 在 DROP TABLE 时会对自引用外键执行隐式清空并校验 FK,
        # 需先关闭 foreign_keys 再 drop_all
        await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        await conn.run_sync(Base.metadata.drop_all)
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        await conn.commit()


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


async def make_permission(db, code="user:create", name="创建用户") -> Permission:
    p = Permission(code=code, name=name)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def make_role(db, code="admin", name="管理员", permissions=None) -> Role:
    r = Role(code=code, name=name, permissions=permissions or [])
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


async def make_user(
    db,
    email="user@example.com",
    password="Passw0rd!",
    name="测试用户",
    roles=None,
    is_active=True,
    department_id=None,
    manager_id=None,
) -> User:
    u = User(
        email=email,
        name=name,
        hashed_password=hash_password(password),
        roles=roles or [],
        is_active=is_active,
        department_id=department_id,
        manager_id=manager_id,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def make_department(db, name="技术部", parent_id=None) -> Department:
    d = Department(name=name, parent_id=parent_id)
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


async def make_leave(
    db,
    applicant: User,
    approver: User,
    type="personal",
    start_date=date(2026, 8, 1),
    end_date=date(2026, 8, 2),
    reason="私事",
    status="pending",
) -> LeaveRequest:
    leave = LeaveRequest(
        applicant_id=applicant.id,
        approver_id=approver.id,
        type=type,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        status=status,
    )
    db.add(leave)
    await db.commit()
    await db.refresh(leave)
    return leave


async def make_notification(
    db,
    user: User,
    type="leave_submitted",
    title="新的待审批任务",
    content="测试通知",
    ref_type="leave",
    ref_id=None,
    read_at=None,
    created_at=None,
) -> Notification:
    n = Notification(
        user_id=user.id,
        type=type,
        title=title,
        content=content,
        ref_type=ref_type,
        ref_id=ref_id or uuid.uuid4(),
        read_at=read_at,
    )
    if created_at is not None:
        n.created_at = created_at
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n


async def login_token(client, email, password) -> str:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


ALL_PERMISSIONS = [
    ("user:create", "创建用户"),
    ("user:list", "查看用户列表"),
    ("user:update", "编辑用户"),
    ("user:disable", "启用/禁用用户"),
    ("role:list", "查看角色列表"),
    ("role:assign", "分配角色"),
    ("department:create", "创建部门"),
    ("department:update", "编辑/移动部门"),
    ("department:delete", "删除部门"),
    ("department:list", "查看部门树"),
    ("department:members", "查看部门人员"),
    ("leave:create", "提交/撤回请假申请"),
    ("leave:list", "查看我的申请"),
    ("leave:approve", "审批请假申请"),
    ("leave:list_all", "查看全部审批记录"),
]


@pytest_asyncio.fixture
async def admin(db) -> User:
    perms = [Permission(code=c, name=n) for c, n in ALL_PERMISSIONS]
    role = Role(code="admin", name="管理员", permissions=perms)
    user = User(
        email="admin@x.com",
        name="Admin",
        hashed_password=hash_password("Admin123!"),
        roles=[role],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_client(client, admin):
    token = await login_token(client, "admin@x.com", "Admin123!")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c


@pytest_asyncio.fixture
async def employee_client(client, db):
    await make_user(db, email="emp@x.com", password="Passw0rd!")
    token = await login_token(client, "emp@x.com", "Passw0rd!")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c
