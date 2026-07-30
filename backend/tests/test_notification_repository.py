from datetime import datetime

from sqlalchemy import select

from app.models.notification import Notification
from tests.conftest import make_notification, make_user


async def test_list_mine_only_own_and_desc(db):
    from app.repositories.notification_repository import NotificationRepository

    u1 = await make_user(db, email="u1@x.com")
    u2 = await make_user(db, email="u2@x.com")
    await make_notification(db, u1, title="旧", created_at=datetime(2026, 7, 1, 9, 0, 0))
    await make_notification(db, u1, title="新", created_at=datetime(2026, 7, 2, 9, 0, 0))
    await make_notification(db, u2, title="别人的")

    items, total = await NotificationRepository(db).list_mine(u1.id, None, 0, 20)
    assert total == 2
    assert [n.title for n in items] == ["新", "旧"]


async def test_list_mine_is_read_filter(db):
    from app.repositories.notification_repository import NotificationRepository

    u = await make_user(db, email="u1@x.com")
    await make_notification(db, u, title="未读")
    await make_notification(db, u, title="已读", read_at=datetime(2026, 7, 1, 10, 0, 0))

    repo = NotificationRepository(db)
    _, total_unread = await repo.list_mine(u.id, False, 0, 20)
    _, total_read = await repo.list_mine(u.id, True, 0, 20)
    _, total_all = await repo.list_mine(u.id, None, 0, 20)
    assert (total_unread, total_read, total_all) == (1, 1, 2)


async def test_list_mine_pagination(db):
    from app.repositories.notification_repository import NotificationRepository

    u = await make_user(db, email="u1@x.com")
    for i in range(3):
        await make_notification(db, u, title=f"n{i}", created_at=datetime(2026, 7, 1, 10, i, 0))

    items, total = await NotificationRepository(db).list_mine(u.id, None, 2, 2)
    assert total == 3
    assert len(items) == 1


async def test_unread_count(db):
    from app.repositories.notification_repository import NotificationRepository

    u = await make_user(db, email="u1@x.com")
    await make_notification(db, u)
    await make_notification(db, u)
    await make_notification(db, u, read_at=datetime(2026, 7, 1, 10, 0, 0))

    assert await NotificationRepository(db).unread_count(u.id) == 2


async def test_mark_read_sets_read_at_and_idempotent(db):
    from app.repositories.notification_repository import NotificationRepository

    u = await make_user(db, email="u1@x.com")
    n = await make_notification(db, u)
    repo = NotificationRepository(db)

    n = await repo.mark_read(n)
    assert n.read_at is not None
    first_read_at = n.read_at

    n = await repo.mark_read(n)
    assert n.read_at == first_read_at


async def test_mark_all_read_returns_updated_count(db):
    from app.repositories.notification_repository import NotificationRepository

    u1 = await make_user(db, email="u1@x.com")
    u2 = await make_user(db, email="u2@x.com")
    await make_notification(db, u1)
    await make_notification(db, u1)
    await make_notification(db, u1, read_at=datetime(2026, 7, 1, 10, 0, 0))
    await make_notification(db, u2)

    repo = NotificationRepository(db)
    assert await repo.mark_all_read(u1.id) == 2
    assert await repo.mark_all_read(u1.id) == 0
    assert await repo.unread_count(u2.id) == 1
