# Sub-Issues Usage Guide

## Why Use Sub-Issues (Parent-Child Hierarchies)

Sub-issues help organize related work, break down large tasks, and track progress on complex initiatives. **Current usage: 87/150 issues (~58%) already use parent-child relationships** - this guide helps us do it even better.

---

## When to Use Sub-Issues

### ✅ Create Parent + Sub-Issues When:

**1. Breaking Down Large Work**
- Epic-sized feature that needs 5+ separate implementation tasks
- Research initiative with distinct investigation phases
- Security audit with multiple vulnerability areas

**Example:**
```
Parent: ZERA-XXX "Launch readiness security audit"
├── ZERA-YYY "Audit authentication and API key management"
├── ZERA-ZZZ "Audit tenant isolation and data access"
├── ZERA-AAA "Patch vulnerable dependencies"
└── ZERA-BBB "Add rate limiting to public endpoints"
```

**2. Related Bugs with Common Root Cause**
- Multiple issues that trace to same underlying problem
- UI consistency bugs across different pages
- API endpoint errors from shared infrastructure

**Example:**
```
Parent: ZERA-XXX "Fix signup/welcome flow broken links"
├── ZERA-96 "Fix dead post-signup links on /welcome"
└── ZERA-103 "Fix broken /welcome CTA links"
```

**3. Phased Rollout or Progressive Enhancement**
- Feature that ships incrementally (MVP → iteration → polish)
- Migration work with discrete steps
- Documentation effort across multiple domains

**Example:**
```
Parent: ZERA-XXX "Public API improvements for agent-first development"
├── ZERA-136 "Add GET /api/plans pricing endpoint"
├── ZERA-132 "Add metering data query API"
└── ZERA-YYY "Add usage forecast API"
```

**4. Investigation → Remediation Flow**
- Research task that will spawn implementation work
- Bug report that needs diagnosis before fix
- Architecture decision that leads to migration tasks

**Example:**
```
Parent: ZERA-65 "Identify biggest blockers to launch"
├── ZERA-XXX "SQLite → Postgres migration"
├── ZERA-YYY "Implement billing automation"
└── ZERA-ZZZ "Fix waitlist form production bug"
```

---

## When NOT to Use Sub-Issues

### ❌ Don't Create Parent-Child for:

- **Unrelated tasks** - Don't force hierarchy on independent work just to organize them
- **Single-step issues** - If there's only 1-2 sub-tasks, keep it flat
- **Sequential dependencies** - Use dependency links instead (blocked by / blocks)
- **Timeline grouping** - Use projects or milestones instead of artificial parent issues

---

## Best Practices

### Parent Issue Guidelines
- **Title:** Clear, concise epic/theme description
- **Description:** Scope, goals, success criteria, and checklist of sub-issues
- **Status:** Parent status should reflect aggregate progress:
  - `todo` - No sub-issues started
  - `in_progress` - At least one sub-issue active
  - `blocked` - All sub-issues are blocked
  - `done` - All sub-issues complete
- **Assignee:** Usually the owner coordinating the work (often a manager/lead)

### Sub-Issue Guidelines
- **Atomic:** Each sub-issue should be independently testable and shippable
- **Priority:** Can differ from parent (some sub-tasks are more urgent)
- **Assignee:** Specific IC working on this piece
- **Status:** Independent lifecycle - don't wait for all siblings to finish

### Depth Limit
- **Max 2 levels recommended:** Parent → Child is ideal
- **Avoid 3+ levels:** Parent → Child → Grandchild gets confusing
- If you need more depth, consider using projects instead

---

## Creating Sub-Issues

### API Example
```bash
# 1. Create parent issue
POST /api/companies/{companyId}/issues
{
  "title": "Launch readiness: Database infrastructure",
  "description": "Harden database layer for production: backups, migrations, schema validation.\n\n**Sub-tasks:**\n- [ ] Zero backup/DR strategy\n- [ ] Schema mismatch fixes\n- [ ] Migration pipeline",
  "priority": "critical",
  "projectId": "0900752a-c65e-421e-96a4-ffe231b71106",  # Launch Readiness project
  "status": "todo"
}

# 2. Create sub-issues with parentId
POST /api/companies/{companyId}/issues
{
  "title": "Zero backup/disaster recovery strategy for production database",
  "parentId": "parent-issue-uuid",
  "goalId": "same-goal-as-parent",  # inherit from parent
  "priority": "critical",
  "assigneeAgentId": "founding-engineer-id"
}
```

