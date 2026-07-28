from decimal import Decimal

from app.core.security import hash_password
from app.models.user import User


async def test_expense_persist(db):
    from app.models.expense import ExpenseAttachment, ExpenseRequest

    user = User(
        email="e@x.com", name="E", hashed_password=hash_password("Passw0rd!")
    )
    mgr = User(
        email="m@x.com", name="M", hashed_password=hash_password("Passw0rd!")
    )
    db.add_all([user, mgr])
    await db.commit()
    await db.refresh(user)
    await db.refresh(mgr)

    e = ExpenseRequest(
        applicant_id=user.id,
        approver_id=mgr.id,
        type="travel",
        amount=Decimal("1999.50"),
        reason="出差打车",
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)

    assert e.id is not None
    assert e.status == "pending_l1"
    assert e.amount == Decimal("1999.50")
    assert e.created_at is not None

    att = ExpenseAttachment(
        expense_id=e.id,
        filename="a.png",
        stored_path=f"expenses/{e.id}/x.png",
        content_type="image/png",
        size_bytes=8,
    )
    db.add(att)
    await db.commit()
    await db.refresh(e)
    assert len(e.attachments) == 1
    assert e.attachments[0].filename == "a.png"
