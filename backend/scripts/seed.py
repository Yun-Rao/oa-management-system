import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.department import Department  # noqa: F401  # 注册 mapper,供 User 关系解析
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User

PERMISSIONS = [
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

ROLES = [
    ("admin", "管理员", "系统管理员,拥有全部权限"),
    ("manager", "部门主管", "审批本部门员工申请"),
    ("employee", "普通员工", "基础员工角色"),
]

# 角色权限映射;None 表示全部权限点
ROLE_PERMISSIONS: dict[str, list[str] | None] = {
    "admin": None,
    "manager": [
        "department:list",
        "department:members",
        "leave:create",
        "leave:list",
        "leave:approve",
    ],
    "employee": ["leave:create", "leave:list"],
}


async def seed(db: AsyncSession) -> None:
    existing_perms = {
        p.code: p for p in (await db.execute(select(Permission))).scalars()
    }
    perms: dict[str, Permission] = {}
    for code, name in PERMISSIONS:
        if code in existing_perms:
            perms[code] = existing_perms[code]
        else:
            p = Permission(code=code, name=name)
            db.add(p)
            perms[code] = p
    await db.flush()

    existing_roles = {r.code: r for r in (await db.execute(select(Role))).scalars()}
    for code, name, description in ROLES:
        wanted = ROLE_PERMISSIONS[code]
        target_perms = (
            list(perms.values()) if wanted is None else [perms[c] for c in wanted]
        )
        if code not in existing_roles:
            role = Role(code=code, name=name, description=description)
            role.permissions = target_perms
            db.add(role)
            existing_roles[code] = role
        else:
            # 幂等修复:重跑 seed 时校准角色权限集合
            # 旧 permissions 集合在 flush 时于 greenlet 上下文内
            # 通过 selectin 加载以计算 diff,故无 MissingGreenlet
            existing_roles[code].permissions = target_perms
    await db.flush()

    result = await db.execute(
        select(User).where(User.email == settings.SEED_ADMIN_EMAIL)
    )
    if result.scalar_one_or_none() is None:
        db.add(
            User(
                email=settings.SEED_ADMIN_EMAIL,
                name="系统管理员",
                hashed_password=hash_password(settings.SEED_ADMIN_PASSWORD),
                roles=[existing_roles["admin"]],
            )
        )
    await db.commit()


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await seed(db)
    print(f"Seed 完成,admin 账号: {settings.SEED_ADMIN_EMAIL}")


if __name__ == "__main__":
    asyncio.run(main())
