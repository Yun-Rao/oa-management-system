from fastapi import APIRouter, FastAPI

from app.api.v1 import auth, departments, leaves, notifications, roles, users
from app.core.handlers import register_exception_handlers

app = FastAPI(title="OA Management System")
register_exception_handlers(app)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(users.router)
api_v1.include_router(roles.router)
api_v1.include_router(departments.router)
api_v1.include_router(leaves.router)
api_v1.include_router(notifications.router)
app.include_router(api_v1)


@app.get("/health")
async def health():
    return {"status": "ok"}
