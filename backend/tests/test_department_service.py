import pytest

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.schemas.department import DepartmentCreate, DepartmentUpdate
from app.services.department_service import DepartmentService
from tests.conftest import make_department, make_user


async def test_create_root_and_child(db):
    svc = DepartmentService(db)
    root = await svc.create_department(DepartmentCreate(name="技术部"))
    child = await svc.create_department(
        DepartmentCreate(name="后端组", parent_id=root.id)
    )
    assert child.parent_id == root.id


async def test_create_rejects_sibling_duplicate_name(db):
    svc = DepartmentService(db)
    await svc.create_department(DepartmentCreate(name="技术部"))
    with pytest.raises(ConflictError, match="同级部门下已存在同名部门"):
        await svc.create_department(DepartmentCreate(name="技术部"))


async def test_create_allows_same_name_under_different_parent(db):
    svc = DepartmentService(db)
    a = await svc.create_department(DepartmentCreate(name="甲部门"))
    b = await svc.create_department(DepartmentCreate(name="乙部门"))
    await svc.create_department(DepartmentCreate(name="同名组", parent_id=a.id))
    await svc.create_department(DepartmentCreate(name="同名组", parent_id=b.id))


async def test_create_rejects_unknown_parent(db):
    import uuid

    svc = DepartmentService(db)
    with pytest.raises(NotFoundError, match="父部门不存在"):
        await svc.create_department(
            DepartmentCreate(name="孤儿", parent_id=uuid.uuid4())
        )


async def test_get_tree_nested_with_member_count(db):
    svc = DepartmentService(db)
    root = await svc.create_department(DepartmentCreate(name="技术部"))
    child = await svc.create_department(
        DepartmentCreate(name="后端组", parent_id=root.id)
    )
    await make_user(db, email="a@x.com", department_id=child.id)

    tree = await svc.get_tree()
    assert len(tree) == 1
    assert tree[0].name == "技术部"
    assert tree[0].member_count == 0
    assert tree[0].children[0].name == "后端组"
    assert tree[0].children[0].member_count == 1


async def test_update_rename_and_move(db):
    svc = DepartmentService(db)
    a = await svc.create_department(DepartmentCreate(name="甲"))
    b = await svc.create_department(DepartmentCreate(name="乙"))
    moved = await svc.update_department(
        b.id, DepartmentUpdate(name="乙改", parent_id=a.id)
    )
    assert moved.name == "乙改"
    assert moved.parent_id == a.id


async def test_update_rejects_move_to_descendant(db):
    svc = DepartmentService(db)
    root = await svc.create_department(DepartmentCreate(name="技术部"))
    child = await svc.create_department(
        DepartmentCreate(name="后端组", parent_id=root.id)
    )
    with pytest.raises(ConflictError, match="不能将部门移动到其自身或子部门下"):
        await svc.update_department(root.id, DepartmentUpdate(parent_id=child.id))
    with pytest.raises(ConflictError, match="不能将部门移动到其自身或子部门下"):
        await svc.update_department(root.id, DepartmentUpdate(parent_id=root.id))


async def test_update_rejects_sibling_name_conflict_on_move(db):
    svc = DepartmentService(db)
    a = await svc.create_department(DepartmentCreate(name="甲"))
    await svc.create_department(DepartmentCreate(name="后端组", parent_id=a.id))
    orphan = await svc.create_department(DepartmentCreate(name="后端组"))
    with pytest.raises(ConflictError, match="同级部门下已存在同名部门"):
        await svc.update_department(orphan.id, DepartmentUpdate(parent_id=a.id))


async def test_delete_empty_department(db):
    svc = DepartmentService(db)
    dept = await svc.create_department(DepartmentCreate(name="技术部"))
    await svc.delete_department(dept.id)
    assert await svc.departments.get_by_id(dept.id) is None


async def test_delete_rejects_department_with_children(db):
    svc = DepartmentService(db)
    root = await svc.create_department(DepartmentCreate(name="技术部"))
    await svc.create_department(DepartmentCreate(name="后端组", parent_id=root.id))
    with pytest.raises(ConflictError, match="请先删除或移动子部门"):
        await svc.delete_department(root.id)


async def test_delete_rejects_department_with_members(db):
    svc = DepartmentService(db)
    dept = await svc.create_department(DepartmentCreate(name="技术部"))
    await make_user(db, email="a@x.com", department_id=dept.id)
    with pytest.raises(ConflictError, match="部门下还有员工,无法删除"):
        await svc.delete_department(dept.id)


async def test_list_members_scope(db):
    svc = DepartmentService(db)
    dept = await svc.create_department(DepartmentCreate(name="技术部"))
    other = await svc.create_department(DepartmentCreate(name="市场部"))
    await make_user(db, email="a@x.com", department_id=dept.id)

    admin = await make_user(db, email="admin@x.com", roles=[])
    from tests.conftest import ALL_PERMISSIONS
    from app.models.permission import Permission
    from app.models.role import Role

    perms = [Permission(code=c, name=n) for c, n in ALL_PERMISSIONS]
    admin.roles = [Role(code="admin", name="管理员", permissions=perms)]
    await db.commit()

    members, total = await svc.list_members(dept.id, 1, 20, admin)
    assert total == 1

    outsider = await make_user(db, email="m@x.com", department_id=other.id)
    with pytest.raises(ForbiddenError, match="无权查看其他部门的人员"):
        await svc.list_members(dept.id, 1, 20, outsider)

    insider = await make_user(db, email="i@x.com", department_id=dept.id)
    members, total = await svc.list_members(dept.id, 1, 20, insider)
    assert total == 2
