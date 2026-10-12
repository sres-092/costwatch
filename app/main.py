import secrets
import time
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from . import billing, config
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

admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class BudgetUpdate(BaseModel):
    email: str
    monthly_limit_usd: Decimal = Field(ge=0, max_digits=12, decimal_places=6)


def get_tenant(user=Depends(get_current_user)):
    """Authenticated user, guaranteed to have a budget row."""
    billing.ensure_budget(user.id, user.email)
    return user


def require_admin(key: str | None = Security(admin_key_header)):
    # compare_digest takes the same time whether the first or last char is wrong
    if not key or not secrets.compare_digest(key, config.ADMIN_API_KEY):
        raise HTTPException(status_code=403, detail="Admin key required")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/me")
def me(user=Depends(get_current_user)):
    return {"user_id": user.id, "email": user.email}


@app.post("/v1/chat/completions")
def chat(body: ChatRequest, user=Depends(get_tenant)):
    cost = config.MOCK_COST_USD
    model = "mock"

    # 1. Gate: take the money BEFORE doing the expensive work.
    if billing.reserve(user.id, cost) is None:
        billing.record(user.id, model, "blocked")
        raise HTTPException(status_code=429, detail="Monthly budget exceeded")

    # 2. Work (mock for now; the real Gemini call replaces this in Stage 4).
    start = time.perf_counter()
    reply = f"[mock] You said: {body.prompt[:80]}"
    latency_ms = int((time.perf_counter() - start) * 1000)
    prompt_tokens = max(1, len(body.prompt) // 4)   # rough: ~4 chars per token
    completion_tokens = max(1, len(reply) // 4)

    # 3. Ledger: permanent record of what happened.
    billing.record(user.id, model, "ok", prompt_tokens, completion_tokens, cost, latency_ms)

    return {
        "model": model,
        "reply": reply,
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        "cost_usd": cost,
    }


@app.get("/v1/usage/summary")
def usage_summary(user=Depends(get_tenant)):
    return billing.summary(user.id)


@app.put("/v1/budgets", dependencies=[Depends(require_admin)], tags=["admin"])
def set_budget(body: BudgetUpdate):
    row = billing.set_limit(body.email, body.monthly_limit_usd)
    if row is None:
        raise HTTPException(status_code=404, detail="No CostWatch user with that email yet")
    return row