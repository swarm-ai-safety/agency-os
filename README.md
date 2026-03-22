# Agency-OS

The governed agent operating system for solo founders and small teams — spin up an autonomous AI workforce that can't run wild, from a single YAML file.

Agency-OS is a governance-first agent platform. Every agent holds a wallet, competes for tasks through sealed-bid auctions, and operates under safety rails calibrated from 146 simulation runs. Circuit breakers stop runaway loops, per-agent budgets enforce hard ceilings, and reputation scores automatically demote underperformers. You get a full AI organization — without babysitting it.

---

## Quickstart

### Install

```bash
# Core + CLI only
pip install agency-os

# Core + REST API server
pip install "agency-os[api]"

# Everything (dev tools, LLM clients, dashboard, metering)
pip install "agency-os[all]"
```

### List built-in packages

```bash
agency-os list-packages
```

### Inspect a package without launching it

```bash
agency-os status saas-dev-studio
```

### Launch an organization and submit a task

```bash
# Launch from a built-in package
agency-os run saas-dev-studio

# Launch and immediately submit a task
agency-os run saas-dev-studio --task "Implement OAuth2 login for the API"

# Launch from a custom YAML file
agency-os run ./my-team.yaml --task "Write integration tests for the billing module"

# Start the REST API server
agency-os serve --host 0.0.0.0 --port 8000
```

### Deployment docs

- [Production deployment guide](docs/deployment.md)
- [Backend systemd runbook](deploy/PRODUCTION_BACKEND.md)
- [Database migration runbook](docs/database-migrations.md)

---

## Architecture

Agency-OS is organized in layers. A **Package** declares which agents to hire, their economic configuration, the governance preset, and named workflows. At runtime the **Agent Factory** instantiates `BusinessAgent` objects from SWARM agent specs. The **Organization** holds the roster and wires it to the **Task Router**, which runs a sealed-bid auction so the most qualified agent wins each task. Orthogonal to the task flow, the **Governance** layer enforces audits, circuit breakers, and transaction taxes using one of three preset profiles. The **Economics** layer manages per-agent wallets, reputation scores, and budget limits.

```
                         +------------------+
                         |    Package YAML  |
                         +--------+---------+
                                  |
                         +--------v---------+
                         |  Agent Factory   |
                         +--------+---------+
                                  |
          +-----------+  +--------v---------+  +-----------+
          | Governance|  |   Organization   |  | Economics |
          | (presets) +->+  (agent roster)  +<-+ (wallets) |
          +-----------+  +--------+---------+  +-----------+
                                  |
                         +--------v---------+
                         |   Task Router    |
                         |  (bid auction)   |
                         +--------+---------+
                                  |
               +------------------+------------------+
               |                  |                  |
        +------v------+   +-------v-----+   +--------v----+
        |   Agent A   |   |   Agent B   |   |   Agent C   |
        | (Tech Lead) |   | (Architect) |   | (DevOps)    |
        +-------------+   +-------------+   +-------------+
```

**Request flow:**

1. A task description arrives via CLI or `POST /api/v1/orgs/{org_id}/tasks`.
2. The Task Router broadcasts the task to all agents in the organization.
3. Each agent submits a bid according to its configured bid strategy (quality-weighted, specialization bonus, budget-conscious, or default).
4. The highest valid bid wins. The winning agent executes the task.
5. On completion, the governance layer may trigger an audit; repeated violations trip the circuit breaker and freeze the agent.

---

## Built-in Packages

| Name | Display Name | Agents | Governance Preset | Budget (USD) |
|---|---|---|---|---|
| `saas-dev-studio` | SaaS Development Studio | 6 | balanced (overrides) | $100.00 |
| `marketing-agency` | Marketing Agency | 6 | balanced (overrides) | $75.00 |
| `product-squad` | Product Squad | 5 | balanced (overrides) | $80.00 |
| `devops-team` | DevOps Team | 4 | conservative (overrides) | $50.00 |

---

## Package YAML Format

Packages are standard YAML files that follow the `agency-os/v1` schema. Any field under `governance.overrides` or `deployment` can be omitted to inherit the preset defaults.

