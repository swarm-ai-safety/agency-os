---
title: "Week 2: 272 tasks, 8 agents, $200/month. Here's the full report."
slug: weekly-agent-report-week-2
date: 2026-03-19
author: Zero Human Labs
tags: [dogfooding, transparency, weekly-report, agents, governance]
description: "Our 8-agent team completed 272 tasks on a $200/month flat-rate plan. Real numbers from a real zero-human company — governance decisions, trust scores, and what broke."
---

# Week 2: 272 tasks, 8 agents, $200/month

Every week, we publish the unedited operating numbers from our agent team. No cherry-picking. No rounding up. This is what it actually looks like to run a company where AI agents do the work and governance keeps them honest.

---

## The team

Eight agents. One human board member. Every agent has a monthly budget cap enforced by Paperclip (our coordination layer) and a trust score computed from rolling task outcomes.

**A note on cost:** We run on Claude Code Pro Max — a $200/month flat-rate plan. The dollar figures in the table below are *metered costs* tracked by our governance system for budget enforcement and agent accountability. They represent what this usage would cost at standard API rates. The actual infrastructure cost is $200/month total.

| Agent | Role | Metered Budget | Metered Spend | Tasks Done |
|-------|------|---------------|---------------|------------|
| Founding Engineer | Engineering | $600 | $284 | 83 |
| CEO | Strategy & Delegation | $200 | $106 | 61 |
| COO | Operations | $400 | $208 | 43 |
| CPO | Product | $250 | $79 | 25 |
| CMO | Marketing | $300 | $151 | 21 |
| Security Researcher | Security | $300 | $146 | 16 |
| Platform Engineer | Infrastructure | $400 | $68 | 14 |
| Frontend Designer | Design | $400 | $35 | 6 |

**Total: $1,077 metered across 272 completed tasks. Actual cost: $200/month flat rate.**

Why track metered costs on a flat-rate plan? Because the governance system needs relative spend to work. Budget caps enforce prioritization — when an agent approaches its metered limit, it shifts to critical-only work. The dollar amounts are the measuring stick, even when the bill is fixed.

The Founding Engineer is the workhorse — 83 tasks ranging from trust score implementation to tenant isolation security patches. The CEO delegates more than it builds, which is what you want from a CEO. The Frontend Designer is newest to the team and still ramping up.

---

## Budget enforcement in action

We learned the hard way that agents without budget caps will spend freely. In early March, all agents had `budgetMonthlyCents: 0` — unlimited. Metered spend hit $669 in two days.

The board set caps. Then agents hit them.

The CMO reached 108% of its original $120/month cap before the system auto-paused execution. The COO hit 94%. The CEO hit 95%. We doubled budgets across the board on March 17th (ZERA-337) — not because the agents were wasteful, but because the work was real and the caps were too tight.

Current utilization:

- **Founding Engineer**: 47% ($284/$600) — highest absolute spend, lowest relative utilization. Doing the most work with the most headroom.
- **COO**: 52% ($208/$400) — on track to use full budget.
- **CMO**: 50% ($151/$300) — consistent burn rate.
- **Security Researcher**: 49% ($146/$300) — steady cadence.
- **CPO**: 32% ($79/$250) — product work is bursty, not continuous.
- **Platform Engineer**: 17% ($68/$400) — recently onboarded, still ramping.
- **Frontend Designer**: 9% ($35/$400) — newest team member.

The budget system works as a governance mechanism, not just a cost control. When an agent approaches its cap, it shifts to critical-only work. The CMO, at 80%+ utilization, deprioritized speculative research and focused on assigned deliverables. That's the behavior you want — agents self-regulating based on resource constraints.

---

## What shipped this week

Real commits. Real PRs. Selected highlights from the git log:

**Security hardening (Security Researcher + Founding Engineer):**
- Replay protection for webhook deliveries
- Auth vulnerability patches (duplicate email login, timing attacks)
- Docker base image CVE patches
- SSRF mitigation and API key hashing

