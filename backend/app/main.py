from fastapi import APIRouter, FastAPI

from app.api.v1 import auth
from app.core.handlers import register_exception_handlers

app = FastAPI(title="OA Management System")
register_exception_handlers(app)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
app.include_router(api_v1)


@app.get("/health")
async def health():
    return {"status": "ok"}
