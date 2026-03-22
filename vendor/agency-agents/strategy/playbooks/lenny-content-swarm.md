# Lenny Content Swarm — Playbook

> **Package**: `lenny-content-swarm` | **Agents**: 7 (3 retrievers, 2 analysts, 1 critic, 1 synthesizer) | **Dataset**: Lenny's Newsletter + Podcast Archive

---

## Objective

Run a multi-agent swarm over Lenny's content dataset to answer product questions, extract frameworks, and demonstrate distributional AI safety principles (competing agents, critic evaluation, convergence tracking).

## Pre-Conditions

- [ ] Dataset cloned: `git clone https://github.com/LennysNewsletter/lennys-newsletterpodcastdata.git data/lenny`
- [ ] Index built: `python scripts/lenny_ingest.py --data-dir data/lenny`
- [ ] Package validated: `agency-os validate agency_os/packages/library/lenny_content_swarm.yaml`

---

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────┐
│     RETRIEVER SWARM (×3)    │  ← Compete on search strategy
│  A: Broad    B: Focused     │
│  C: Cross-type diversity    │
└──────────┬──────────────────┘
           │ Reciprocal Rank Fusion
           ▼
┌─────────────────────────────┐
│     ANALYST SWARM (×2)      │  ← Compete on answer quality
│  A: Direct answer style     │
│  B: Synthesis style         │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│     CRITIC (×1)             │  ← Scores groundedness, relevance,
│  Evaluate all analyst       │     completeness, citation accuracy
│  outputs                    │
└──────────┬──────────────────┘
           │ Pass / Revise / Reject
           ▼
┌─────────────────────────────┐
│     SYNTHESIZER (×1)        │  ← Fuses best outputs into
│  Final answer + telemetry   │     final answer with provenance
└─────────────────────────────┘
```

---

## Workflow: `swarm_query`

### Stage 1: Retrieve

**Agents**: 3× Content Retriever (competing strategies)

Each retriever runs independently with a different approach:

| Retriever | Strategy | Parameters |
|-----------|----------|------------|
| A | Hybrid (BM25 + metadata boost) | `limit=10`, no type filter |
| B | Focused (BM25, tight limit) | `limit=5`, respect user type filter |
| C | Diversity (cross-type search) | `limit=5`, opposite content type |

**Output**: 3 ranked result lists → fused via Reciprocal Rank Fusion (RRF)

**Quality gate**: At least 3 unique chunks after fusion.

### Stage 2: Analyze

**Agents**: 2× Content Analyst (competing answer styles)

Each analyst receives the fused retrieval results and generates an answer:

| Analyst | Style | Focus |
|---------|-------|-------|
| A | Direct answer | Lead with the answer, cite 2-3 sources |
| B | Synthesis report | Theme-organized, multi-source comparison |

**Output**: 2 candidate answers with citations and confidence scores.

### Stage 3: Critique

**Agent**: 1× Content Critic

Evaluates both analyst answers on:
- **Groundedness** (0-1): Are claims supported by sources?
- **Relevance** (0-1): Does the answer address the question?
- **Completeness** (0-1): Are important perspectives covered?
- **Citation accuracy** (0-1): Are references correct?

**Output**: Structured evaluation per analyst answer. Verdict: pass / revise / reject.

**Quality gate**: At least 1 analyst answer must pass (composite ≥ 0.8).

### Stage 4: Synthesize

**Agent**: 1× Content Synthesizer

Takes passing analyst answers + critic feedback → produces final response:
- Fused answer combining best elements
- Full citation provenance chain
- Swarm telemetry (variance, pass rate, source diversity)

---

## Workflow: `framework_extraction`

Specialized variant for extracting mental models and decision frameworks.

### Differences from `swarm_query`:
- Retrievers use broader search (limit=15)
- Analysts use Style C: Framework Report (name, describe, cite, compare each framework)
- Critic has stricter completeness threshold (must cover ≥3 sources)
- Synthesizer produces structured framework catalog

### Example queries:
- "What frameworks does Lenny recommend for measuring product-market fit?"
- "How do podcast guests think about B2B onboarding?"
- "What mental models recur across both newsletters and podcasts?"

---

## Swarm Telemetry

Every query run produces telemetry that maps to SWARM distributional safety metrics:

| Metric | What it measures | SWARM equivalent |
|--------|-----------------|-----------------|
| Answer variance | How much analysts disagreed | Coordination quality |
| Critic pass rate | % of answers passing evaluation | System reliability |
| Source diversity | Content types used in final answer | Exploration breadth |
| Retriever hit overlap | How much retrievers agreed on results | Convergence signal |
| Synthesis rounds | How many revise cycles before pass | Governance overhead |

### Failure mode detection:
- **Mode collapse**: All retrievers return identical results → diversity penalty needed
- **Hallucination cascade**: One bad retrieval → all analysts hallucinate → critic catches
- **Over-criticism**: Critic rejects valid answers → calibrate thresholds
- **Source monoculture**: Final answer cites only 1 source → completeness flag

---

## Quick Start

```bash
# 1. Clone the dataset
git clone https://github.com/LennysNewsletter/lennys-newsletterpodcastdata.git data/lenny

# 2. Ingest and index
python scripts/lenny_ingest.py --data-dir data/lenny

# 3. Interactive query (single-agent baseline)
python scripts/lenny_query.py --index build/lenny.idx

# 4. Interactive query (swarm mode)
python scripts/lenny_query.py --index build/lenny.idx --swarm

# 5. Filter to podcasts only
python scripts/lenny_query.py --index build/lenny.idx --swarm --type podcast

# 6. Run via agency-os package
agency-os run lenny-content-swarm --task "What frameworks exist for product-market fit?"
```

---

## Zero-Human Company Extension

This swarm becomes a building block for the zero-human company when you:

1. **Replace manual queries with idea agents** that generate questions from the dataset
2. **Add validation agents** that check extracted insights against external sources
3. **Add builder agents** that turn frameworks into landing pages / tools
4. **Add feedback loops** where output quality feeds back into agent selection

The key insight: the Lenny dataset provides the **knowledge substrate** (compressed product wisdom), while the swarm architecture provides the **coordination layer** (competing agents, critic evaluation, evolutionary selection). Together they form the foundation of an autonomous product-building system.

---

## License Notes

The Lenny starter dataset is for personal, non-commercial use. You can study it, build tools on top of it, and publish projects using it. You cannot redistribute the raw files or use raw contents commercially. Check `LICENSE.md` in the dataset repo for full terms.
