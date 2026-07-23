from fastapi import FastAPI

from app.core.handlers import register_exception_handlers

app = FastAPI(title="OA Management System")
register_exception_handlers(app)


@app.get("/health")
async def health():
    return {"status": "ok"}
