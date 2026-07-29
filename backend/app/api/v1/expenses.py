import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_permission
from app.core.exceptions import ValidationError
from app.models.user import User
from app.schemas.expense import (
    ExpenseDetailResponse,
    ExpenseListResponse,
    ExpenseReject,
    ExpenseResponse,
)
from app.services.expense_service import ExpenseService

router = APIRouter(prefix="/expenses", tags=["expenses"])

ALLOWED_TYPES = {"travel", "office", "entertainment", "transport", "other"}
MAX_FILE_SIZE = 5 * 1024 * 1024
MAGIC = {
    "jpg": ("image/jpeg", b"\xff\xd8\xff"),
    "jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    "png": ("image/png", b"\x89PNG"),
    "pdf": ("application/pdf", b"%PDF"),
}


async def _read_files(
    files: list[UploadFile],
) -> list[tuple[str, str, bytes]]:
    if not 1 <= len(files) <= 5:
        raise ValidationError("附件数量须为 1~5 个")
    payloads = []
    for f in files:
        ext = (f.filename or "").rsplit(".", 1)[-1].lower()
        if ext not in MAGIC:
            raise ValidationError("附件仅支持 jpg/png/pdf")
        content = await f.read()
        if len(content) > MAX_FILE_SIZE:
            raise ValidationError("单个附件不能超过 5MB")
        content_type, magic = MAGIC[ext]
        if not content.startswith(magic):
            raise ValidationError("附件内容与扩展名不符")
        payloads.append((f.filename or f"file.{ext}", content_type, content))
    return payloads


@router.post("", response_model=ExpenseResponse, status_code=201)
async def create_expense(
    type: str = Form(...),
    amount: Decimal = Form(...),
    reason: str = Form(...),
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("expense:create")),
):
    if type not in ALLOWED_TYPES:
        raise ValidationError("报销类型非法")
    if amount <= 0:
        raise ValidationError("金额必须大于 0")
    if not (1 <= len(reason) <= 500):
        raise ValidationError("说明长度须为 1~500 字符")
    payloads = await _read_files(files)
    return await ExpenseService(db).create_expense(
        type, amount, reason, payloads, current_user
    )


@router.get("/mine", response_model=ExpenseListResponse)
async def list_mine(
    status: str | None = Query(None),
    type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("expense:list")),
):
    items, total = await ExpenseService(db).list_mine(
        current_user, status, type, page, page_size
    )
    return ExpenseListResponse(
        items=[ExpenseResponse.model_validate(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/todo", response_model=ExpenseListResponse)
async def list_todo(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await ExpenseService(db).list_todo(current_user, page, page_size)
    return ExpenseListResponse(
        items=[ExpenseResponse.model_validate(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=ExpenseListResponse)
async def list_all(
    department_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    type: str | None = Query(None),
    start_from: date | None = Query(None),
    end_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("expense:list_all")),
):
    items, total = await ExpenseService(db).list_all(
        department_id, status, type, start_from, end_to, page, page_size
    )
    return ExpenseListResponse(
        items=[ExpenseResponse.model_validate(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{expense_id}", response_model=ExpenseDetailResponse)
async def get_detail(
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("expense:list")),
):
    return await ExpenseService(db).get_detail(expense_id, current_user)


@router.get("/{expense_id}/attachments/{attachment_id}")
async def download_attachment(
    expense_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("expense:list")),
):
    att = await ExpenseService(db).get_attachment(
        expense_id, attachment_id, current_user
    )
    return FileResponse(
        Path(settings.UPLOAD_DIR) / att.stored_path,
        media_type=att.content_type,
        filename=att.filename,
    )


@router.post("/{expense_id}/cancel", response_model=ExpenseResponse)
async def cancel_expense(
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("expense:create")),
):
    return await ExpenseService(db).cancel_expense(expense_id, current_user)


@router.post("/{expense_id}/approve", response_model=ExpenseResponse)
async def approve_expense(
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ExpenseService(db).approve_expense(expense_id, current_user)


@router.post("/{expense_id}/reject", response_model=ExpenseResponse)
async def reject_expense(
    expense_id: uuid.UUID,
    data: ExpenseReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ExpenseService(db).reject_expense(
        expense_id, current_user, data.reason
    )
