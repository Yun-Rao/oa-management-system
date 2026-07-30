import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, notification_id: uuid.UUID) -> Notification | None:
        return await self.db.get(Notification, notification_id)

    async def list_mine(
        self, user_id: uuid.UUID, is_read: bool | None, offset: int, limit: int
    ) -> tuple[list[Notification], int]:
        conditions = [Notification.user_id == user_id]
        if is_read is True:
            conditions.append(Notification.read_at.is_not(None))
        elif is_read is False:
            conditions.append(Notification.read_at.is_(None))
        total = (
            await self.db.execute(
                select(func.count()).select_from(Notification).where(*conditions)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(Notification)
            .where(*conditions)
            .order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def unread_count(self, user_id: uuid.UUID) -> int:
        return (
            await self.db.execute(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.user_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
        ).scalar_one()

    async def mark_read(self, notification: Notification) -> Notification:
        if notification.read_at is None:
            await self.db.execute(
                update(Notification)
                .where(
                    Notification.id == notification.id,
                    Notification.read_at.is_(None),
                )
                .values(read_at=func.now())
            )
            await self.db.commit()
            await self.db.refresh(notification)
        return notification

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=func.now())
        )
        await self.db.commit()
        return result.rowcount
