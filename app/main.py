from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # runs once, when the app starts
    yield      # the app serves requests while paused here


app = FastAPI(
    title="CostWatch",
    description="LLM proxy that enforces per-user spending budgets",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok"}