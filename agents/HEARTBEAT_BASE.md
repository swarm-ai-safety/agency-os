# Shared Heartbeat Base

Every agent's HEARTBEAT.md imports this shared protocol. Role-specific sections are defined in each agent's own file. This avoids duplicating ~400 tokens per agent per heartbeat cycle.

## 1. Identity and Context

- `GET /api/agents/me` -- confirm your id, role, budget, chainOfCommand.
- Check wake context: `PAPERCLIP_TASK_ID`, `PAPERCLIP_WAKE_REASON`, `PAPERCLIP_WAKE_COMMENT_ID`.

## 2. Local Planning Check

1. Read today's plan from `$AGENT_HOME/memory/YYYY-MM-DD.md` under "## Today's Plan".
2. Review each planned item: what's completed, what's blocked, what's next.
3. For any blockers, resolve them yourself or escalate to the CEO.
4. **Record progress updates** in the daily notes.

## 3. Get Assignments

- `GET /api/companies/{companyId}/issues?assigneeAgentId={your-id}&status=todo,in_progress,blocked`
- Prioritize: `in_progress` first, then `todo`. Skip `blocked` unless you can unblock it.
- If `PAPERCLIP_TASK_ID` is set and assigned to you, prioritize that task.

## 4. Checkout and Triage

- Always checkout before working: `POST /api/issues/{id}/checkout`.
- Never retry a 409 -- that task belongs to someone else.
- **Before starting work, triage for delegation:**
  1. Read the task description and comments carefully.
  2. Identify if any part of the task is outside your domain.
  3. If yes, create subtasks for the right agent using `POST /api/companies/{companyId}/issues` with `assigneeAgentId` and `parentId` set to the current issue. Use `GET /api/companies/{companyId}/agents` to find agent IDs.
  4. If you need input or review from another agent, @mention them in a comment with `mentionedAgentIds`.
  5. Keep the parts that are in your domain and proceed.

## 5. Do the Work

> **See your role-specific HEARTBEAT.md for domain work patterns.**

## 6. Fact Extraction

1. Check for new conversations since last extraction.
2. Extract durable facts to the relevant entity in `$AGENT_HOME/life/` (PARA).
3. Update `$AGENT_HOME/memory/YYYY-MM-DD.md` with timeline entries.
4. Update access metadata (timestamp, access_count) for any referenced facts.

## 7. Exit

- Comment on any in_progress work before exiting.
- If no assignments and no valid mention-handoff, exit cleanly.

## Rules

- Always use the Paperclip skill for coordination.
- Always include `X-Paperclip-Run-Id` header on mutating API calls.
- Comment in concise markdown: status line + bullets + links.
- Never look for unassigned work -- only work on what is assigned to you.
