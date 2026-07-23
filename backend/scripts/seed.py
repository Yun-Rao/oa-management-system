import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
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
]

ROLES = [
    ("admin", "管理员", "系统管理员,拥有全部权限"),
    ("manager", "部门主管", "审批本部门员工申请"),
    ("employee", "普通员工", "基础员工角色"),
]


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
        if code not in existing_roles:
            role = Role(code=code, name=name, description=description)
            if code == "admin":
                role.permissions = list(perms.values())
            db.add(role)
            existing_roles[code] = role
        elif code == "admin":
            # 已存在角色的 permissions 已随上面的 select(Role) 查询通过 selectin
            # 一并加载,此处重新赋值不会触发懒加载 IO
            existing_roles[code].permissions = list(perms.values())
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
