"""Race test: fire many requests at the SAME moment at a small budget.

Proves the atomic budget gate: exactly the affordable number of requests
succeed, the rest get 429, and spending never goes over the limit.

Run inside the API container (mock mode only):
    docker compose exec api python scripts/race_test.py --email you@x.com --password ...
"""
import argparse
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import httpx

COST_PER_CALL = Decimal("0.002")   # mock mode's fixed cost


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--requests", type=int, default=50, help="how many to fire at once")
    parser.add_argument("--affordable", type=int, default=5, help="how many the budget should allow")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    admin_key = os.environ["ADMIN_API_KEY"]
    client = httpx.Client(base_url=args.base_url, timeout=30)

    # 0. Safety: never hammer the real LLM (free tier would rate-limit us).
    mode = client.get("/health").json().get("llm_mode")
    if mode != "mock":
        raise SystemExit(f"Refusing to run: LLM_MODE is '{mode}'. Set LLM_MODE=mock in .env first.")

    # 1. Log in as the test user.
    login = client.post("/auth/login", json={"email": args.email, "password": args.password})
    login.raise_for_status()
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # 2. Set the budget so EXACTLY `affordable` more calls fit.
    before = client.get("/v1/usage/summary", headers=auth).json()
    spent_before = Decimal(str(before["spent_usd"]))
    limit = spent_before + COST_PER_CALL * args.affordable
    r = client.put("/v1/budgets", headers={"X-Admin-Key": admin_key},
                   json={"email": args.email, "monthly_limit_usd": str(limit)})
    r.raise_for_status()

    # 3. Fire all requests at the same moment.
    def one_call(i):
        return client.post("/v1/chat/completions", headers=auth,
                           json={"prompt": f"race test {i}"}).status_code

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.requests) as pool:
        codes = list(pool.map(one_call, range(args.requests)))
    elapsed = time.perf_counter() - start

    # 4. Check the result.
    after = client.get("/v1/usage/summary", headers=auth).json()
    spent_after = Decimal(str(after["spent_usd"]))
    ok = codes.count(200)
    blocked = codes.count(429)
    other = len(codes) - ok - blocked
    charged = spent_after - spent_before
    overspend = max(Decimal("0"), spent_after - limit)
    without_gate = COST_PER_CALL * args.requests

    print()
    print("=== CostWatch race test ===")
    print(f"Requests fired at once : {args.requests}")
    print(f"Budget allows          : {args.affordable} calls (${COST_PER_CALL * args.affordable})")
    print(f"Succeeded (200)        : {ok}")
    print(f"Blocked   (429)        : {blocked}")
    print(f"Other status codes     : {other}")
    print(f"Status breakdown       : {dict(Counter(codes))}")
    print(f"Charged this run       : ${charged}")
    print(f"Overspend              : ${overspend}")
    print(f"Without a gate         : ${without_gate} ({args.requests // args.affordable}x the budget)")
    print(f"Wall time              : {elapsed:.2f}s")
    passed = ok == args.affordable and blocked == args.requests - args.affordable and overspend == 0
    print("RESULT                 :", "PASS" if passed else "FAIL")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()