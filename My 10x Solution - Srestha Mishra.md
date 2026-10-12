# My 10x Solution - Srestha Mishra

**Project:** CostWatch, an LLM proxy that enforces per-user spending budgets
**Repo:** https://github.com/sres-092/costwatch

---

## The problem

Teams that add LLM features usually hand out API access with no spending guardrails. One recursive agent loop, retry storm or abusive user can burn a month's allowance in minutes, and nobody finds out until the bill arrives. Ordinary reverse proxies don't understand tokens or per-user money, and checking usage logs afterwards is too late, because the money is already gone.

## Who it's for

Backend engineers and tech leads running LLM features for internal teams or multi-tenant SaaS users, who need each user's spending capped in real time.

## The 10x claim and how I measured it

**Without a gate, 50 runaway requests spend 10x the budget. With CostWatch, overspend is exactly $0.**

I wrote `scripts/race_test.py` to prove this rather than estimate it. It fires 50 requests at the same moment against a budget that covers only 5. Result: exactly 5 succeeded, 45 were blocked with `429`, and overspend was $0.000. Without the gate, all 50 would have gone through ($0.100 against a $0.010 budget).

The first run of this test actually failed. The budget was still exact (5 succeeded, overspend $0), but 7 requests came back with unexpected error codes. Every request was verifying its login token with Supabase over the network, 50 at once, so the most likely cause was Supabase rate-limiting those checks. I added a 60-second token cache and the test has passed cleanly since. The budget gate itself never leaked, even in the failing run.

The "10x" comes from the test setup (50 requests against a budget for 5). It isn't a fixed limit: the gate blocks a runaway loop of any size the same way, because every request has to win the same atomic check.

## Concepts used

| Concept | How it's used |
|---|---|
| API endpoints | Proxy endpoint, usage summary, admin budget endpoint (FastAPI) |
| Database | Postgres: `budgets` for running totals and `token_ledger` as the audit trail; exact `NUMERIC` money; constraints |
| Authentication | Supabase Bearer tokens with per-user isolation; separate admin key |
| LLM integration | Gemini with an output cap; real token counts priced and logged per call; refund on failure |
| Caching | 60-second thread-safe token cache that removed a real failure under load |
| Swap: rate limiting / quotas | The atomic budget gate: reserve, then call, then settle; `429` when exhausted |
| Swap: containerized stack | API + Postgres via Docker Compose, with a healthcheck |

## The hardest part

**Charging correctly when two requests arrive at the same moment, and when you don't know the cost in advance.**

1. **Race conditions.** Checking the balance and then deducting in two steps lets two requests both see "enough money" and both spend it. I put the check and the deduction in **one atomic SQL `UPDATE ... WHERE spent + cost <= limit`**, so Postgres's row lock makes the second request re-check against the new total.
2. **Unknown cost.** An LLM call's cost depends on how many tokens it writes, which you only learn afterwards. I **reserve the worst case** (estimated input plus the output cap), call the model, then **settle** the real cost and refund the rest. If the provider fails, the user is refunded in full and gets a `502`.

## What I'd do next

- Automatic monthly budget reset, done lazily inside the same atomic update
- A shared cache (Redis) so the token cache works across several API replicas
- Streaming responses, and per-model pricing tables

## How I used AI

I built this step by step with an AI assistant as a tutor: it explained each concept and proposed code, and I ran, tested and debugged everything myself, one stage and one commit at a time. Real problems I hit and fixed along the way:
- Docker volume paths
- A retired Gemini model, which I diagnosed by adding error logging
- A thinking model using up its output cap
- The Supabase rate limit under concurrent load

I can explain every file and every design decision in this repo.
