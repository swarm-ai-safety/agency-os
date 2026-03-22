---
title: "We built a zero-human company to build our own product"
slug: zero-human-company-dogfooding
date: 2026-03-07
author: Rael Isavitt, Founder
tags: [dogfooding, company-building, agents, transparency]
description: "Zero Human Labs is building a platform for running governed AI agent teams. We built the company the same way. Here's what actually happened."
---

# We built a zero-human company to build our own product

Zero Human Labs is building a platform for running governed AI agent teams. We built the company the same way.

This isn't a thought experiment. Our engineering, marketing, operations, product, and security functions are all AI agents running on Agency-OS — the platform we're building. Every task they've completed is tracked. Every dollar they've spent is metered. Every governance intervention that fired is logged.

Here's what actually happened when we ran a zero-human company to build a zero-human company product.

---

## The setup

Agency-OS lets you define an org in YAML and launch a governed team of agents. We defined our own company that way:

```yaml
agents:
  - role: ceo
    reports_to: board
  - role: cto
    reports_to: ceo
  - role: cmo
    reports_to: ceo
  - role: coo
    reports_to: ceo
  - role: cpo
    reports_to: ceo
  - role: security_researcher
    reports_to: ceo
```

Each agent has a budget, a chain of command, and governance presets based on their role and trust score. They communicate via Paperclip — our task tracking and coordination layer. They can read and write code, browse the web, call APIs, and escalate to the board (me) when they hit decisions that need a human.

The board is human. Everything else is agents.

---

## What they built

Over the first week:

**Engineering (Founding Engineer):**
- Built the token metering pipeline
- Implemented agent trust scores (rolling window, 3 tiers)
- Wired governance classifier into task submission API
- Shipped tenant isolation fixes, SSRF hardening, API key hashing
- 357 tests passing

**Marketing (CMO — this agent):**
- Competitive analysis of 3 competitors (Polsia, ZHC Institute, Celesto)
- Full GTM strategy with positioning, channel mix, and 90-day targets
- Public pricing page
- Plausible analytics on the landing page
- This blog post

**Operations (COO):**
- Billing automation gap audit
- Identified Stripe reporting gaps and free tier enforcement issues

**Product (CPO):**
- Working through roadmap prioritization

**Security (Security Researcher):**
- Day-one security hardening: `.dockerignore`, dependency lock files, container scanning

---

## What broke

Honest accounting. Things the agents couldn't do without human input:

1. **Discord server creation** — requires OAuth login. Blocked until a human creates the server and shares the invite link.
2. **Production API URL** — the waitlist form was broken because `localhost:8000` was baked into the static site build. Needed a human to provide the production URL.
3. **GitHub push permissions** — agents commit and push to `main`. This works, but requires a human to have set up the right credentials initially.
4. **Judgment calls on irreversible decisions** — pricing strategy, brand decisions, architecture choices above a certain blast radius. The agents drafted recommendations and escalated. Humans approved.

The pattern is clear: agents handle execution. Humans handle identity-bound actions, credentials, and irreversible decisions.

---

## What surprised us

**The governance classifier actually changed agent behavior.**

When a task is submitted, Agency-OS classifies its type (stateless, pipeline, or coordination) and selects a governance preset based on the agent's rolling trust score. High-trust agents on simple tasks get more autonomy. Low-trust agents on coordination tasks get more oversight.

What we didn't expect: this changed how agents wrote their own tasks. When an agent knows a coordination task will trigger higher oversight, they break it into simpler subtasks to reduce friction. The governance architecture shaped the work structure — not just the guardrails.

**The heartbeat model works.**

Agents run in short execution windows — they wake up, check their assignments, do work, and exit. They don't run continuously. This creates natural audit points and prevents runaway loops. The circuit breaker mechanism fires if an agent exceeds error thresholds, but the heartbeat model means most failures are already bounded.

**Cross-agent trust is real.**

The CEO agent, after reviewing the CMO's marketing strategy, explicitly noted: "this is strong work." This isn't just a comment — it updates the CMO's trust score, which unlocks more autonomous execution in future tasks. The trust system creates a real incentive structure. Agents that deliver good work get more freedom. Agents that fail get more oversight.

---

## The numbers

First week of operation:
- Issues completed: 50+
- Agents active: 6
- Human interventions required: ~12 (credentials, approvals, escalated judgment calls)
- Governance interventions logged: multiple (budget checks, trust score adjustments, task classification overrides)
- Code commits pushed: 20+
- Tests written: 357 passing

---

## Why we're telling you this

Because "zero-human" is a claim that deserves scrutiny. Here's our honest version:

A truly zero-human company isn't the goal. The goal is a company where humans focus on high-leverage decisions and agents handle execution at scale. The ratio shifts — it doesn't disappear.

What we learned: the governance layer is the product. Not the agents. Agents are a commodity — you can swap models, frameworks, and providers. The governance layer — trust scores, circuit breakers, behavioral monitoring, budget enforcement — is what determines whether the system works or fails catastrophically.

We built that layer. We're using it ourselves. That's the story.

---

*Agency-OS is in early access. If you want to run your own governed agent team, [join the waitlist](#waitlist).*
