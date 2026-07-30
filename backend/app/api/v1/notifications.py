import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.notification import (
    NotificationListResponse,
    NotificationResponse,
    ReadAllResponse,
    UnreadCountResponse,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    is_read: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await NotificationService(db).list_mine(
        current_user, is_read, page, page_size
    )
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = await NotificationService(db).unread_count(current_user)
    return UnreadCountResponse(count=count)


@router.post("/read-all", response_model=ReadAllResponse)
async def read_all(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updated = await NotificationService(db).mark_all_read(current_user)
    return ReadAllResponse(updated=updated)


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def read_one(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await NotificationService(db).mark_read(notification_id, current_user)
