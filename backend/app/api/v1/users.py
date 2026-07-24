import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.models.user import User
from app.schemas.user import (
    RoleAssignRequest,
    UserCreate,
    UserListResponse,
    UserOrgUpdate,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user:create")),
):
    return await UserService(db).create_user(data)


@router.get("", response_model=UserListResponse)
async def list_users(
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user:list")),
):
    items, total = await UserService(db).list_users(keyword, page, page_size)
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user:update")),
):
    return await UserService(db).update_user(user_id, data)


@router.patch("/{user_id}/status", response_model=UserResponse)
async def set_status(
    user_id: uuid.UUID,
    data: UserStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user:disable")),
):
    return await UserService(db).set_status(user_id, data.is_active)


@router.put("/{user_id}/roles", response_model=UserResponse)
async def assign_roles(
    user_id: uuid.UUID,
    data: RoleAssignRequest,
    db: AsyncSession = Depends(get_db),
    operator: User = Depends(require_permission("role:assign")),
):
    return await UserService(db).assign_roles(user_id, data.role_codes, operator)


@router.patch("/{user_id}/org", response_model=UserResponse)
async def set_org(
    user_id: uuid.UUID,
    data: UserOrgUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user:update")),
):
    return await UserService(db).set_org(user_id, data)
