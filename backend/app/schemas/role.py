from pydantic import BaseModel, ConfigDict


class PermissionBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    description: str | None
    permissions: list[PermissionBrief]