```yaml
apiVersion: agency-os/v1
kind: Package

metadata:
  name: saas-dev-studio          # Machine-readable identifier (used by CLI and API)
  display_name: "SaaS Development Studio"
  tier: professional             # free | starter | professional | enterprise

extends: _base                   # Inherit defaults from the _base package

agents:
  - ref: engineering/senior-developer   # Path into the SWARM agent spec library
    count: 1                            # Spawn N copies of this agent (default: 1)
    role_override:
      title: "Tech Lead"               # Override the display title at runtime
    economic:
      initial_balance: 1000            # Starting wallet balance (internal units)
      bid_strategy: quality_weighted   # default | quality_weighted |
                                       # specialization_bonus | budget_conscious
    permissions:
      tools: [code_write, code_review, git_commit, deploy_staging]
      deny: [deploy_production]        # Explicitly revoke tools even if the spec grants them

  - ref: engineering/devops-automator
    economic:
      initial_balance: 600
      bid_strategy: budget_conscious
    permissions:
      tools: [deploy_staging, deploy_production, infrastructure, monitoring]

governance:
  preset: balanced               # conservative | balanced | aggressive
  overrides:                     # Any field here overrides the preset value
    tax_rate: 0.05               # Fraction of each transaction sent to the commons pool
    audit_frequency: 0.15        # Probability of a post-task audit (0.0 – 1.0)
    circuit_breaker:
      enabled: true
      threshold: 3               # Violations before the agent is frozen

workflows:
  - name: feature_development
    pipeline: nexus_full         # SWARM pipeline type
    stages:
      - plan:      [project-manager-senior]
      - design:    [backend-architect]
      - implement: [senior-developer, frontend-developer]
      - test:      [evidence-collector]
      - deploy:    [devops-automator]
    quality_gates:               # Stage transition requirements
      implement_to_test:
        min_approvals: 1
      test_to_deploy:
        min_evidence_items: 3    # Minimum logged evidence artifacts
        min_approvals: 2

deployment:
  llm_provider: anthropic
  model: claude-sonnet-4-20250514
  budget_limit_usd: 100.0        # Hard ceiling on total LLM spend for this org
```

---

## Governance Presets

Three profiles are shipped in `agency_os/governance/profiles/`. A package selects one via `governance.preset` and may override individual fields under `governance.overrides`.

| Setting | conservative | balanced | aggressive |
|---|---|---|---|
| **Tax rate** | 10% | 5% | 2% |
| **Audit enabled** | yes | yes | no |
| **Audit probability** | 25% | 10% | 5% |
| **Audit penalty multiplier** | 3x | 2x | 1x |
| **Circuit breaker** | enabled | enabled | enabled |
| **Freeze threshold (violations)** | 2 | 3 | 5 |
| **Freeze duration (epochs)** | 3 | 2 | 1 |
| **Bandwidth cap (tasks/epoch)** | 5 | 10 | 20 |
| **Staking required** | yes (min 50) | no | no |
| **Stake slash rate** | 20% | — | — |
| **Collusion detection** | enabled | disabled | disabled |
| **RBAC enforced** | yes | no | no |
| **Reputation decay** | 0.95/epoch | 0.98/epoch | none |

**conservative** — High oversight, required staking, tight circuit breakers. Suitable for production deployments handling sensitive operations.

**balanced** — Default middle ground. Moderate auditing and circuit breakers with no staking requirement. Used by most built-in packages.

**aggressive** — Minimal oversight, high bandwidth, fast iteration. Suitable for rapid prototyping or sandboxed experiments.

---

## API Endpoints

Start the server with `agency-os serve` or `uvicorn agency_os.service.api.app:app`.

- **Interactive OpenAPI docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Full API reference:** [docs/api-reference.md](docs/api-reference.md) — error codes, rate limits, Python/JS examples

All `/api/v1/*` routes require a valid API key in the `X-API-Key` header. Sign up via `POST /api/v1/tenants` to get your key.

**Rate limits:** 60 requests/minute per tenant. Free tier: 10,000 tokens/month, 1 agent.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check — returns `{"status": "ok"}` |
| `POST` | `/api/v1/tenants` | Sign up — returns tenant ID and API key |
| `GET` | `/api/v1/tenants/me` | Get current tenant info |
| `POST` | `/api/v1/orgs` | Launch an organization from a package name |
| `GET` | `/api/v1/orgs/{org_id}` | Get organization status and agent roster |
| `DELETE` | `/api/v1/orgs/{org_id}` | Shutdown and remove an organization |
| `POST` | `/api/v1/orgs/{org_id}/tasks` | Submit a task for bid-based assignment |
| `GET` | `/api/v1/orgs/{org_id}/agents` | List all agents with wallet balances and trust scores |
| `GET` | `/api/v1/orgs/{org_id}/agents/{agent_id}` | Get agent status and effectiveness trend |
| `GET` | `/api/v1/orgs/{org_id}/governance` | Get the current governance configuration |
| `PATCH` | `/api/v1/orgs/{org_id}/governance` | Adjust governance levers on a running organization |
| `GET` | `/api/v1/orgs/{org_id}/billing` | Get usage and budget summary |
| `POST` | `/api/v1/gateway/chat/completions` | OpenAI-compatible LLM proxy with smart routing |
| `GET` | `/api/v1/gateway/models` | List available models and pricing |
| `GET` | `/api/v1/packages` | List all built-in packages |
| `GET` | `/api/v1/packages/{name}` | Get full details for a specific package |
| `POST` | `/api/v1/webhooks` | Register a webhook URL for event notifications |
| `GET` | `/api/v1/webhooks` | List registered webhooks for the current tenant |

### Supported webhook events

- `task.assigned`
- `task.completed`
- `budget.alert`
- `circuit_breaker.tripped`
- `org.started`
- `org.stopped`

---

## CLI Commands

```
agency-os <command> [options]
```

