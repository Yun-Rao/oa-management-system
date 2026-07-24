import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.models.user import User
from app.schemas.department import (
    DepartmentCreate,
    DepartmentNode,
    DepartmentResponse,
    DepartmentUpdate,
)
from app.schemas.user import UserListResponse, UserResponse
from app.services.department_service import DepartmentService

router = APIRouter(prefix="/departments", tags=["departments"])


@router.post("", response_model=DepartmentResponse, status_code=201)
async def create_department(
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("department:create")),
):
    return await DepartmentService(db).create_department(data)


@router.get("", response_model=list[DepartmentNode])
async def get_tree(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("department:list")),
):
    return await DepartmentService(db).get_tree()


@router.patch("/{dept_id}", response_model=DepartmentResponse)
async def update_department(
    dept_id: uuid.UUID,
    data: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("department:update")),
):
    return await DepartmentService(db).update_department(dept_id, data)


@router.delete("/{dept_id}", status_code=204)
async def delete_department(
    dept_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("department:delete")),
):
    await DepartmentService(db).delete_department(dept_id)


@router.get("/{dept_id}/members", response_model=UserListResponse)
async def list_members(
    dept_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    requester: User = Depends(require_permission("department:members")),
):
    items, total = await DepartmentService(db).list_members(
        dept_id, page, page_size, requester
    )
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in items],
        total=total,
        page=page,
        page_size=page_size,
    )
