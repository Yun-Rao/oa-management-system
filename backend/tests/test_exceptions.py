import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from app.core.handlers import register_exception_handlers


def make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/not-found")
    async def _nf():
        raise NotFoundError("用户不存在")

    @app.get("/unauthorized")
    async def _ua():
        raise UnauthorizedError("未登录")

    @app.get("/conflict")
    async def _cf():
        raise ConflictError("邮箱已被使用")

    return app


@pytest.mark.asyncio
async def test_error_response_format():
    async with AsyncClient(
        transport=ASGITransport(app=make_app()), base_url="http://test"
    ) as c:
        resp = await c.get("/not-found")
        assert resp.status_code == 404
        assert resp.json() == {"error": {"code": "NOT_FOUND", "message": "用户不存在"}}

        resp = await c.get("/unauthorized")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"

        resp = await c.get("/conflict")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"
