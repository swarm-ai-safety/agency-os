---
name: reddit-growth
description: Reddit community growth via authentic human-style engagement. Finds high-intent posts, checks subreddit rules, writes value-first replies, and reports run summaries. Works for any app, product, or service targeting a specific community.
version: "1.0"
generated_from: "reddit-growth-skill-v1"
user-invocable: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebFetch, WebSearch
context: fork
model: sonnet
argument-hint: "warmup | engage [subreddit-list] | report | status"
---

## EXECUTE NOW

**Target: $ARGUMENTS**

Parse immediately:
- `warmup` → warm-up mode: value-only comments, no promotion (Steps 1-4)
- `engage [subreddit-list]` → full engagement: value + soft product mentions (Steps 1-6)
- `report` → generate session report (Step 7)
- `status` → show account health and subreddit status (Step 8)
- Empty → show help with subcommand options

---

## WARMUP MODE: Steps 1-4 (Days 1-7 of new account)

### Step 1: Account Pre-Flight Check

Verify account readiness:
1. Check account age. If under 7 days, enforce warm-up constraints.
2. Review any mod removal history. Mark affected subreddits as paused (7-day cooldown).
3. Confirm daily comment count is under the cap (3 for warm-up, 5 for engage).

### Step 2: Subreddit Reconnaissance

For each target subreddit:
1. Read sidebar rules completely.
2. Identify self-promotion and link policies.
3. Skip if previously banned or removed.
4. Note posting restrictions (account age, karma minimums, flair requirements).

**Decision matrix:**
- Self-promo allowed → eligible for engage mode later
- Self-promo restricted → value-only replies, never mention product
- Self-promo banned → skip entirely in engage mode; value-only in warm-up

### Step 3: Intent Scanning

Scan new/hot posts for high-value threads:
1. Look for keyword matches: recommendation requests, "how do I", "best tool for", beginner questions, comparison threads.
2. Read full post and top comments before replying.
3. Skip: bait, trolls, polarized debates, promo-banned threads.
4. Shortlist 3-5 candidate threads.

### Step 4: Value-Only Replies (Warm-Up)

For each selected thread:
1. Write a genuinely helpful reply addressing the person's actual question.
2. **Zero product mentions.** Zero links. Pure value.
3. Keep it natural — match the subreddit's tone and conventions.
4. Every reply must be unique. No template reuse across threads.
5. Wait 20-30 minutes between posts.
6. Log the permalink.

**Warm-up constraints:**
- Max 3 comments/day
- No links of any kind
- No product, brand, or company mentions

---

## ENGAGE MODE: Steps 1-6 (After warm-up complete)

### Steps 1-3: Same as Warm-Up Mode

Execute Steps 1-3 identically. Reconnaissance and scanning are always required.

### Step 5: Choose Reply Type

For each candidate thread, decide:

| Signal | Action |
|--------|--------|
| Thread asks for recommendations and product fits | Value + soft mention |
| Thread is a how-to and product is a supporting tool | Value + soft mention |
| Thread is informational, product not relevant | Value-only reply |
| Thread bans promo or is in a restricted subreddit | Value-only reply or skip |
| Thread is bait, troll, or polarized | Skip entirely |

### Step 6: Write and Post Replies

For value + soft mention replies, follow the 80/20 rule:
1. **80%**: Direct, useful answer to the person's actual question. This must stand alone.
2. **20%**: Soft product mention, only when genuinely relevant. No marketing language, no hard CTAs.

**Four reply frameworks:**

**Product recommendation requests:**
- Acknowledge the need
- Provide evaluation criteria
- Mention product if relevant (with honest framing)
- Ask clarifying questions

**"How do I" questions:**
- Give the real method first
- Practical step-by-step routine
- Product as supporting tool only (if applicable)

**Beginner questions:**
- Reduce overwhelm first
- Provide one clear path
- Gentle mention if useful

**Skill-building requests:**
- Share structure and cadence
- Soft feature mention if applicable

**Posting rules:**
- Max 5 promotional-leaning comments/day total
- Max 2 comments/day per subreddit
- 20-30 minute spacing between posts
- Every reply must be unique — identical replies across threads are prohibited
- No marketing language: no "game-changing," "revolutionary," "best-in-class"

---

## REPORT MODE: Step 7

Generate a session report:

```
## Reddit Growth Session Report

**Date:** [today]
**Mode:** warmup | engage
**Account age:** N days

### Posted
posted in X threads
links:
- [r/subreddit - thread title](permalink)
- [r/subreddit - thread title](permalink)

### Skipped
- r/subreddit: reason (e.g., self-promo banned, low-intent day, mod removal cooldown)

### Subreddit Health
- r/subreddit: status (active | paused until date | restricted)

### Blockers
- [any issues preventing execution]

### Notes
- warm-up phase: day N of 7
- total promotional comments today: N/5
- subreddit-level counts: r/sub1 (N/2), r/sub2 (N/2)
```

---

## STATUS MODE: Step 8

Show account and subreddit health:

1. Account age and warm-up phase progress
2. Total karma (if trackable)
3. For each target subreddit:
   - Status: active, paused (with resume date), restricted
   - Last post date
   - Rule summary (promo policy)
   - Any mod actions

---

## Critical Constraints

1. **Browser/headless only.** No Reddit API, no PRAW, no automation libraries.
2. **Direct posting required.** Not draft-only — comments must be posted.
3. **Pre-post rule verification mandatory.** Read sidebar before every post session.
4. **Self-promotion restrictions honored.** If restricted: value-only or skip entirely.
5. **No identical replies.** Every comment is unique to its thread and context.
6. **Daily caps are hard limits.** Never exceed 5 promo comments or 2 per subreddit.
7. **Mod removal = 7-day pause.** No exceptions, no arguments with mods.
8. **Warm-up is non-negotiable.** New accounts must complete 7+ days before any promotional activity.
9. **One stable persona.** Maintain consistent username and positioning as community member.
10. **Never claim to be a brand rep** unless the subreddit explicitly allows it.
