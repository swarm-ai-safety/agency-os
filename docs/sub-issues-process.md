# Sub-Issues Process Guide

## Current State Analysis

**Good news:** We're already using parent/child relationships heavily.

- **90% of open issues** have parents (53 out of 59)
- Only 6 top-level issues currently
- Existing parent tracking: ZERA-152 (security), ZERA-151 (DB infra), ZERA-153 (UX) all properly track their children

**The Gap:** 44 complex, unassigned issues that need decomposition before assignment.

Critical examples:
- ZERA-140 (2.5k char description) — DB schema mismatch
- ZERA-139 — CI failing
- ZERA-130 — 500 errors
- ZERA-138 (4.7k char description) — Cross-tenant disclosure

## When to Use Sub-Issues

### Always break down if:
1. **Description > 500 chars** — likely multi-step work
2. **Multiple bullet points** in requirements — each bullet is a subtask
3. **Multiple files/modules** need changes
4. **Cross-functional** — needs multiple agent roles (FE + CMO + Security, etc.)
5. **>3 day estimate** — if a human would take >3 days, decompose it

### Keep as single issue if:
1. **Single file edit** — focused change
2. **<300 char description** — simple, clear scope
3. **Obvious next action** — no planning needed
4. **Bug fix with known root cause**

## Process: Board → CEO → Delegation

### Board creates high-level issue
- Title only, or brief description
- Assign to CEO for decomposition (or leave unassigned)
- Set priority/labels

### CEO decomposes (before delegation)
1. **Checkout** the parent issue
2. **Add description** with context/why
3. **Create subtasks** via `POST /api/companies/{companyId}/issues`:
   - Set `parentId` to parent issue ID
   - Set `goalId` if parent has one
   - Assign subtasks to appropriate agents
4. **Mark parent `in_review`** or `blocked` (waiting for children to complete)
5. **Comment** on parent linking to children

### Agents complete subtasks
- Work on assigned subtasks
- Mark `done` when complete
- Comment with summary

### Permission Caveat on Subtask Creation

Creating issues with `assigneeAgentId` requires `tasks:assign`. If an engineer/general agent gets:

```json
{"error":"Missing permission: tasks:assign"}
```

Fallback workflow:

1. Create the issue without `assigneeAgentId`.
2. Claim it with `POST /api/issues/{issueId}/checkout` using your own `agentId`.

### CEO closes parent
- When all children done, review outcomes
- Close parent with summary comment

## Anti-Patterns (Don't Do This)

❌ **Markdown checklists instead of real subtasks**
```md
## Sub-tasks
- [ ] ZERA-138 (issue exists but parentId not set)
- [ ] ZERA-118
```
✅ **Proper parent/child via API**
- Create issues with `parentId` set
- Use `GET /api/issues/{id}` to see ancestors/children
- Comment threads work across hierarchy

❌ **Assigning complex issue directly to engineer**
- Forces engineer to either:
  - Work on monolith (inefficient)
  - Decompose themselves (not their role)

✅ **CEO decomposes, then assigns subtasks**
- Clear scope per agent
- Parallelizable work
- Better cost tracking

❌ **Creating subtask after parent is `done`**
- Orphaned work, lost context

✅ **All subtasks created upfront**
- Full scope visible
- Can track progress

## Automation Candidates

1. **Issue complexity linter** — flag issues with >500 char description and no children
2. **Auto-decomposition prompt** — when board creates complex issue, auto-assign to CEO with "Please decompose" comment
3. **Parent closing guard** — prevent marking parent `done` if children are still `in_progress`

## Immediate Actions (CEO)

Run this query daily to find decomposition candidates:

```bash
curl -s -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/issues?status=todo,backlog" | \
  jq -r '.[] | select(.assigneeAgentId == null) | select(.description) | select((.description | length) > 400) | "\(.identifier) - \(.title)"'
```

Decompose these before assigning to engineers.

## Metrics to Track

- % of issues with parents (target: maintain >85%)
- Average subtask count per parent (target: 3-5)
- % of critical/high issues decomposed before assignment (target: 100%)
- Time from issue creation to decomposition (target: <24h for critical)
