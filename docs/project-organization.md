# Project Organization Guidelines

## When to Create a Project

Create a project when:
- **Multiple related issues** span 2+ weeks of work across multiple team members
- **Strategic initiative** with clear goals, deliverables, and success metrics
- **Domain-specific work** that benefits from dedicated workspace configuration
- **Cross-functional effort** requiring coordination between multiple agents/roles

**Don't create a project for:**
- Single issues or small bug fixes
- One-off research tasks
- Individual feature requests that don't belong to a larger initiative

## Current Strategic Projects

### 1. **agency-os** (Core Platform)
**Purpose:** Core product development - FastAPI backend, governance engine, metering, gateway, orchestration.

**What belongs here:**
- Platform architecture and core features
- Database schema and persistence layer
- Core API endpoints and business logic
- Governance and safety framework implementation
- Metering and billing core functionality

**Examples:**
- Task-type classifier integration (ZERA-20)
- Trust score computation (ZERA-6)
- Idempotency support for Stripe (from commit history)

---

### 2. **Launch Readiness**
**Purpose:** Infrastructure hardening, security, and production-grade reliability for public launch.

**What belongs here:**
- Database migrations and schema fixes (ZERA-140)
- Backup and disaster recovery (ZERA-146)
- Security hardening (ZERA-138, ZERA-118, ZERA-122)
- CI/CD pipeline fixes (ZERA-139)
- Production deployment hygiene (ZERA-128)
- Critical bug fixes blocking launch
- API completion gaps (ZERA-136 - public pricing API)
- Performance and reliability issues

**Examples:**
- Zero backup/disaster recovery strategy (ZERA-146)
- Database schema mismatch - missing governance_preset column (ZERA-140)
- Cross-tenant information disclosure (ZERA-138)
- Tenant API keys invalid after restart (ZERA-118)

---

### 3. **Marketing & Growth**
**Purpose:** Go-to-market execution, public presence, user acquisition.

**What belongs here:**
- Website improvements and UX fixes
- Content pipeline (blog, documentation)
- SEO optimization (ZERA-111)
- Community building (Discord, forums)
- Brand messaging and positioning (ZERA-116)
- Analytics and conversion optimization
- Waitlist and signup flow

**Examples:**
- Fix dead post-signup links (ZERA-96)
- Hero messaging conflict (ZERA-116)
- SEO metadata (ZERA-111)
- Blog publishing pipeline (ZERA-92)
- Discord community launch (ZERA-41)

---

### 4. **Governance & Research**
**Purpose:** Agent safety research, evaluation frameworks, IP development through original research.

**What belongs here:**
- Capability-safety optimization research
- Governance framework evolution
- Evaluation harness development
- SWARM research integration
- Trust and safety mechanisms
- Harness engineering research

**Examples:**
- Capability-safety pareto frontier (ZERA-3, ZERA-5-8)
- Harness engineering research (ZERA-12, ZERA-4)
- Eval harness PR review (ZERA-13)

---

## Project Lifecycle

### Creating a Project
```bash
POST /api/companies/{companyId}/projects
{
  "name": "Project Name",
  "urlKey": "project-slug",
  "description": "Clear description of scope, goals, and deliverables",
  "visibility": "company",
  "workspace": {
    "cwd": "/path/to/working/directory",
    "repoUrl": "https://github.com/org/repo"  # optional
  }
}
```

### Assigning Issues to Projects
When creating new issues:
```bash
POST /api/companies/{companyId}/issues
{
  "title": "Issue title",
  "projectId": "project-uuid",
  "priority": "high",
  ...
}
```

### Assignment Permission Guardrails

Issue creation with `assigneeAgentId` requires `tasks:assign` permission. Engineer/general agents without that permission will get:

```json
{"error":"Missing permission: tasks:assign"}
```

Remediation flow for non-manager agents:

1. Create the issue without `assigneeAgentId` (leave it unassigned).
2. Claim it via checkout:

```bash
POST /api/issues/{issueId}/checkout
{
  "agentId": "{your-agent-id}",
  "expectedStatuses": ["todo", "backlog", "blocked"]
}
```

This keeps assignment policy intact while still allowing self-serve ownership by the assignee.

For existing issues:
```bash
PATCH /api/issues/{issueId}
{
  "projectId": "project-uuid"
}
```

---

## Project Ownership

Each project should have:
- **Clear scope** - What's in, what's out
- **Success metrics** - How do we know when it's done?
- **Primary owner** - Which agent/team is accountable?
- **Workspace config** - Where does the work happen?

---

## When NOT to Use Projects

- **Organizational meta-work** - Issues about how we organize work (like ZERA-147 itself)
- **One-off investigations** - Single research tasks that don't connect to broader initiatives
- **Administrative tasks** - Hiring, onboarding, recurring loops
- **Quick wins** - Small improvements that can be done in isolation

These can remain in the backlog without a project assignment.

---

## Migration Strategy

**Existing issues:** Don't force-migrate everything. Instead:
1. New critical/high priority work → assign to appropriate project on creation
2. When working on an old issue, optionally reassign to project if it fits
3. Quarterly cleanup: review orphaned issues and batch-assign to projects

**Project health:** Review project dashboards monthly to ensure:
- No abandoned projects with zero activity
- Projects have clear owners and roadmaps
- Issues are properly distributed (not everything dumped into agency-os)
