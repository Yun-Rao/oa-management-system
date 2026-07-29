import uuid
from decimal import Decimal

import pytest
import pytest_asyncio

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from tests.conftest import (
    make_expense,
    make_permission,
    make_role,
    make_user,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest_asyncio.fixture
async def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


async def perms_role(db, codes, role_code):
    # get-or-create:同一测试内 _mk_chain 可能已建同名权限,直接 INSERT 会触发 UNIQUE 冲突
    from sqlalchemy import select

    from app.models.permission import Permission

    perms = []
    for c in codes:
        existing = (
            await db.execute(select(Permission).where(Permission.code == c))
        ).scalar_one_or_none()
        perms.append(existing or await make_permission(db, code=c, name=c))
    return await make_role(db, code=role_code, name=role_code, permissions=perms)


async def test_create_requires_manager(db, upload_dir):
    from app.services.expense_service import ExpenseService

    emp = await make_user(db, email="e@x.com")
    with pytest.raises(ValidationError):
        await ExpenseService(db).create_expense(
            "travel", Decimal("100"), "x", [("a.png", "image/png", PNG)], emp
        )


async def test_create_stores_files_and_rows(db, upload_dir):
    from app.services.expense_service import ExpenseService

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    e = await ExpenseService(db).create_expense(
        "travel",
        Decimal("1999.50"),
        "出差打车",
        [("a.png", "image/png", PNG), ("b.pdf", "application/pdf", b"%PDF-1.4 fake")],
        emp,
    )
    assert e.status == "pending_l1"
    assert e.approver_id == mgr.id
    assert len(e.attachments) == 2
    for att in e.attachments:
        assert (upload_dir / att.stored_path).exists()
        assert att.size_bytes > 0
    assert len(e.history) == 1
    assert e.history[0].to_status == "pending_l1"


async def _mk_chain(db):
    mgr_role = await perms_role(db, ["expense:approve"], "mgr-r")
    l2_role = await perms_role(db, ["expense:approve_l2"], "hr-r")
    mgr = await make_user(db, email="m@x.com", roles=[mgr_role])
    admin = await make_user(db, email="a@x.com", roles=[l2_role])
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    return mgr, admin, emp


async def test_approve_l1_small_amount_directly_approved(db):
    from app.services.expense_service import ExpenseService

    mgr, _, emp = await _mk_chain(db)
    e = await make_expense(db, emp, mgr, amount=Decimal("2000.00"))
    e = await ExpenseService(db).approve_expense(e.id, mgr)
    assert e.status == "approved"
    assert e.approver_id == mgr.id


async def test_approve_l1_large_amount_goes_pending_l2(db):
    from app.services.expense_service import ExpenseService

    mgr, _, emp = await _mk_chain(db)
    e = await make_expense(db, emp, mgr, amount=Decimal("2000.01"))
    e = await ExpenseService(db).approve_expense(e.id, mgr)
    assert e.status == "pending_l2"
    assert e.approver_id is None
    assert [h.to_status for h in e.history] == ["pending_l2"]


async def test_approve_l2_success(db):
    from app.services.expense_service import ExpenseService

    mgr, admin, emp = await _mk_chain(db)
    e = await make_expense(db, emp, None, amount=Decimal("3000"), status="pending_l2")
    e = await ExpenseService(db).approve_expense(e.id, admin)
    assert e.status == "approved"


async def test_approve_l2_rejects_applicant_self(db):
    from app.services.expense_service import ExpenseService

    mgr, admin, emp = await _mk_chain(db)
    role = await perms_role(db, ["expense:approve_l2"], "hr-r2")
    emp.roles.append(role)
    await db.commit()
    e = await make_expense(db, emp, None, amount=Decimal("3000"), status="pending_l2")
    with pytest.raises(ForbiddenError):
        await ExpenseService(db).approve_expense(e.id, emp)


async def test_approve_l1_wrong_approver_forbidden(db):
    from app.services.expense_service import ExpenseService

    mgr, admin, emp = await _mk_chain(db)
    e = await make_expense(db, emp, mgr)
    with pytest.raises(ForbiddenError):
        await ExpenseService(db).approve_expense(e.id, admin)


async def test_approve_on_terminal_status_conflict(db):
    from app.services.expense_service import ExpenseService

    mgr, _, emp = await _mk_chain(db)
    e = await make_expense(db, emp, mgr, status="approved")
    with pytest.raises(ConflictError):
        await ExpenseService(db).approve_expense(e.id, mgr)


async def test_reject_requires_reason(db):
    from app.services.expense_service import ExpenseService

    mgr, _, emp = await _mk_chain(db)
    e = await make_expense(db, emp, mgr)
    with pytest.raises(ValidationError):
        await ExpenseService(db).reject_expense(e.id, mgr, "  ")


async def test_reject_l2_terminates(db):
    from app.services.expense_service import ExpenseService

    mgr, admin, emp = await _mk_chain(db)
    e = await make_expense(db, emp, None, status="pending_l2")
    e = await ExpenseService(db).reject_expense(e.id, admin, "超标")
    assert e.status == "rejected"
    assert e.history[-1].comment == "超标"


async def test_cancel_rules(db):
    from app.services.expense_service import ExpenseService

    mgr, admin, emp = await _mk_chain(db)
    other = await make_user(db, email="o@x.com")
    svc = ExpenseService(db)

    e1 = await make_expense(db, emp, mgr)
    with pytest.raises(ForbiddenError):
        await svc.cancel_expense(e1.id, other)

    e2 = await make_expense(db, emp, mgr, status="approved")
    with pytest.raises(ConflictError):
        await svc.cancel_expense(e2.id, emp)

    e3 = await make_expense(db, emp, None, status="pending_l2")
    e3 = await svc.cancel_expense(e3.id, emp)
    assert e3.status == "cancelled"


async def test_detail_visibility(db):
    from app.services.expense_service import ExpenseService

    mgr, admin, emp = await _mk_chain(db)
    all_role = await perms_role(db, ["expense:list_all"], "all-r")
    viewer = await make_user(db, email="v@x.com", roles=[all_role])
    stranger = await make_user(db, email="s@x.com")
    svc = ExpenseService(db)

    e = await make_expense(db, emp, mgr, status="pending_l1")
    for u in (emp, mgr, viewer):
        assert (await svc.get_detail(e.id, u)).id == e.id
    with pytest.raises(ForbiddenError):
        await svc.get_detail(e.id, stranger)
    # pending_l1 时 l2 权限者不可见
    with pytest.raises(ForbiddenError):
        await svc.get_detail(e.id, admin)

    e2 = await make_expense(db, emp, None, status="pending_l2")
    assert (await svc.get_detail(e2.id, admin)).id == e2.id
    # 一级审批人在单进入二级后不再可见
    with pytest.raises(ForbiddenError):
        await svc.get_detail(e2.id, mgr)


async def test_get_attachment_belongs_to_expense(db):
    from app.models.expense import ExpenseAttachment
    from app.services.expense_service import ExpenseService

    mgr, _, emp = await _mk_chain(db)
    e1 = await make_expense(db, emp, mgr)
    e2 = await make_expense(db, emp, mgr)
    att = ExpenseAttachment(
        expense_id=e2.id,
        filename="a.png",
        stored_path="expenses/x/y.png",
        content_type="image/png",
        size_bytes=3,
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)

    svc = ExpenseService(db)
    got = await svc.get_attachment(e2.id, att.id, emp)
    assert got.id == att.id
    from app.core.exceptions import NotFoundError
    with pytest.raises(NotFoundError):
        await svc.get_attachment(e1.id, att.id, emp)
    with pytest.raises(NotFoundError):
        await svc.get_attachment(e2.id, uuid.uuid4(), emp)
