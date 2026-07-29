import uuid

from app.core.security import hash_password
from app.models.user import User


async def test_notification_persist(db):
    from app.models.notification import Notification

    user = User(
        email="n@x.com", name="N", hashed_password=hash_password("Passw0rd!")
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    ref_id = uuid.uuid4()
    n = Notification(
        user_id=user.id,
        type="leave_submitted",
        title="新的待审批任务",
        content="张三 提交了 2026-08-01 ~ 2026-08-02 的事假申请,待您审批",
        ref_type="leave",
        ref_id=ref_id,
    )
    db.add(n)
    await db.commit()
    await db.refresh(n)

    assert n.id is not None
    assert n.user_id == user.id
    assert n.ref_id == ref_id
    assert n.read_at is None
    assert n.created_at is not None
