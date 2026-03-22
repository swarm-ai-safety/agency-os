# Issue Labeling Guide

## Overview

Labels help us categorize, filter, and prioritize work. Every issue should have at least one **type** label. Add **area** and **modifier** labels when relevant.

## Label Taxonomy

### Type Labels (Required — pick one)

| Label | When to Use | Color |
|-------|-------------|-------|
| `type:feature` | New features, capabilities, or enhancements | Green `#0E8A16` |
| `type:bug` | Bug fixes, error corrections, broken functionality | Red `#D73A4A` |
| `type:research` | Research, analysis, competitive intelligence, investigation | Blue `#0075CA` |
| `type:docs` | Documentation, guides, READMEs, API docs | Purple `#5319E7` |
| `type:infra` | Infrastructure, tooling, CI/CD, platform work | Light Blue `#C5DEF5` |

### Area Labels (Optional — pick all that apply)

| Label | When to Use | Color |
|-------|-------------|-------|
| `area:marketing` | Marketing, growth, content, campaigns, SEO | Yellow `#FBCA04` |
| `area:product` | Product features, UI/UX, design, frontend | Pink `#F9D0C4` |
| `area:governance` | Governance, trust, safety, security, auditing | Soft Blue `#BFD4F2` |
| `area:billing` | Billing, payments, Stripe, pricing | Lavender `#D4C5F9` |

### Modifier Labels (Optional — add when relevant)

| Label | When to Use | Color |
|-------|-------------|-------|
| `blocker` | Blocks other work, launch, or critical paths | Dark Red `#B60205` |
| `good-first-issue` | Good for new team members or contributors | Bright Purple `#7057FF` |
| `needs-approval` | Waiting on board approval or external gate | Soft Red `#E99695` |
| `duplicate` | Duplicate of another issue (close with reference) | Gray `#CFD3D7` |

## Examples

### Well-Labeled Issues

```
[ZERA-130] Project and goal detail endpoints return 500 errors
Labels: type:bug, area:product, blocker

[ZERA-135] If agents start consuming developer infra at scale...
Labels: type:research, area:product

[ZERA-38] Fix waitlist form (localhost hardcoded)
Labels: type:bug, area:marketing

[ZERA-114] Pricing drift between docs and site
Labels: type:bug, area:billing, area:product
```

## Auto-Labeling

The CEO runs auto-labeling on new issues based on keywords:

- **Type** — detected from title/description keywords
- **Area** — inferred from domain terms (marketing, governance, etc.)
- **Modifiers** — applied based on priority (critical → blocker) or status (approval → needs-approval)

If auto-labeling misses or mislabels, manually update via the Paperclip API:

```bash
curl -X PATCH "$PAPERCLIP_API_URL/api/issues/{issueId}" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"labelIds": ["<label-id-1>", "<label-id-2>"]}'
```

## Filtering by Labels

Use the `labelId` query parameter to filter issues:

```bash
# All bugs
GET /api/companies/{companyId}/issues?labelId={type:bug-id}

# Marketing bugs
GET /api/companies/{companyId}/issues?labelId={type:bug-id}&labelId={area:marketing-id}

# Blockers
GET /api/companies/{companyId}/issues?labelId={blocker-id}&status=todo,in_progress
```

## Best Practices

1. **Always add a type label** — every issue needs one
2. **Use area labels for cross-functional work** — helps with ownership and routing
3. **Mark blockers aggressively** — if it blocks something, tag it
4. **Don't over-label** — 2-3 labels per issue is usually enough
5. **Update labels as issues evolve** — a research task might become a feature task
6. **Use `duplicate` sparingly** — only when truly redundant, and link to the canonical issue

## Label Management

- Labels are company-wide (not per-project)
- CEO and managers can create new labels via API
- To propose a new label, comment on [ZERA-133](/issues/ZERA-133)

---

**Last updated:** 2026-03-08 (ZERA-133 — label system bootstrap)
