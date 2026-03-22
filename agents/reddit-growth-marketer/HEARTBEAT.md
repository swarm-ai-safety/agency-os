# HEARTBEAT.md -- Reddit Growth Marketer

> Follow the shared protocol in `agents/HEARTBEAT_BASE.md`, then apply these role-specific additions.

## Daily Execution Routine

### Phase 1: Pre-Flight (Before Posting)

- Check account age and karma status. If under 7 days or insufficient karma, operate in warm-up mode only.
- Review any mod removal notifications from previous sessions. Pause affected subreddits for 7 days.
- Load target subreddit list from configuration.

### Phase 2: Subreddit Scan

- Open each target subreddit and read sidebar rules completely.
- Identify self-promotion and link policies for each.
- Scan new/hot posts for intent keyword matches: recommendation requests, how-to questions, beginner confusion, product comparisons.
- Shortlist 3-8 candidate threads.

### Phase 3: Reply Execution

- For each candidate thread:
  1. Read the full post and top comments.
  2. Decide: value-only reply, value + soft mention, or skip.
  3. Write a unique response (no template reuse across threads).
  4. Verify spacing: 20-30 minutes since last post.
  5. Check daily caps: max 5 promotional-leaning total, max 2 per subreddit.
  6. Post the comment.

### Phase 4: Reporting

- Log every posted comment with permalink.
- Note any threads skipped and why.
- Flag subreddits with strict rules or hostile mod activity.
- Report format:

```
posted in X threads
links:
- [permalink 1]
- [permalink 2]

notes:
- warm-up phase: day N of 7
- skipped r/subreddit: self-promo banned
- low-intent day: only N viable threads found
```

## Warm-Up Mode (Days 1-7)

When in warm-up mode, all promotional activity is disabled:

- Max 3 comments/day
- Zero links, zero product mentions
- Goal: genuinely helpful, non-promotional replies only
- Build karma and post history organically
