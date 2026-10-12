"""All budget and ledger SQL lives here, so main.py never writes SQL itself."""
from decimal import Decimal
from .db import get_conn
from . import config


def ensure_budget(user_id: str, email: str) -> None:
    """Give a first-time user the default budget. Safe to call on every request."""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO budgets (user_id, email, monthly_limit_usd)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id, email, config.DEFAULT_MONTHLY_LIMIT_USD),
        )


def reserve(user_id: str, amount: Decimal) -> dict | None:
    """Atomically take `amount` out of the budget.

    The check and the deduction are ONE statement, so two concurrent requests
    can never both squeeze through the last bit of budget.
    Returns the new totals, or None if the budget can't cover it.
    """
    with get_conn() as conn:
        return conn.execute(
            """
            UPDATE budgets
            SET spent_usd = spent_usd + %s, updated_at = now()
            WHERE user_id = %s AND spent_usd + %s <= monthly_limit_usd
            RETURNING spent_usd, monthly_limit_usd
            """,
            (amount, user_id, amount),
        ).fetchone()


def record(user_id: str, model: str, status: str, prompt_tokens: int = 0,
           completion_tokens: int = 0, cost: Decimal = Decimal("0"),
           latency_ms: int | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO token_ledger
                (user_id, model, status, prompt_tokens, completion_tokens, cost_usd, latency_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, model, status, prompt_tokens, completion_tokens, cost, latency_ms),
        )


def summary(user_id: str) -> dict:
    with get_conn() as conn:
        budget = conn.execute(
            "SELECT monthly_limit_usd, spent_usd FROM budgets WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        recent = conn.execute(
            """
            SELECT model, status, prompt_tokens, completion_tokens, cost_usd, latency_ms, created_at
            FROM token_ledger
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (user_id,),
        ).fetchall()
    return {
        "monthly_limit_usd": budget["monthly_limit_usd"],
        "spent_usd": budget["spent_usd"],
        "remaining_usd": budget["monthly_limit_usd"] - budget["spent_usd"],
        "recent": recent,
    }


def set_limit(email: str, limit: Decimal) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            """
            UPDATE budgets
            SET monthly_limit_usd = %s, updated_at = now()
            WHERE email = %s
            RETURNING email, monthly_limit_usd, spent_usd
            """,
            (limit, email),
        ).fetchone()