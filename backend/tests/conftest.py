import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models.base import Base
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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


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
) -> User:
    u = User(
        email=email,
        name=name,
        hashed_password=hash_password(password),
        roles=roles or [],
        is_active=is_active,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


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
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest_asyncio.fixture
async def employee_client(client, db):
    await make_user(db, email="emp@x.com", password="Passw0rd!")
    token = await login_token(client, "emp@x.com", "Passw0rd!")
    client.headers["Authorization"] = f"Bearer {token}"
    return client
