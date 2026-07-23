from fastapi import FastAPI

app = FastAPI(title="OA Management System")


@app.get("/health")
async def health():
    return {"status": "ok"}
