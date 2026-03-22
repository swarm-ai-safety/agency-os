# Agent System Patterns

Operational patterns for running multi-agent systems reliably, distilled from production experience and the [Everything Claude Code](https://github.com/affaan-m/everything-claude-code) ecosystem. Each pattern maps to specific agency-os mechanisms.

---

## 1. Context as a Scarce Resource

**Principle:** Treat the context window like a budget, not a buffer. Every tool, MCP integration, and ambient state imposes persistent cognitive load on the agent. The best agent is often the one carrying *less* state.

**Anti-pattern:** Adding more tools/MCPs to make agents "more capable." Each addition competes for context tokens and increases the chance of context-rot (the model forgetting earlier instructions as the window fills).

**Agency-OS implementation:**

- **Tool permissions use explicit allow/deny lists.** Each agent's `permissions.tools` list in the package YAML scopes what tools the agent can use. When `tools` is set, only listed tools are permitted; when omitted (`null`), all tools are allowed except those in `deny`. An agent that can `code_write` and `code_review` does *not* automatically get `deploy_production` — but package authors must explicitly populate `tools` to get this restriction. An empty list (`[]`) means *no* tools are allowed. See `agency_os/packages/schema.py` → `AgentRef.permissions` and `agency_os/agents/business_agent.py` → `is_tool_allowed()`.
- **Governance presets control ambient complexity.** The `conservative` preset enables RBAC and collusion detection; `aggressive` strips them. Choose the preset that matches the actual trust boundary, not the maximum feature set.
- **CLI-wrapped commands over always-on services.** The beads system (`bd ready`, `bd show`, `bd close`) is invoked on-demand rather than running as a persistent MCP, keeping agent context clean between operations.

**Guideline:** Before adding a tool to an agent's surface, ask: *what persistent cognitive load does this impose on the system?* If the tool is used less than once per session, wrap it as a CLI command instead.

---

## 2. Memory as Workflow Artifacts, Not Session State

**Principle:** Reliability comes from session compaction + durable artifacts + repeatable commands, not from longer context windows. The real unit of intelligence is the *workflow artifact chain*, not the model session.

**Anti-pattern:** Relying on a single long session to accumulate knowledge. Sessions degrade; artifacts persist.

**Agency-OS implementation:**

- **Agent memory is file-based and structured.** Each agent has a `memory/` directory with daily notes (`YYYY-MM-DD.md`) and a persistent knowledge graph (`life/areas/`). See `agents/ceo/memory/` for the pattern.
- **HEARTBEAT.md as session checkpoint.** Every agent heartbeat runs through an explicit checklist (identity → planning → assignments → delegation → fact extraction → exit), compressing decisions into durable notes.
- **SOUL.md as persistent identity.** Agent personality and decision heuristics survive across sessions without re-prompting. The CEO's strategic posture ("default to action, hold long view, protect focus, think in constraints") is loaded once, not restated.
- **Beads as append-only event log.** `issues.jsonl` and `interactions.jsonl` provide a durable, git-native record of all work. Session state compresses into issue status transitions.

**Guideline:** At the end of every session, the agent should produce artifacts that let the *next* session cold-start without context loss. If you can't reconstruct what happened from the artifacts alone, the memory system is incomplete.

---

## 3. Verification as Mechanical Property, Not Soft Instruction

**Principle:** Quality gates should be enforced by the environment, not by the model remembering to check. Action → enforced validation → only then trust output. Agents should not self-certify.

**Anti-pattern:** Relying on "please also run tests" in prompts. The model will eventually forget, especially under context pressure.

**Agency-OS implementation:**

- **Quality gates in workflow definitions.** Package YAML workflows define explicit gate conditions between stages:
  ```yaml
  quality_gates:
    implement_to_test:
      min_approvals: 1
    test_to_deploy:
      min_evidence_items: 3
      min_approvals: 2
  ```
  Work cannot advance without meeting the gate. See `agency_os/packages/schema.py` → `WorkflowDef`.

- **Governance audits are configured but not yet enforced at runtime.** The `audit_frequency` parameter is stored in governance profiles and can be overridden per-package, but the audit execution path is not yet wired into task routing or agent execution. The dashboard notes audit logs will appear "when the SWARM audit system is integrated." This is a planned control, not an active one today.
- **Circuit breakers halt bad actors.** `BusinessAgent.execute_task()` checks `is_frozen` before calling the LLM, and `Organization.submit_task()` excludes frozen agents from bidding. After N consecutive failures (default 3), the agent is frozen automatically. Note: the governance profile's `freeze_threshold_violations` is not yet wired to the per-agent threshold — the default of 3 is used unless callers pass `freeze_threshold` to `record_task_result()`.
- **Landing-the-plane checklist in AGENTS.md.** Session completion has a mandatory push-to-remote step. Work is not "done" until `git status` shows "up to date with origin."

**Guideline:** For any critical action, define a gate that runs *after* the action, automatically. If the gate fails, the output is not trusted. This turns quality from a soft instruction into a structural guarantee.

---

## 4. Narrow Roles with Explicit Handoff

**Principle:** Parallelization only works when roles are narrow and composable. Agents with overlapping authority and fuzzy responsibilities create coordination failures. The pattern is: narrow role → explicit handoff → reusable command surface → shared verification layer.

**Anti-pattern:** Creating several agents that all have broad, overlapping capabilities. This leads to duplicate work, conflicting decisions, and no clear accountability.

**Agency-OS implementation:**

- **Role specialization via agent refs.** Each agent in a package has a specific `ref` (e.g., `engineering/senior-developer`, `marketing/content-strategist`) and can have `role_override` to further narrow scope.
- **Sealed-bid task routing.** The `TaskRouter` collects bids from eligible agents, scores them by `bid_amount * reputation`, and assigns to the highest scorer. This is explicit handoff, not implicit coordination. See `agency_os/orchestration/task_router.py`.
- **Workflow pipelines define stage ownership.** Each stage in a workflow names specific agent roles:
  ```yaml
  stages:
    - plan: [project-manager-senior]
    - design: [backend-architect]
    - implement: [senior-developer, frontend-developer]
    - test: [evidence-collector]
    - deploy: [devops-automator]
  ```
  No stage has "everyone." Each agent knows when it's their turn.

- **Delegation guidelines enforce boundaries.** The ROSTER.md and per-agent AGENTS.md files define *when* to delegate and *to whom*. The rule: delegate outside your specialization, escalate to CEO when blocked, don't over-delegate tasks under 5 minutes in your own domain.

**Guideline:** If two agents can both plausibly do a task, the role definitions are too broad. Narrow until assignment is unambiguous.

---

## 5. Security as Architecture, Not Afterthought

**Principle:** In agent systems, every integration is a new attack surface. Prompt engineering and security engineering are converging. The architecture itself is part of the defense model.

**Threat model:** Malicious configuration files, transitive prompt injection via ingested docs, poisoned tool definitions, over-permissioned agents acting beyond intended scope.

**Agency-OS implementation:**

- **Permission allowlists and denylists per agent.** Tools are explicitly granted and can be explicitly denied:
  ```yaml
  permissions:
    tools: [code_write, code_review, git_commit, deploy_staging]
    deny: [deploy_production]
  ```
  An agent can never acquire a denied capability, regardless of prompt.

- **Multi-tenant isolation.** The `agency_os/tenancy/` module provides tenant-level secrets management and isolation boundaries. Agent A in org X cannot access org Y's state.
- **Circuit breaker enforcement.** `BusinessAgent.execute_task()` checks `is_frozen` before calling the LLM. After N consecutive failures (configurable via `CircuitBreakerConfig.threshold`), the agent is automatically frozen and refuses further execution. This is mechanical containment, not a prompt instruction.
- **Pre-execution tool permission check.** `execute_task()` validates `context.required_tool` against the agent's allow/deny lists *before* calling the LLM. Denied tools never reach the model.
- **Economic constraints as security.** Budget limits (`budget_limit_usd`) and wallet balances create a hard ceiling on agent activity. A compromised agent that exhausts its wallet is automatically contained.
- **Reputation decay penalizes bad behavior.** The governance engine tracks task success/failure and adjusts reputation scores. In `conservative` mode, reputation decays at 0.95 per epoch and staking with slashing (20% slash rate) creates economic disincentives for misbehavior.
- **Append-only audit logs.** Beads' `issues.jsonl` and `interactions.jsonl` are append-only, providing tamper-evident records of all agent actions.

**Guideline:** Design agent systems with the assumption that any input channel (configs, tools, docs, prompts) can be adversarial. Minimize channels, constrain tools, isolate execution, and watch behavior live. Security is a design constraint from day one, not a review step at the end.

---

## Summary: The Operating Model

These five patterns together form an operating model, not a prompt pack:

| Pattern | Core Question | Agency-OS Mechanism |
|---------|--------------|---------------------|
| Context budgeting | What cognitive load does this impose? | Tool allow/deny lists, on-demand CLI |
| Artifact memory | Can the next session cold-start from this? | HEARTBEAT.md, daily notes, beads |
| Mechanical verification | Does the environment enforce this? | Quality gates, circuit breakers, audits (planned) |
| Narrow roles | Is assignment unambiguous? | Agent refs, sealed-bid routing, pipelines |
| Security as architecture | Is this channel adversarial? | Denylists, tenancy, budgets, append-only logs |

**Reference:** Patterns informed by the [Everything Claude Code](https://github.com/affaan-m/everything-claude-code) project and adapted for SWARM-governed multi-agent organizations.
