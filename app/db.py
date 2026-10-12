import psycopg
from psycopg.rows import dict_row
from . import config


def get_conn():
    return psycopg.connect(config.DATABASE_URL, row_factory=dict_row)


SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS budgets (
        user_id           TEXT PRIMARY KEY,
        email             TEXT NOT NULL,
        monthly_limit_usd NUMERIC(12, 6) NOT NULL CHECK (monthly_limit_usd >= 0),
        spent_usd         NUMERIC(12, 6) NOT NULL DEFAULT 0 CHECK (spent_usd >= 0),
        updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS token_ledger (
        id                BIGSERIAL PRIMARY KEY,
        user_id           TEXT NOT NULL REFERENCES budgets(user_id),
        model             TEXT NOT NULL,
        status            TEXT NOT NULL CHECK (status IN ('ok', 'blocked', 'upstream_error')),
        prompt_tokens     INT NOT NULL DEFAULT 0,
        completion_tokens INT NOT NULL DEFAULT 0,
        cost_usd          NUMERIC(12, 6) NOT NULL DEFAULT 0,
        latency_ms        INT,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ledger_user_time ON token_ledger (user_id, created_at DESC)",
]


def init_db():
    with get_conn() as conn:
        for statement in SCHEMA:
            conn.execute(statement)