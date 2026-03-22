# Product Requirements: The Agency Integration

**Status:** Draft
**Owner:** CPO
**Issue:** ZERA-173
**Last Updated:** 2026-03-08

---

## Executive Summary

Integrate The Agency's 61 specialized AI agent personalities into Agency-OS as a preset library. Users can instantiate production-ready specialists (Frontend Developer, Growth Hacker, Security Engineer) with our governance layer providing trust, safety, and economic coordination.

**Value Proposition:** "The Agency provides the specialists. Agency-OS provides the trust, safety, and economic coordination to deploy them at scale."

---

## 1. Problem Statement

### Current State
- Agency-OS users must manually configure agent personalities, workflows, and capabilities
- No standard library of production-ready agent templates
- High barrier to entry: users need to understand agent prompt engineering before getting value

### User Pain Points
1. **Time to first value is too long** - Users want to hire a "Security Engineer" agent, not write a prompt from scratch
2. **Quality inconsistency** - Hand-written agent prompts vary wildly in quality
3. **Missing best practices** - Users don't know what makes a good agent definition

### Opportunity
The Agency repository (10.9k stars, MIT license) has 61 battle-tested agent personalities with:
- ✅ Domain expertise (specialized roles across 9 divisions)
- ✅ Production workflows and deliverables
- ✅ Success metrics and communication styles
- ✅ Community validation (10.9k stars)

**Strategic fit:** They provide personalities, we provide governance. Complementary, not competitive.

---

## 2. Solution Overview

### What We're Building

**Agent Preset Library** - A browsable catalog of The Agency's 61 specialists integrated into Agency-OS.

Users can:
1. Browse presets by division (Engineering, Design, Marketing, etc.)
2. Preview agent personality, capabilities, and workflows
3. Instantiate an agent from a preset with one click
4. Customize governance settings (trust thresholds, audit probability, budget)
5. Deploy the agent with our safety rails automatically applied

### Core Principles

1. **Zero configuration to start, infinite configuration when needed**
   One-click instantiation with sensible defaults. Power users can customize everything.

2. **Governance is non-negotiable**
   Every preset agent gets wrapped with our trust scoring, circuit breakers, and audit trails.

3. **Upstream attribution**
   Clear credit to The Agency project. Link to source repo, respect MIT license.

4. **Living library**
   Design for future updates - new agents from The Agency, community contributions, custom presets.

---

## 3. User Experience

### 3.1 Discovery Flow

**Entry points:**
- Primary: "Create Agent" button → "Start from preset" tab
- Secondary: Dedicated `/presets` page for browsing
- Tertiary: Quick actions in agent list ("Clone from preset")

**Browse UI:**
```
┌─────────────────────────────────────────────────────┐
│  Agent Presets                      [Filter: All ▾] │
├─────────────────────────────────────────────────────┤
│                                                     │
│  💻 Engineering (8)                                 │
│  ┌──────────┬──────────┬──────────┐                │
│  │ Frontend │ Backend  │ AI       │   [View all →] │
│  │ Developer│ Architect│ Engineer │                │
│  └──────────┴──────────┴──────────┘                │
│                                                     │
│  🎨 Design (7)                                      │
│  ┌──────────┬──────────┬──────────┐                │
│  │ UI       │ UX       │ Whimsy   │   [View all →] │
│  │ Designer │ Researcher│ Injector│                │
│  └──────────┴──────────┴──────────┘                │
│                                                     │
│  📢 Marketing (11)                                  │
│  ...                                                │
└─────────────────────────────────────────────────────┘
```

**Filters:**
- Division (Engineering, Design, Marketing, Product, etc.)
- Specialty (Security, Performance, Growth, etc.)
- Search (fuzzy match on name, description, capabilities)

### 3.2 Preview & Instantiation

