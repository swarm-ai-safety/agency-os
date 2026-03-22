---
title: "From YAML to governed agent team in 60 seconds"
slug: yaml-to-governed-agent-team
date: 2026-03-18
author: Zero Human Labs Research Team
tags: [tutorial, governance, packages, yaml, agents]
description: "A single YAML file defines your entire agent team — roles, budgets, trust scores, circuit breakers, and audit trails. Here's the complete walkthrough from PackageSpec to production."
---

# From YAML to governed agent team in 60 seconds

Most agent frameworks make you wire up agents one at a time. Define a prompt. Add tools. Connect them to each other. Bolt on safety checks as an afterthought.

Agency-OS takes a different approach: you declare your entire team in a single YAML file. The platform handles the rest — instantiation, governance, trust scoring, budget enforcement, and audit trails. One file in, governed organization out.

Here's what that looks like.

---

## The PackageSpec

Every agent team starts as a PackageSpec — a declarative YAML file that defines who's on the team, what they can do, and how they're governed.

Here's a real one from our built-in library:

```yaml
apiVersion: agency-os/v1
kind: Package
metadata:
  name: saas-dev-studio
  display_name: "SaaS Development Studio"
  tier: professional
  tagline: "Full-stack SaaS development from architecture to deployment"

extends: _base

agents:
  - ref: engineering/senior-developer
    count: 1
    role_override:
      title: "Tech Lead"
    economic:
      initial_balance: 1000
      bid_strategy: quality_weighted
    permissions:
      tools: [code_write, code_review, git_commit, deploy_staging]
      deny: [deploy_production]
    domain_tags: [backend, api, database, python, architecture]

  - ref: engineering/frontend-developer
    economic:
      initial_balance: 800
      bid_strategy: quality_weighted
    permissions:
      tools: [code_write, code_review, ui_design]
    domain_tags: [frontend, react, css, ui, accessibility]

  - ref: testing/evidence-collector
    economic:
      initial_balance: 500
      bid_strategy: quality_weighted
    permissions:
      tools: [test_run, screenshot, code_review]
    domain_tags: [testing, qa, screenshot, regression]

governance:
  preset: balanced
  overrides:
    audit_frequency: 0.15
    circuit_breaker:
      enabled: true
      threshold: 3
    tax_rate: 0.05

workflows:
  - name: feature_development
    stages:
      - plan: [project-manager-senior]
      - design: [backend-architect]
      - implement: [senior-developer, frontend-developer]
      - test: [evidence-collector]
      - deploy: [devops-automator]
    quality_gates:
      implement_to_test:
        min_approvals: 1
      test_to_deploy:
        min_evidence_items: 3
        min_approvals: 2

deployment:
  llm_provider: anthropic
  model: claude-sonnet-4-20250514
  budget_limit_usd: 100.0
```

That's six agents, a five-stage workflow with quality gates, governance with circuit breakers and audit trails, and a $100 budget cap. All in one file.

---

## What `extends: _base` gives you

Every PackageSpec can inherit from a base template. The `_base` package ships sensible defaults:

```yaml
governance:
  preset: balanced
  overrides:
    audit_frequency: 0.1
    circuit_breaker:
      enabled: true
      threshold: 3
    tax_rate: 0.05

deployment:
  llm_provider: anthropic
  model: claude-sonnet-4-20250514
  budget_limit_usd: 100.0
```

Your package extends this. Override what you need; inherit the rest. The loader resolves the chain recursively (up to 10 levels deep) and deep-merges the result. You get governance defaults without thinking about them. When you do think about them, you override exactly the knobs you care about.

---

## What happens when you deploy

When you POST a PackageSpec to Agency-OS (or call `Organization.from_builtin("saas_dev_studio")`), the platform resolves it through a concrete pipeline:

**1. YAML → Pydantic validation.** The raw YAML is parsed, the `extends` chain is resolved, and the merged config is validated against typed Pydantic models. Invalid configs fail fast with clear errors — not at runtime, not in production.

**2. Agent instantiation.** Each `AgentRef` is resolved against the agent registry. The `ref` field (like `engineering/senior-developer`) maps to a full agent spec with personality, system prompt, success criteria, and tool definitions. The `AgentFactory` creates `BusinessAgent` instances with wallets, bidding strategies, and scoped permissions.

**3. Governance resolution.** The `governance.preset` field (e.g., `balanced`) loads a governance profile:

```yaml
# balanced.yaml
transaction_tax_rate: 0.05
audit_enabled: true
audit_probability: 0.10
circuit_breaker_enabled: true
freeze_threshold_violations: 3
freeze_duration_epochs: 2
bandwidth_cap: 10
```

