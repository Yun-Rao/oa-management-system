import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.models.user import User
from app.schemas.leave import (
    LeaveCreate,
    LeaveDetailResponse,
    LeaveListResponse,
    LeaveReject,
    LeaveResponse,
)
from app.services.leave_service import LeaveService

router = APIRouter(prefix="/leaves", tags=["leaves"])


def to_response(leave) -> LeaveResponse:
    return LeaveResponse.model_validate(leave)


@router.post("", response_model=LeaveResponse, status_code=201)
async def create_leave(
    data: LeaveCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("leave:create")),
):
    return await LeaveService(db).create_leave(data, current_user)


@router.get("/mine", response_model=LeaveListResponse)
async def list_mine(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("leave:list")),
):
    items, total = await LeaveService(db).list_mine(
        current_user, status, page, page_size
    )
    return LeaveListResponse(
        items=[to_response(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/todo", response_model=LeaveListResponse)
async def list_todo(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("leave:approve")),
):
    items, total = await LeaveService(db).list_todo(current_user, page, page_size)
    return LeaveListResponse(
        items=[to_response(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=LeaveListResponse)
async def list_all(
    department_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    type: str | None = Query(None),
    start_from: date | None = Query(None),
    end_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("leave:list_all")),
):
    items, total = await LeaveService(db).list_all(
        department_id, status, type, start_from, end_to, page, page_size
    )
    return LeaveListResponse(
        items=[to_response(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{leave_id}", response_model=LeaveDetailResponse)
async def get_detail(
    leave_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("leave:list")),
):
    return await LeaveService(db).get_detail(leave_id, current_user)


@router.post("/{leave_id}/cancel", response_model=LeaveResponse)
async def cancel_leave(
    leave_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("leave:create")),
):
    return await LeaveService(db).cancel_leave(leave_id, current_user)


@router.post("/{leave_id}/approve", response_model=LeaveResponse)
async def approve_leave(
    leave_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("leave:approve")),
):
    return await LeaveService(db).approve_leave(leave_id, current_user)


@router.post("/{leave_id}/reject", response_model=LeaveResponse)
async def reject_leave(
    leave_id: uuid.UUID,
    data: LeaveReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("leave:approve")),
):
    return await LeaveService(db).reject_leave(leave_id, current_user, data.reason)
