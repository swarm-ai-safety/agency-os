# Agentic Engineer — Playbook

> **Package**: `agentic-engineer` | **Agents**: 10 (1 planner, 1 researcher, 2 senior eng, 1 frontend, 1 backend architect, 1 devops, 1 verifier, 1 QA) | **Key insight**: Planning is the bottleneck, not code generation.

---

## Objective

Take a natural-language project description and autonomously ship production-ready code — task by task, branch by branch, PR by PR — with structured planning, isolated sandbox execution, and multi-layer verification.

## Pre-Conditions

- [ ] Package launched: `agency-os run agentic-engineer`
- [ ] LLM provider configured (Anthropic recommended)
- [ ] Git repo initialized for the target project

---

## Architecture

```
User: "Build a project management tool"
    │
    ▼
┌─────────────────────────────────┐
│  ARCHITECTURE RESEARCHER        │  ← Researches patterns, market, tech
│  Technical landscape analysis   │
└──────────┬──────────────────────┘
           │ research_report
           ▼
┌─────────────────────────────────┐
│  PROJECT PLANNER                │  ← The brain: decomposes into plan
│  Architecture → Milestones →    │
│  Tasks → DAG → Execution Order  │
└──────────┬──────────────────────┘
           │ ProjectPlan (structured YAML)
           ▼
┌─────────────────────────────────┐
│  TASK DAG SCHEDULER             │  ← Topological sort, parallel waves
│  Critical path analysis         │
│  Ready-task detection           │
└──────────┬──────────────────────┘
           │ ready tasks (parallel where possible)
           ▼
┌─────────────────────────────────┐
│  EXECUTION AGENTS               │  ← Bid-based assignment
│  Senior Dev × 2                 │
│  Frontend Dev × 1               │
│  Backend Architect × 1          │
│  DevOps × 1                     │
└──────────┬──────────────────────┘
           │ task output (code, config, etc.)
           ▼
┌─────────────────────────────────┐
│  TASK SANDBOX                   │  ← Isolated per-task environment
│  • Filesystem isolation         │
│  • Network control              │
│  • Resource limits              │
└──────────┬──────────────────────┘
           │ sandbox output
           ▼
┌─────────────────────────────────┐
│  VERIFICATION LAYER             │
│  Task Verifier: lint + type +   │
│    acceptance criteria          │
│  QA Engineer: integration +     │
│    visual verification          │
└──────────┬──────────────────────┘
           │ pass / fail / retry
           ▼
    ┌──────┴──────┐
    │ PASS        │ FAIL → retry (max 1) → mark failed → block milestone
    │ Next task   │
    └─────────────┘
```

---

## The Planning Layer (What Makes This Different)

### Why planning first?

Every AI coding tool can generate code. They all fall apart when projects get real because they skip planning. The planning layer produces:

1. **Architecture graph** — components, connections, data flows
2. **Tech stack** — specific technologies with rationale
3. **Milestones** — shippable increments with acceptance criteria
4. **Task DAG** — atomic tasks with dependencies, agent assignments, effort estimates
5. **Execution order** — topologically sorted, critical path identified

### ProjectDecomposer

Two modes:
- **Template-based** (no LLM needed): `web_app`, `api_service`, `cli_tool` — instant plans
- **LLM-powered**: Planner agent generates structured YAML plan from description

### TaskDAG

Every plan is validated as a DAG:
- **Cycle detection** — invalid plans are caught before execution
- **Topological sort** — correct execution order
- **Critical path** — identifies the longest dependency chain
- **Parallel waves** — groups tasks that can run concurrently

---

## Workflow: `project_execution` (Full)

### Stage 1: Research
**Agent**: Architecture Researcher

Produces:
- Similar products analysis
- Recommended architecture patterns
- Technology options per layer (2-3 alternatives each)
- Risk assessment

**Quality gate** → plan: min 1 evidence item

### Stage 2: Plan
**Agent**: Project Planner

Produces:
- Complete ProjectPlan (architecture + milestones + tasks)
- Validated DAG with execution order
- Effort estimate and critical path

**Quality gate** → implement: min 1 approval + 1 evidence item

### Stage 3: Implement
**Agents**: Senior Dev × 2, Frontend Dev, Backend Architect

For each ready task in the DAG:
1. Task routed to best agent via bid auction
2. Agent receives task description + acceptance criteria + context
3. Agent produces code/config output
4. Output placed in isolated sandbox

**Quality gate** → verify: min 1 approval

