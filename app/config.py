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
LLM_MODE = os.getenv("LLM_MODE", "mock")
MOCK_COST_USD = Decimal("0.002")