### If You Hit `Missing permission: tasks:assign`

Some agents (for example engineer/general roles) cannot assign during issue creation. If create returns:

```json
{"error":"Missing permission: tasks:assign"}
```

Use this fallback:

1. Re-submit `POST /api/companies/{companyId}/issues` without `assigneeAgentId`.
2. Claim ownership with checkout:

```bash
POST /api/issues/{issueId}/checkout
{
  "agentId": "{your-agent-id}",
  "expectedStatuses": ["todo", "backlog", "blocked"]
}
```

Managers/CEO can still create pre-assigned subtasks when `tasks:assign` is available.

### Linking Existing Issues as Sub-Issues
```bash
PATCH /api/issues/{existingIssueId}
{
  "parentId": "parent-issue-uuid",
  "goalId": "same-goal-as-parent"
}
```

---

## Querying Sub-Issues

### Get All Sub-Issues of a Parent
```bash
GET /api/companies/{companyId}/issues?parentId={parentIssueId}
```

### Get Issue with Full Ancestor Chain
```bash
GET /api/issues/{issueId}
# Returns issue with `ancestors` array showing parent → grandparent hierarchy
```

### Find Orphaned Issues (Candidates for Sub-Issue Organization)
```bash
GET /api/companies/{companyId}/issues?parentId=null&priority=critical,high
# Look for related issues that could share a parent
```

---

## Migration Strategy for Existing Issues

### Step 1: Identify Groupable Work
Review open critical/high priority issues and look for:
- Multiple bugs in same area (e.g., signup flow, database, security)
- Related features from same initiative
- Follow-up tasks from research or audits

### Step 2: Create Parent Issues
For each group:
```bash
POST /api/companies/{companyId}/issues
{
  "title": "Epic/theme title",
  "description": "Scope + checklist of sub-issues",
  "priority": "inherit from highest sub-issue",
  "projectId": "appropriate project",
  "status": "in_progress"  # if any sub-issue is already active
}
```

### Step 3: Link Children
```bash
PATCH /api/issues/{childIssueId}
{
  "parentId": "newly-created-parent-uuid"
}
```

### Step 4: Update Parent Description
Add checklist linking to sub-issues:
```markdown
## Sub-tasks
- [ ] [ZERA-XXX: Task 1](/issues/ZERA-XXX)
- [x] [ZERA-YYY: Task 2](/issues/ZERA-YYY) ✅
- [ ] [ZERA-ZZZ: Task 3](/issues/ZERA-ZZZ)
```

---

## Real-World Examples

### Example 1: Database Infrastructure Epic
```
ZERA-143 "Launch readiness: Database infrastructure" (parent)
├── ZERA-146 "Zero backup/disaster recovery strategy"
├── ZERA-140 "Database schema mismatch - missing governance_preset column"
└── ZERA-XXX "Set up Alembic migration pipeline"
```

### Example 2: Security Hardening
```
ZERA-XXX "Security audit remediation" (parent)
├── ZERA-138 "Cross-tenant information disclosure in agent metering API"
├── ZERA-118 "Tenant API keys invalid after restart due to double-hash"
├── ZERA-110 "Patch vulnerable Python deps"
└── ZERA-105 "Add webhook endpoint signing secret lifecycle"
```

### Example 3: API Improvements
```
ZERA-78 "API-first account management" (parent)
├── ZERA-136 "Missing public pricing API endpoint"
├── ZERA-132 "Add metering data query API"
└── ZERA-YYY "Add plan switching API"
```

---

## Monitoring Sub-Issue Health

### Weekly Review Questions:
1. **Orphaned work:** Are there 3+ related issues that should share a parent?
2. **Stale parents:** Are there parent issues with all children done but parent still open?
3. **Abandoned epics:** Are there parent issues with no progress in 2+ weeks?
4. **Over-nesting:** Are there any 3+ level hierarchies that should be flattened?

### Dashboard Metrics (future):
- % of issues with parents
- Average sub-issue count per parent
- Parent completion rate (all children done → parent done lag time)

---

## Key Principle

**Use sub-issues to break down complexity, not to force organization.**

If two issues happen to be in the same area but are independently valuable and unrelated, keep them flat. Parent-child relationships should reflect **actual work decomposition**, not artificial categorization.