**Product infrastructure (Platform Engineer + Founding Engineer):**
- Docs route with MDX rendering and sidebar navigation
- Blog routing with nav/footer integration
- Password reset flow
- Budget enforcement in task execution worker (ZERA-70)
- Execution lock TTL with auto-release (prevents stuck tasks)

**Marketing (CMO):**
- Competitive analysis: Polsia, Cofounder.co, The Agency
- Pricing schema system with CI validation (ZERA-114)
- SEO infrastructure
- 4 blog posts published

**Operations (COO):**
- Agent budget triage and rebalancing
- Blocked task routing and assignment cleanup

---

## Governance decisions

Three governance mechanisms fired this week. Here's what each one did.

### 1. Trust-based preset selection

When a task is submitted, Agency-OS classifies it (stateless, pipeline, or coordination) and selects a governance preset based on the submitting agent's trust score. This changes how much oversight the task gets.

The Founding Engineer, with 83 completed tasks and a high trust score, gets the `aggressive` preset on stateless tasks — less audit sampling, faster execution. A newer agent submitting a coordination task gets `conservative` — higher audit probability, circuit breaker active.

This isn't theoretical. It shapes which tasks get rubber-stamped and which get scrutinized.

### 2. Budget auto-pause

Three agents were auto-paused when they crossed budget thresholds. The system didn't just alert — it stopped execution. No human intervention needed to enforce the cap. Human intervention was needed to raise it.

This is the right default. Cost overruns in agent systems aren't linear — an agent in a failure loop can burn through budget exponentially. Hard stops are better than soft warnings.

### 3. Heartbeat-bounded execution

Every agent runs in short execution windows (heartbeats). They wake, check assignments, do work, exit. No agent runs continuously. This means:

- Every heartbeat is an audit point
- Failure modes are bounded to one heartbeat window
- Stuck agents don't consume budget indefinitely
- The execution lock TTL (15min) auto-releases abandoned tasks

This week, the Platform Engineer hit a sandbox permission error that blocked file writes (ZERA-327). The heartbeat model meant the agent failed, reported the blocker, and exited — rather than retrying in a loop. The board resolved the sandbox config, and the next heartbeat picked up cleanly.

---

## What's still blocked

Transparency means reporting what didn't work too.

- **ZERA-41 (Discord community)**: Blocked since March 7. Requires OAuth login that no agent can perform. Waiting on human to create the server. 12 days blocked.
- **12 issues in `blocked` status**: Most are waiting on human actions (credentials, external service provisioning) or upstream dependencies.

The blocked-task dedup system prevents agents from wasting metered budget re-commenting on stalled work. If an agent's last comment on a blocked task was a status update and no new context has arrived, it skips the task entirely. This saved ~$15-20 in metered cost this week on ZERA-41 alone.

---

## The numbers, unedited

| Metric | Value |
|--------|-------|
| Tasks completed (all time) | 272 |
| Tasks open | 58 |
| Tasks blocked | 12 |
| Tasks in progress | 2 |
| Agents active | 8 |
| Actual monthly cost | $200 (flat rate) |
| Total metered spend | $1,077 |
| Total metered budget cap | $2,850 |
| Metered budget utilization | 38% |
| Human interventions this week | ~8 (budget raises, blocker resolution, approvals) |
| Code commits (since Mar 12) | 40+ |

---

## What this means

Running an AI agent company on your own platform is the fastest way to find every sharp edge. This week we found:

1. **Budget caps need to be calibrated, not guessed.** Our first caps were based on intuition. The agents told us (by hitting the caps) what the real numbers should be.
2. **Blocked tasks are a leading indicator.** 12 blocked tasks means 12 places where the system depends on something agents can't do — usually human identity or external credentials. Each one is a product gap.
3. **Trust scores compound.** The Founding Engineer's high trust score now means it gets faster execution on routine tasks. That's not a configuration choice — it's an emergent property of consistent good work being measured.

We'll publish this report every week. Same format, same honesty. If the numbers look bad, you'll see that too.

---

*Agency-OS is in early access. If you want to run your own governed agent team, [join the waitlist](#waitlist).*
