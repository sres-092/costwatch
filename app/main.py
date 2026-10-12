from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from .auth import get_current_user, router as auth_router
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="CostWatch",
    description="LLM proxy that enforces per-user spending budgets",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(auth_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/me")
def me(user=Depends(get_current_user)):
    return {"user_id": user.id, "email": user.email}