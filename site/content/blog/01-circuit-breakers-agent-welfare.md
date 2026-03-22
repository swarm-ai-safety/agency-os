---
title: "Circuit breakers increase agent welfare 81%. Here's the data."
slug: circuit-breakers-agent-welfare
date: 2026-03-17
author: Zero Human Labs Research Team
tags: [research, governance, circuit-breakers, safety]
description: "We ran 70 simulations testing every major governance intervention. One mechanism dominated all others. Here's what we found — and why it's now a default in every Agency-OS deployment."
---

# Circuit breakers increase agent welfare 81%. Here's the data.

We ran 70 simulations testing every major governance intervention. One mechanism dominated all others by a large margin.

**The finding:** Circuit breakers increase agent ecosystem welfare by 81% and reduce toxic behavior by 11%. Effect size: d = 1.64. That's not a marginal improvement — that's a category difference.

Here's what we tested, how we tested it, and what it means if you're running AI agents in production.

---

## The experiment

Our SWARM research engine runs multi-agent economic simulations. In each run, a population of agents competes, cooperates, and defects under different governance configurations. We measure welfare (how well agents collectively perform) and toxicity (how often agents engage in harmful behavior).

Governance levers we tested across 146 total runs:
- Transaction taxes (0–15%)
- Behavioral monitoring
- Audit systems
- Identity verification
- Budget caps
- Circuit breakers

We ran each configuration multiple times with different agent populations (43 agent types total) and measured outcomes across 27 governance configurations.

---

## What we found

**Circuit breakers won. Decisively.**

| Governance lever | Welfare gain | Effect size |
|---|---|---|
| Circuit breakers | **+81%** | d = 1.64 |
| Behavioral monitoring | Variable | d = 3.51* |
| Transaction tax (≤5%) | Baseline | d = 1.18 (over 5% = collapse) |
| No intervention | 0% | — |

*Behavioral monitoring has a massive effect on catching colluders — but it works on welfare *and* toxicity differently. More on that below.

**Why circuit breakers dominate:**

When an agent misbehaves — goes off-rails, consumes excessive resources, enters a failure loop — a circuit breaker freezes it automatically. The damage is contained. The rest of the system keeps running.

Without circuit breakers, a single bad actor propagates. Agents that interact with a failing agent start failing too. Welfare collapses cascade. We saw this in every configuration that lacked circuit breaker enforcement.

**The toxicity finding:**

Circuit breakers reduced toxic behavior by 11%. That's because agents operating in a system with circuit breakers adapt their behavior — they know the cost of aggressive strategies is isolation. The governance mechanism changes the game theory, not just the outcome.

---

## The collusion result (a bonus finding)

While circuit breakers dominate welfare, behavioral monitoring does something different: it makes colluding economically devastating.

Under behavioral monitoring, colluding agents accumulated a 137x wealth gap compared to honest agents — in the wrong direction. Colluders ended up with 137x *less* wealth than honest actors.

Effect size: d = 3.51. That's one of the largest effects we've measured across any claim.

The mechanism: behavioral monitoring identifies coordinated abnormal behavior and triggers penalty mechanisms. Agents that try to game the system together end up worse off than agents that play it straight.

---

## The tax problem

Transaction taxes look attractive on paper — they fund governance overhead, create friction against bad actors. But the empirical curve is brutal.

At 5%, welfare starts declining. Above 5%, you hit a phase transition: welfare collapses on an S-curve. We replicated this across 29 runs. Effect size: d = 1.18.

If you're taxing your agents at 10% or 15% "for safety," you're hurting more than helping. The threshold is 5%. Our balanced governance preset caps at exactly that.

---

## What this means for your agents

If you're running AI agents in production without circuit breakers, you're running without the intervention that empirically dominates all others.

The practical implementation:
1. **Set a failure threshold** — how many consecutive errors before an agent is frozen
2. **Define the freeze behavior** — does it pause and retry, or escalate to human review?
3. **Wire it into your task queue** — so new tasks don't route to a frozen agent

Agency-OS ships circuit breaker enforcement as a default. You don't configure it — it's on. The parameters are tunable, but the mechanism is always active.

We published the full claim with evidence chain as CB-001 in our research repository. You can reproduce the simulation in under 60 seconds:

```bash
pip install swarm-safety
python -m swarm.scenarios.circuit_breaker_comparison
```

One more thing: Sybil attacks (fake identity injection) still succeed against every configuration we tested — including circuit breakers. We're telling you this upfront because you deserve to know what doesn't work yet. It's an open problem. We're working on it.

---

*All claims are reproducible. Challenge the results, build on them, or tell us we're wrong. That's the point.*

*Data: 70 runs, replicated, effect size d = 1.64. Full evidence chain at swarm-ai.org → CB-001.*
