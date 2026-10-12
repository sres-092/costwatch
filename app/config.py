import os
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

# os.environ[...] crashes at startup if a required value is missing (fail fast).
DATABASE_URL = os.environ["DATABASE_URL"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
ADMIN_API_KEY = os.environ["ADMIN_API_KEY"]

DEFAULT_MONTHLY_LIMIT_USD = Decimal(os.getenv("DEFAULT_MONTHLY_LIMIT_USD", "0.01"))

# LLM settings
LLM_MODE = os.getenv("LLM_MODE", "mock")            # "mock" or "gemini"
MOCK_COST_USD = Decimal("0.002")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "256"))
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

# List prices in USD per 1 million tokens. The free tier costs $0, but we
# meter at paid list prices so the budget reflects what production would cost.
PRICE_INPUT_PER_M = Decimal(os.getenv("PRICE_INPUT_PER_M", "0.30"))
PRICE_OUTPUT_PER_M = Decimal(os.getenv("PRICE_OUTPUT_PER_M", "2.50"))

if LLM_MODE == "gemini" and not GEMINI_API_KEY:
    raise RuntimeError("LLM_MODE=gemini needs GEMINI_API_KEY in .env")