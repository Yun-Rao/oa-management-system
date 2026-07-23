import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RoleBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)


class UserStatusUpdate(BaseModel):
    is_active: bool


class RoleAssignRequest(BaseModel):
    role_codes: list[str]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    is_active: bool
    roles: list[RoleBrief]


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    is_active: bool
    roles: list[RoleBrief]
    permissions: list[str]
