# Agency-OS

The governed agent operating system — spin up an autonomous AI workforce that can't run wild, from a single YAML file.

Agency-OS is a governance-first agent platform. Every agent holds a wallet, competes for tasks through sealed-bid auctions, and operates under safety rails calibrated from real simulation data. Circuit breakers stop runaway loops, per-agent budgets enforce hard ceilings, and trust scores automatically demote underperformers. You get a full AI organization — without babysitting it.

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

### Launch an organization

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

---

## Architecture

A **Package** declares which agents to hire, their economic configuration, the governance preset, and named workflows. At runtime the **Agent Factory** instantiates agents from specs. The **Organization** holds the roster and wires it to the **Task Router**, which runs a sealed-bid auction so the most qualified agent wins each task. The **Governance** layer enforces audits, circuit breakers, and transaction taxes. The **Economics** layer manages per-agent wallets, trust scores, and budget limits.

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
        +-------------+   +-------------+   +-------------+
```

**Request flow:**

1. A task arrives via CLI or `POST /api/v1/orgs/{org_id}/tasks`.
2. The Task Router broadcasts the task to all agents.
3. Each agent submits a bid according to its configured strategy.
4. The highest valid bid wins. The winning agent executes the task.
5. On completion, the governance layer may trigger an audit; repeated violations trip the circuit breaker and freeze the agent.

---

## Built-in Packages

| Name | Agents | Governance | Description |
|---|---|---|---|
| `saas-dev-studio` | 6 | balanced | Full-stack SaaS development team |
| `marketing-agency` | 6 | balanced | Content, SEO, and growth marketing |
| `product-squad` | 5 | balanced | Product management and design |
| `devops-team` | 4 | conservative | Infrastructure and operations |

---

## Package YAML Format

```yaml
apiVersion: agency-os/v1
kind: Package

metadata:
  name: my-team
  display_name: "My Custom Team"

agents:
  - ref: engineering/senior-developer
    role_override:
      title: "Tech Lead"
    economic:
      initial_balance: 1000
      bid_strategy: quality_weighted
    permissions:
      tools: [code_write, code_review, git_commit]
      deny: [deploy_production]

governance:
  preset: balanced                # conservative | balanced | aggressive
  overrides:
    audit_frequency: 0.15
    circuit_breaker:
      enabled: true
      threshold: 3

workflows:
  - name: feature_development
    stages:
      - plan:      [project-manager]
      - implement: [senior-developer]
      - test:      [qa-engineer]
    quality_gates:
      implement_to_test:
        min_approvals: 1
```

---

## Governance Presets

Three profiles ship out of the box. Select one via `governance.preset` and override individual fields as needed.

| | conservative | balanced | aggressive |
|---|---|---|---|
| **Audit** | High probability | Moderate | Minimal |
| **Circuit breaker** | Tight (2 violations) | Standard (3) | Loose (5) |
| **Bandwidth** | Restricted | Moderate | High throughput |
| **Staking** | Required | No | No |
| **Best for** | Production / sensitive ops | General use | Prototyping / sandbox |

---

## API

Start the server with `agency-os serve` or `uvicorn agency_os.service.api.app:app`.

All `/api/v1/*` routes require a valid API key via `X-API-Key` header. Interactive docs at `/docs`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/tenants` | Sign up — returns tenant ID and API key |
| `POST` | `/api/v1/orgs` | Launch an organization from a package |
| `POST` | `/api/v1/orgs/{org_id}/tasks` | Submit a task for bid-based assignment |
| `GET` | `/api/v1/orgs/{org_id}/agents` | List agents with wallet balances and trust scores |
| `PATCH` | `/api/v1/orgs/{org_id}/governance` | Adjust governance levers at runtime |
| `POST` | `/api/v1/gateway/chat/completions` | OpenAI-compatible LLM proxy with smart routing |
| `POST` | `/api/v1/webhooks` | Register webhook for event notifications |

---

## CLI

```
agency-os <command> [options]
```

| Command | Description |
|---|---|
| `run <package>` | Launch from a package name or YAML path |
| `run <package> --task "..."` | Launch and submit a task |
| `list-packages` | List built-in packages |
| `validate <package>` | Validate a package YAML against the schema |
| `status <package>` | Print package details without launching |
| `serve` | Start the REST API server |

---

## Development

```bash
git clone https://github.com/swarm-ai-safety/agency-os.git
cd agency-os
make python-env   # Bootstrap .venv via uv
make test         # Run all tests
make lint         # Lint + format
make typecheck    # mypy
```

### Optional private modules

Stripe billing, Coinbase wallet integration, and pricing configuration are available as a separate private package:

```bash
pip install agency-os-private
```

The core platform works without it — billing/wallet endpoints return 503 gracefully.

---

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
