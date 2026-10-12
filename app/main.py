from fastapi import FastAPI

app = FastAPI(
    title="CostWatch",
    description="LLM proxy that enforces per-user spending budgets",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}