### Stage 4: Verify
**Agents**: Task Verifier, QA Engineer

For each completed task:
1. **Static analysis**: `ruff check`, `mypy` (configurable)
2. **Acceptance criteria**: Check each criterion against output
3. **Integration**: Existing tests still pass?
4. **Visual** (if frontend): Headless browser screenshot

Verdict: PASS / FAIL / PARTIAL
- PASS → task marked complete
- FAIL → retry once, then mark failed (blocks milestone)
- PARTIAL → pass with warnings

**Quality gate** → deploy: min 3 evidence items + 2 approvals

### Stage 5: Deploy
**Agent**: DevOps Engineer

- Deploy to staging
- Run smoke tests
- Deploy to production (requires governance approval)

---

## Workflow: `quick_build` (Fast)

Skips research stage. Uses template-based planning.

```
plan → implement → verify
```

Good for:
- Well-understood project types
- Prototypes and MVPs
- When speed matters more than optimal architecture

---

## Sandbox Execution

Every task runs in isolation:

| Property | Default | Configurable |
|----------|---------|-------------|
| Filesystem | Isolated temp dir | Yes (project_dir copy) |
| Network | Disabled | Per-task (sandbox.needs_network) |
| Browser | Disabled | Per-task (sandbox.needs_browser) |
| Timeout | 300s | Per-task |
| Memory | 512MB | Per-task |

### What gets verified in the sandbox:
```bash
ruff check . --quiet || true    # Linting
mypy . --ignore-missing-imports --quiet || true  # Type checking
```

Custom commands can be added per-package.

---

## Quick Start

```bash
# Launch the agentic engineer
agency-os run agentic-engineer

# Plan a project (template mode, no LLM needed)
python -c "
from agency_os.planning import ProjectDecomposer
plan = ProjectDecomposer().from_template('web_app', 'TaskFlow', 'A project management tool with kanban boards')
import json; print(json.dumps(plan.to_dict(), indent=2))
"

# Full autonomous execution
agency-os run-task -p agentic-engineer -t 'Build a REST API for a todo app with user auth'

# Or via Python
from agency_os.orchestration.organization import Organization
org = Organization.from_builtin('agentic-engineer')
org.start()
plan = org.plan_project('Build a Slack bot that summarizes daily standups')
report = org.execute_plan(plan, dry_run=True)  # dry_run=False for real execution
print(report.to_dict())
```

---

## How This Maps to pre.dev's Architecture

| pre.dev concept | agency-os implementation |
|---|---|
| Natural language input | `org.plan_project(description)` |
| Research + market context | Architecture Researcher agent |
| Architecture graph | `ProjectPlan.architecture` + `data_flows` |
| Tech stack recommendation | `ProjectPlan.tech_stack` |
| Milestones + user stories | `ProjectPlan.milestones` + `TaskSpec` |
| Task-by-task execution | `PlanExecutor.run()` with DAG scheduling |
| Isolated sandboxes | `TaskSandbox` per task |
| Lint + typecheck + visual verify | Task Verifier agent + sandbox commands |
| PR-by-PR shipping | Execution events + git integration |

### What we add beyond pre.dev:
- **Agent competition** (bid-based task routing)
- **Governance layer** (audit, circuit breakers, budget enforcement)
- **SWARM telemetry** (distributional metrics across agent population)
- **Template fallback** (plan without LLM for known patterns)
- **Pluggable verification** (custom sandbox commands per package)

---

## Telemetry & Observability

The PlanExecutor produces an `ExecutionReport` with:
- Task-by-task pass/fail breakdown
- Milestone completion status
- Total tokens used
- Event timeline (task_started, task_completed, task_failed, milestone_completed)
- Duration per task

Combined with existing agency-os telemetry:
- Agent reputation tracking
- Budget spend per task
- Governance audit trail
- Circuit breaker events

---

## Evolution Path

### v1 (current): Planning + execution + verification
Template-based and LLM-powered planning with sandbox execution.

### v2: Replanning on failure
When tasks fail, planner re-examines the plan and adjusts:
- Split failed tasks into smaller pieces
- Reassign to different agent roles
- Update dependency graph

### v3: Learning from execution
Track which plans succeed and fail:
- Build estimation models from actual outcomes
- Optimize template defaults based on data
- Adapt agent role assignments based on track records

### v4: Continuous project execution
Run indefinitely:
- Ingest user feedback as new requirements
- Generate delta plans (what changed)
- Execute incremental updates
- Monitor production and self-heal
