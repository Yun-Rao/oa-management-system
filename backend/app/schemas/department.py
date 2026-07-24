import uuid

from pydantic import BaseModel, ConfigDict, Field


class DepartmentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: uuid.UUID | None = None


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: uuid.UUID | None = None


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None


class DepartmentNode(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    member_count: int
    children: list["DepartmentNode"] = []
