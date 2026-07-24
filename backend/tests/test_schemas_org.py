import uuid

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas.department import DepartmentCreate, DepartmentNode, DepartmentUpdate
from app.schemas.user import UserOrgUpdate


def test_department_create_validates_name_length():
    with pytest.raises(PydanticValidationError):
        DepartmentCreate(name="")
    with pytest.raises(PydanticValidationError):
        DepartmentCreate(name="x" * 101)
    ok = DepartmentCreate(name="技术部", parent_id=None)
    assert ok.parent_id is None


def test_department_node_recursive():
    child = DepartmentNode(
        id=uuid.uuid4(), name="后端组", parent_id=None, member_count=3, children=[]
    )
    root = DepartmentNode(
        id=uuid.uuid4(),
        name="技术部",
        parent_id=None,
        member_count=10,
        children=[child],
    )
    assert root.children[0].name == "后端组"


def test_user_org_update_distinguishes_unset_and_null():
    empty = UserOrgUpdate()
    assert "department_id" not in empty.model_fields_set
    cleared = UserOrgUpdate(manager_id=None)
    assert "manager_id" in cleared.model_fields_set