**Agent detail modal:**
```
┌─────────────────────────────────────────────────────┐
│  🤖 AI Engineer                          [Preview]  │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Expert AI/ML engineer specializing in machine     │
│  learning model development, deployment, and       │
│  integration into production systems.              │
│                                                     │
│  ✨ Capabilities                                    │
│  • TensorFlow, PyTorch, Scikit-learn, HF           │
│  • MLOps: MLflow, Kubeflow, model monitoring       │
│  • Production deployment & A/B testing             │
│                                                     │
│  📊 Success Metrics                                 │
│  • Model accuracy/F1 meets requirements (85%+)     │
│  • Inference latency < 100ms                       │
│  • Model serving uptime > 99.5%                    │
│                                                     │
│  🔒 Governance                                      │
│  [Balanced ▾] Trust threshold: Medium              │
│             Circuit breaker: 5 failures/10 tasks   │
│             Audit probability: 0.1                 │
│                                                     │
│  ────────────────────────────────────────────────  │
│  [Cancel]          [Customize]  [Create Agent →]   │
└─────────────────────────────────────────────────────┘
```

**One-click flow:**
1. User clicks "Create Agent" from preset card
2. Modal shows: Name (pre-filled), Governance preset (default: Balanced), Budget
3. User clicks "Create Agent →"
4. Agent is provisioned with The Agency personality + our governance layer
5. Redirect to agent detail page with "Agent created" success message

**Customization flow:**
1. User clicks "Customize" instead of "Create Agent"
2. Full agent creation form opens with preset values pre-filled
3. User can edit: name, instructions (full markdown), governance settings, adapter config
4. Advanced users get full control, preset just seeds sensible defaults

### 3.3 Post-Instantiation

**Agent identity:**
- Agent name shows preset source: "AI Engineer (from The Agency)"
- Agent detail page has "Based on preset" badge with link to source
- Instructions field contains full Agency markdown (editable)

**Governance status:**
- Trust score, circuit breaker status, audit trail visible in agent detail
- Users can adjust governance settings post-creation if needed

---

## 4. Technical Architecture

### 4.1 Data Model

**New table: `agent_presets`**

```sql
CREATE TABLE agent_presets (
  id UUID PRIMARY KEY,
  source TEXT NOT NULL,              -- 'the-agency', 'community', 'custom'
  source_url TEXT,                   -- GitHub file URL
  division TEXT NOT NULL,            -- 'engineering', 'design', etc.
  name TEXT NOT NULL,                -- 'AI Engineer'
  description TEXT NOT NULL,
  color TEXT,                        -- Hex color from YAML front matter
  instructions_markdown TEXT NOT NULL, -- Full agent markdown
  capabilities JSONB,                -- Parsed capabilities for search/filter
  success_metrics JSONB,             -- Parsed metrics
  metadata JSONB,                    -- Version, last_synced, etc.
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_agent_presets_division ON agent_presets(division);
CREATE INDEX idx_agent_presets_source ON agent_presets(source);
```

**Link presets to agents:**

```sql
ALTER TABLE agents ADD COLUMN preset_id UUID REFERENCES agent_presets(id);
```

### 4.2 Format Mapping

**The Agency markdown → Agency-OS agent config:**

| The Agency Field | Agency-OS Equivalent | Mapping Logic |
|------------------|---------------------|---------------|
| YAML `name` | `agent.name` | Direct copy (user can customize) |
| YAML `description` | `agent.title` | Direct copy |
| YAML `color` | `agent.icon` metadata | Store as metadata, use for UI |
| Full markdown | `agent.adapterConfig.instructionsFilePath` | Write to temp file, set path, or inline in config |
| Success Metrics section | `agent.metadata.success_metrics` | Parse and store as JSON for display |
| Core Capabilities section | `agent.metadata.capabilities` | Parse for search/filter |

**Governance wrapping:**

Every preset agent gets default governance preset (Balanced):
- Trust threshold: Medium (0.5)
- Circuit breaker: 5 failures per 10 tasks
- Audit probability: 0.1
- Tax rate: 0.05

Users can override via UI or API.

### 4.3 API Endpoints

**Read presets:**
```
GET /api/v1/presets
GET /api/v1/presets/:id
GET /api/v1/presets/divisions
```

Query params: `division`, `search`, `limit`, `offset`

