import logging
import secrets
import time
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from . import billing, config, llm
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
logger = logging.getLogger("uvicorn.error")


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
    return {"status": "ok", "llm_mode": config.LLM_MODE}


@app.get("/v1/me")
def me(user=Depends(get_current_user)):
    return {"user_id": user.id, "email": user.email}


@app.post("/v1/chat/completions")
def chat(body: ChatRequest, user=Depends(get_tenant)):
    model = llm.model_name()
    reserved = llm.max_cost(body.prompt)

    # 1. Gate: reserve the WORST-CASE cost before calling the LLM.
    if billing.reserve(user.id, reserved) is None:
        billing.record(user.id, model, "blocked")
        raise HTTPException(status_code=429, detail="Monthly budget exceeded")

    # 2. Work: call the LLM. If it fails, give the money back.
    start = time.perf_counter()
    try:
        result = llm.complete(body.prompt)
    except llm.LLMError as e:
        logger.warning("LLM call failed for user %s: %s", user.id, e)
        latency_ms = int((time.perf_counter() - start) * 1000)
        billing.settle(user.id, reserved, Decimal("0"))
        billing.record(user.id, model, "upstream_error", latency_ms=latency_ms)
        raise HTTPException(status_code=502, detail="LLM provider failed. You were not charged.")
    latency_ms = int((time.perf_counter() - start) * 1000)

    # 3. Settle: swap the reservation for the real cost, then write the ledger.
    billing.settle(user.id, reserved, result.cost)
    billing.record(user.id, result.model, "ok", result.prompt_tokens,
                   result.completion_tokens, result.cost, latency_ms)

    return {
        "model": result.model,
        "reply": result.text,
        "usage": {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
        },
        "reserved_usd": reserved,
        "cost_usd": result.cost,
        "latency_ms": latency_ms,
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