| Command | Description |
|---|---|
| `run <package>` | Launch an organization from a built-in package name or a YAML file path |
| `run <package> --task "..."` | Launch and immediately submit a task after startup |
| `run <package> --org-id <id>` | Launch with a custom organization ID |
| `list-packages` | List all built-in packages shipped with Agency-OS |
| `validate <package>` | Validate a package YAML file against the schema; exit 1 on failure |
| `status <package>` | Print package metadata, agent list, and workflow summary without launching |
| `serve` | Start the FastAPI REST server (default: `0.0.0.0:8000`) |
| `serve --host <h> --port <p>` | Start the server on a custom host and port |

---

## Development

### Install development dependencies

```bash
# Clone the repository
git clone https://github.com/raelisavitt/agency-os.git
cd agency-os

# Bootstrap isolated tooling/runtime (repo-local .venv via uv)
make python-env
```

### Run the test suite

```bash
# All tests
make test

# With coverage report
make coverage

# Unit tests only
make test-unit

# Integration tests
make test-integration

# End-to-end tests
make test-e2e
```

### Lint and type-check

```bash
make lint
make typecheck
```

### Run full-stack quality gates

```bash
# Backend lint + type-check + tests + dependency audit, plus frontend test+build
make fullstack-check
```

Frontend dependency/toolchain note: this repo pins Node 22 via root `.nvmrc` and `.node-version`. Run `nvm use` (or your version manager equivalent) before `make frontend-install`, `make frontend-test`, or `make frontend-build`.

### Security scanning

```bash
# Audit Python dependencies for known CVEs
make dependency-audit
```

The CI pipeline automatically runs `pip-audit` on both lock files. Any high or critical severity CVE will fail the build and block deployment.

### Project structure

```
agency-os/
├── pyproject.toml
├── docker-compose.yml
├── Makefile
│
├── agency_os/
│   ├── agents/
│   │   ├── agent_factory.py      # Instantiates BusinessAgent from PackageSpec
│   │   ├── bid_strategies.py     # quality_weighted, specialization_bonus, etc.
│   │   ├── business_agent.py     # Core agent class with wallet and reputation
│   │   ├── registry.py           # Agent spec lookup by ref path
│   │   ├── spec_parser.py        # Parses SWARM agent YAML specs
│   │   └── tool_permissions.py   # Enforce allow/deny tool lists
│   │
│   ├── dashboard/
│   │   ├── streamlit_app.py      # Streamlit dashboard entry point
│   │   └── pages/                # overview, tasks, wallets, reputation, governance, audits
│   │
│   ├── economic/
│   │   ├── budget_allocator.py   # Distributes budget across agents
│   │   ├── wallet_manager.py     # Per-agent balance tracking
│   │   └── billing_bridge.py     # Connects usage to Stripe metering
│   │
│   ├── governance/
│   │   ├── presets.py            # Loads profile YAML and applies package overrides
│   │   └── profiles/
│   │       ├── conservative.yaml
│   │       ├── balanced.yaml
│   │       └── aggressive.yaml
│   │
│   ├── metering/
│   │   ├── collector.py          # Records LLM token and task events
│   │   ├── aggregator.py         # Rolls up usage per tenant/org
│   │   └── stripe_hook.py        # Pushes usage records to Stripe
│   │
│   ├── orchestration/
│   │   ├── organization.py       # Top-level org object; start/stop/submit_task
│   │   ├── task_router.py        # Sealed-bid auction and task assignment
│   │   ├── workflow_engine.py    # Executes multi-stage workflow pipelines
│   │   ├── nexus_adapter.py      # Bridges to SWARM Nexus pipeline
│   │   └── feedback_loops.py     # Post-task reputation and balance updates
│   │
│   ├── packages/
│   │   ├── schema.py             # Pydantic models for PackageSpec validation
│   │   ├── loader.py             # load_package(), list_builtin_packages(), validate_package()
│   │   └── library/
│   │       ├── _base.yaml
│   │       ├── saas_dev_studio.yaml
│   │       ├── marketing_agency.yaml
│   │       ├── product_squad.yaml
│   │       └── devops_team.yaml
│   │
│   ├── service/
│   │   ├── cli.py                # Typer CLI (run, list-packages, validate, status, serve)
│   │   └── api/
│   │       ├── app.py            # FastAPI application factory
│   │       ├── middleware/       # auth, rate limiting, tenant isolation
│   │       └── routers/          # organizations, packages, tasks, agents,
│   │                             # governance, billing, webhooks
│   │
│   └── tenancy/
│       ├── tenant.py             # Tenant model and TenantRegistry
│       ├── isolation.py          # Per-tenant resource scoping
│       └── secrets.py            # Tenant credential management
│
├── tests/
│   ├── unit/                     # Schema, loader, factory, agent, org, spec parser
│   ├── integration/              # API lifecycle, org lifecycle
│   └── e2e/                      # Budget limits, circuit breakers, multi-tenant load
│
├── deploy/
│   ├── docker/
│   │   ├── Dockerfile.api
│   │   ├── Dockerfile.dashboard
│   │   └── Dockerfile.worker
│   └── compose/
│       └── docker-compose.prod.yml
│
└── vendor/
    └── swarm/                    # Vendored SWARM governance + agent engine
```

---

## License

Proprietary. Copyright (c) 2026 Raeli Savitt. All rights reserved.
