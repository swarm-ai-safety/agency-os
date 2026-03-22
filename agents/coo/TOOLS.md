# Tools

## Paperclip API

**Permissions**: COO role is `general` (not `ceo`), which means:
- ❌ Cannot create agents (`canCreateAgents: false`)
- ❌ Cannot assign tasks to other agents (`tasks:assign` permission denied)
- ❌ Cannot reassign issues (requires `tasks:assign`)
- ✅ Can checkout, update status, comment on assigned issues
- ✅ Can mark issues as blocked and escalate via comments

**Escalation pattern when blocked**:
1. Mark issue status → `blocked`
2. Add comment with clear next steps and who needs to act
3. CEO will see blocked issue and delegate accordingly

**API Endpoints Used**:
- `GET /api/agents/me` - get my identity and chain of command
- `GET /api/companies/{companyId}/issues?assigneeAgentId={id}&status=...` - get assignments
- `POST /api/issues/{id}/checkout` - checkout before working (required!)
- `GET /api/issues/{id}` - get issue details with ancestors
- `GET /api/issues/{id}/comments` - read comment thread
- `PATCH /api/issues/{id}` - update status and add comments
- `GET /api/companies/{companyId}/dashboard` - run stats and health metrics

**Always include**: `-H 'X-Paperclip-Run-Id: $PAPERCLIP_RUN_ID'` on mutating requests.

## Memory System (PARA)

Using `para-memory-files` skill for persistent memory across sessions.

**Structure**:
- `$AGENT_HOME/memory/YYYY-MM-DD.md` - daily timeline notes
- `$AGENT_HOME/life/` - PARA-organized entity files (projects/areas/resources/archives)
- `$AGENT_HOME/MEMORY.md` - tacit knowledge about user patterns

**Recall**: Use `qmd query "search term"` for semantic search across memory.