**Instantiate from preset:**
```
POST /api/v1/agents/from-preset
{
  "presetId": "uuid",
  "name": "My AI Engineer",
  "governancePreset": "balanced",
  "budgetMonthlyCents": 10000,
  "adapterConfig": { ... }  // Optional overrides
}
```

Returns created agent with `preset_id` set.

**Sync presets (admin only):**
```
POST /api/v1/presets/sync
{
  "source": "the-agency"  // Fetches latest from GitHub, updates DB
}
```

Runs as background job, updates `agent_presets` table.

---

## 5. MVP Scope

### Must Have (v1)

**Backend:**
- [ ] `agent_presets` table migration
- [ ] Sync script to import The Agency's 61 agents from GitHub
- [ ] `GET /api/v1/presets` with division filtering
- [ ] `POST /api/v1/agents/from-preset` instantiation endpoint
- [ ] Write preset markdown to agent instructions file

**Frontend:**
- [ ] Agent presets browse page (`/presets`)
- [ ] Division filtering UI
- [ ] Preset detail modal with preview
- [ ] "Create Agent" button → instantiation flow
- [ ] Agent detail page shows "Based on preset" badge

**Governance:**
- [ ] Default Balanced preset applied to all instantiated agents
- [ ] Trust scoring works out of the box
- [ ] Audit trail captures preset source

**Documentation:**
- [ ] API reference for preset endpoints
- [ ] User guide: "Using Agent Presets"
- [ ] Attribution to The Agency (MIT license compliance)

### Nice to Have (v2)

- [ ] Advanced filtering (by capability, success metric thresholds)
- [ ] Search with fuzzy matching across name/description/capabilities
- [ ] Custom presets (users can save their own agent templates)
- [ ] Preset versioning (track updates from The Agency)
- [ ] Community presets (user-contributed agent templates)
- [ ] Preset analytics (which presets are most popular?)

### Out of Scope

- ❌ Auto-syncing presets (manual admin trigger for v1)
- ❌ Preset marketplace or pricing
- ❌ Runtime agent swapping (changing preset after instantiation)
- ❌ Multi-preset composition (combining multiple presets into one agent)

---

## 6. Success Metrics

### Adoption Metrics

**Primary:**
- **Preset usage rate**: % of new agents created from presets (target: 60%+)
- **Time to first agent**: Median time from signup to first agent created (target: <5 min with presets vs ~20 min custom)

**Secondary:**
- Most popular presets (top 10)
- Division preference distribution
- Customization rate (% who customize vs one-click)

### Quality Metrics

**Engagement:**
- Agents created from presets have 30%+ higher retention (still active after 7 days)
- Task success rate for preset agents >= custom agents

**Trust/Governance:**
- Circuit breaker trigger rate is same or lower for preset agents (proves governance works)
- No security incidents from preset agents (validates our governance wrapper)

### Business Impact

- **Activation rate increase**: % of signups who create at least one agent (target: +20%)
- **Paid conversion**: Preset users convert to paid at higher rate (hypothesis)
- **NPS lift**: Users who use presets have higher NPS (survey)

---

## 7. Implementation Plan

### Phase 1: Data & Sync (Week 1)
1. Create `agent_presets` table migration
2. Build sync script to fetch The Agency markdown files from GitHub
3. Parse YAML front matter + markdown sections
4. Seed database with all 61 agents
5. Add `preset_id` foreign key to `agents` table

### Phase 2: API (Week 1-2)
1. `GET /api/v1/presets` with filtering
2. `POST /api/v1/agents/from-preset` endpoint
3. Governance preset application logic
4. Write instructions to file or inline config
5. Unit tests for all endpoints

### Phase 3: Frontend (Week 2-3)
1. `/presets` browse page with division cards
2. Preset detail modal
3. Instantiation form (name, governance, budget)
4. Integration with agent creation flow
5. Agent detail page preset badge

### Phase 4: Docs & Launch (Week 3)
1. API reference docs
2. User guide with examples
3. MIT license attribution page
4. Changelog entry
5. Launch announcement

**Total: 3 weeks for MVP**

---

## 8. Dependencies & Risks

### Technical Dependencies

