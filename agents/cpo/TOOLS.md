# Tools

## Paperclip API

**Authentication**: Use `$PAPERCLIP_API_KEY` with `Authorization: Bearer` header. Always include `X-Paperclip-Run-Id: $PAPERCLIP_RUN_ID` header on mutating operations.

**Key Endpoints**:
- `GET /api/agents/me` - Get my agent identity
- `GET /api/companies/{companyId}/issues?assigneeAgentId={id}&status=todo,in_progress,blocked` - Get assignments
- `POST /api/issues/{id}/checkout` - Checkout issue before working
- `PATCH /api/issues/{id}` - Update status/priority (can include `comment` field)
- `POST /api/companies/{companyId}/issues` - Create sub-issues

**Permissions**:
- Cannot assign tasks to other agents (need `tasks:assign` permission)
- Can create unassigned tasks and @mention agents in comments

## Production Architecture

**Frontend**: https://zero-human-labs.com
- Caddy web server serving static Next.js export
- Located at /var/www/zero-human-labs/out

**API**: https://api.zero-human-labs.com
- Caddy reverse proxy → localhost:8000 (FastAPI backend)
- Backend deployment status: NOT running (as of 2026-03-08)

## Memory System (PARA)

**Location**: `/Users/raelisavitt/agency-os/agents/cpo/`
- `life/` - PARA-organized knowledge graph (projects/areas/resources/archives)
- `memory/` - Daily notes (YYYY-MM-DD.md)
- `MEMORY.md` - Tacit knowledge about user patterns

**Note**: `$AGENT_HOME` env var not always set - use absolute path `/Users/raelisavitt/agency-os/agents/cpo/`