Package-level overrides are applied on top. The result is a fully resolved `GovernanceConfig` that controls every agent's execution environment.

**4. Workflow engine.** Multi-stage pipelines are initialized with quality gates. Work can't move from `implement` to `test` without at least one approval. Can't move from `test` to `deploy` without three evidence items and two approvals. These aren't suggestions — they're enforced constraints.

**5. Organization is live.** The org accepts tasks via `submit_task()`. Each task triggers a sealed-bid auction where agents compete based on their economic config. The winner executes under the governance rules defined in the original YAML.

---

## Trust scores: governance that adapts

Static governance rules are necessary. They're not sufficient. An agent that's been reliable for 50 tasks deserves different oversight than one that failed 3 of its last 5.

Agency-OS computes rolling trust scores for every agent based on task outcomes:

- **Success** = 1.0 credit
- **Partial completion** = 0.5 credit
- **Failure** = 0.0 credit

The score is computed over a rolling window (default: 20 tasks) with anti-gaming protections — outcomes arriving faster than 5 seconds apart are discarded to prevent trust inflation via rapid fake-success flooding.

Trust maps to governance tiers:

| Score | Tier | Preset | What it means |
|-------|------|--------|---------------|
| ≥ 0.85 (20+ tasks) | High | Balanced* | Higher budgets, fewer audits, more parallel execution |
| ≥ 0.50 (10+ tasks) | Medium | Balanced | Standard oversight |
| < 0.50 | Low | Conservative | Frequent audits, lower budgets, escalation on exceptions |

*Note the asterisk: the `aggressive` preset is never assigned automatically. Even a high-trust agent caps at `balanced` via automated scoring. Aggressive requires explicit admin override. This prevents a compromised agent from gaming its way to zero oversight.

This is a deliberate design choice backed by 146 simulation runs in our SWARM research engine. The 3×3 governance matrix (task type × trust tier) was derived empirically, not assumed.

---

## Budget enforcement: agents have wallets

Every agent in a PackageSpec has an `economic` config:

```yaml
economic:
  initial_balance: 1000
  bid_strategy: quality_weighted
```

This isn't metadata — it's a real wallet. When agents bid on tasks, they spend from their balance. The `bid_strategy` determines how they compete:

- `default` — straightforward bid proportional to balance
- `quality_weighted` — bids higher on tasks matching domain expertise
- `specialization_bonus` — premium for domain-specific work
- `budget_conscious` — conservative bidding to preserve balance

A 5% transaction tax on every task completion flows back into the governance treasury. This isn't arbitrary — our research shows that a 5% tax rate optimally balances agent incentives with ecosystem stability.

When an agent's balance runs out, they can't bid. No balance, no work. Budget enforcement isn't a dashboard metric — it's a hard constraint in the execution loop.

---

## Circuit breakers: automatic shutdown

The `circuit_breaker` config in governance isn't optional safety theater. It's a hard stop:

```yaml
circuit_breaker:
  enabled: true
  threshold: 3
```

Three violations and the agent is frozen for 2 epochs. No manual intervention required. This single mechanism increased agent ecosystem welfare by 81% in our simulation testing (effect size d = 1.64). It's enabled by default in every governance profile because the data says it should be.

---

## Audit trails: every action is recorded

With `audit_probability: 0.15`, roughly 1 in 7 task executions gets a full audit. The metering collector records every token, every API call, every task outcome per agent. Percentile aggregation (p5/p50/p95) surfaces performance trends. Cost attribution tracks spending per agent per task.

This isn't logging for debugging. It's a compliance layer for production agent systems.

---

## The full picture

```
PackageSpec (YAML)
    │
    ├─ metadata      → org identity, tier, billing
    ├─ agents[]      → AgentFactory → BusinessAgent instances with wallets
    ├─ governance    → GovernanceConfig → trust scores, audits, circuit breakers
    ├─ workflows[]   → WorkflowEngine → staged pipelines with quality gates
    └─ deployment    → LLM config, budget caps
    │
    ▼
Organization.start()
    │
    ├─ Agents instantiated with economic configs
    ├─ Governance rules active
    ├─ Workflow pipelines initialized
    └─ Ready for submit_task() → sealed-bid auction → governed execution
```

One YAML file. A complete governed agent team. Trust scores, budget wallets, circuit breakers, audit trails, quality-gated workflows. All validated at parse time, all enforced at runtime.

---

## Try it

```bash
curl -X POST https://api.agencyos.dev/api/v1/organizations \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"package_name": "saas_dev_studio"}'
```

Or bring your own spec:

```bash
curl -X POST https://api.agencyos.dev/api/v1/organizations \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -F "package=@my-team.yaml"
```

From YAML to governed agent team. No assembly required.
