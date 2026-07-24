from app.repositories.department_repository import DepartmentRepository
from tests.conftest import make_department, make_user


async def test_get_sibling_by_name_root(db):
    dept = await make_department(db, name="技术部")
    repo = DepartmentRepository(db)
    found = await repo.get_sibling_by_name("技术部", None)
    assert found is not None and found.id == dept.id
    assert await repo.get_sibling_by_name("不存在", None) is None


async def test_descendant_ids_includes_self_and_all_descendants(db):
    repo = DepartmentRepository(db)
    root = await make_department(db, name="技术部")
    child = await make_department(db, name="后端组", parent_id=root.id)
    grandchild = await make_department(db, name="平台组", parent_id=child.id)
    other = await make_department(db, name="市场部")

    ids = await repo.descendant_ids(root.id)
    assert ids == {root.id, child.id, grandchild.id}
    assert other.id not in ids


async def test_member_counts(db):
    repo = DepartmentRepository(db)
    dept = await make_department(db, name="技术部")
    await make_user(db, email="a@x.com", department_id=dept.id)
    await make_user(db, email="b@x.com", department_id=dept.id)
    await make_user(db, email="c@x.com")

    counts = await repo.member_counts()
    assert counts[dept.id] == 2


async def test_count_children_and_members(db):
    repo = DepartmentRepository(db)
    dept = await make_department(db, name="技术部")
    await make_department(db, name="后端组", parent_id=dept.id)
    await make_user(db, email="a@x.com", department_id=dept.id)

    assert await repo.count_children(dept.id) == 1
    assert await repo.count_members(dept.id) == 1