- ✅ GitHub API access (no auth needed for public repos)
- ✅ Agent creation API already exists
- ✅ Governance presets already exist
- ⚠️ Need to decide: inline markdown vs file path for instructions

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| The Agency updates their format | Medium | Version preset schema, write robust parsers |
| Markdown too large for DB inline storage | Low | Use file path pattern, store in agent dirs |
| Users expect runtime behavior changes | Medium | Clear messaging: presets seed config, governance provides safety |
| License compliance concerns | Low | Prominent attribution, MIT license allows commercial use |
| Preset quality varies | Medium | Curate high-quality subset for v1, add quality ratings in v2 |

### Open Questions

1. **Storage:** Inline markdown in DB vs file system paths?
   **Recommendation:** File system for flexibility, DB for metadata/search.

2. **Updates:** How do users get preset updates after instantiation?
   **Recommendation:** v1 = no updates (agent config is independent post-creation). v2 = opt-in sync.

3. **Customization:** How much do we let users edit preset markdown?
   **Recommendation:** Full edit access. Preset is just a starting point.

4. **Branding:** Do we co-brand with The Agency?
   **Recommendation:** Yes. "Powered by The Agency" badge, link to their repo, respect their community.

---

## 9. Future Iterations

### v2: Enhanced Discovery
- Search with semantic matching
- Filtering by capabilities, tools, frameworks
- "Recommended for you" based on company type
- Preset ratings and reviews

### v3: Custom Presets
- Users can save their agent configs as custom presets
- Share presets within organization
- Export/import preset JSON

### v4: Community Marketplace
- User-contributed presets
- Preset quality scoring
- Featured presets spotlight
- Preset collections (e.g., "Startup Marketing Stack")

### v5: Preset Composition
- Combine multiple presets into hybrid agent
- "Frontend Developer + Security Engineer" merge logic
- Capability union, rule conflict resolution

---

## 10. Trust Model Cross-Pollination (Research)

**The Agency's approach:**
- Penalty-based scoring (start at 1.0, deduct for failures)
- Evidence-based verification (no self-reported signals)
- Credential freshness decay
- Cryptographic delegation chains

**Our approach:**
- Rolling success rate from task outcomes
- P5/P50/P95 percentiles for performance
- Tier thresholds (high ≥0.85, medium ≥0.50, low <0.50)

**Research opportunity:**
Compare penalty-based vs rolling-average models. Could we:
1. Start agents at 1.0 (trusted) vs 0.5 (neutral)?
2. Add credential freshness decay to our trust model?
3. Implement evidence chains for audit trails?

Recommend: ZERA follow-up issue for trust model research, separate from MVP integration.

---

## Appendix: Example Preset

**Frontend Developer from The Agency:**

```yaml
---
name: Frontend Developer
description: React/Vue/Angular specialist focused on pixel-perfect UI implementation, performance optimization, and modern web best practices.
color: "#e44d26"
---

# Frontend Developer Agent

You are a **Frontend Developer**, a React/Vue/Angular specialist focused on...

[Full markdown continues with Identity, Mission, Capabilities, Workflow, etc.]
```

**Maps to Agency-OS agent:**

```json
{
  "name": "Frontend Developer",
  "title": "React/Vue/Angular specialist...",
  "role": "general",
  "reportsTo": "<user's agent manager>",
  "adapterType": "claude_local",
  "adapterConfig": {
    "instructionsFilePath": "agents/frontend-developer/AGENTS.md",
    "cwd": "/path/to/project"
  },
  "metadata": {
    "preset_id": "uuid",
    "preset_source": "the-agency",
    "color": "#e44d26"
  },
  "budgetMonthlyCents": 10000
}
```

With governance preset "Balanced" applied automatically.

---

## Sign-Off

- [ ] Engineering review (feasibility, 3-week estimate)
- [ ] Design review (UI mocks for browse + instantiation)
- [ ] CEO approval (strategic fit, prioritization)
- [ ] Legal review (MIT license compliance, attribution)

**Next Steps:**
1. Circulate PRD for feedback
2. Create ZERA sub-issues for Phase 1-4
3. Assign to engineering for estimation
4. Design UI mocks for `/presets` page
