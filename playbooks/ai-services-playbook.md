# AI Services Playbook: Zero Human Ops-as-a-Service

> Turn repetitive business operations into autonomous AI systems. Charge to build. Charge monthly to run. Scale to $240K+/year.

---

## The Model

You are not a freelancer. You are not an agency. You sell **the permanent elimination of work**.

- **Setup fee**: $3K-8K (one-time, covers discovery + build + deployment)
- **Monthly retainer**: $1.5K-3K/mo (monitoring, maintenance, iteration)
- **Unit economics**: 10 clients at $2K/mo avg = $240K/year recurring, plus $30K-80K in setup fees
- **Margin**: 80%+ once systems stabilize (agents run themselves, you monitor dashboards)

---

## Phase 1: Target Selection (Week 1)

### Find the right company

**Ideal client profile:**
- 10-200 employees (big enough to have the problem, small enough that you talk to the decision-maker)
- Operations-heavy: agencies, law firms, property management, logistics, e-commerce, healthcare admin, accounting firms, recruiting
- Already paying $4K+/mo in labor for the task you'll automate
- Tech-tolerant but not tech-native (they won't build it themselves)

**Where to find them:**
- LinkedIn: search for ops managers posting about being "buried" or "drowning"
- Reddit/Twitter: founders complaining about back-office work
- Upwork/Fiverr: look at what people are hiring VAs and contractors for repeatedly
- Your network: ask "what does your team do 50+ times a week that everyone hates?"

### Find the right task

**The sweet spot: too messy for Zapier, too repetitive for talent.**

| Category | Example Tasks | Typical Volume |
|---|---|---|
| **Lead research** | Enrich inbound leads with firmographics, tech stack, intent signals, draft personalized outreach | 200-500/week |
| **Client reporting** | Pull data from 3-5 sources, format into branded reports, email to clients | 20-50/week |
| **Content repurposing** | Take one long-form piece, produce 10 social posts, 3 email snippets, 1 summary | 5-15/week |
| **Invoice routing** | Receive invoices (email/PDF), extract fields, match to PO, route for approval, enter into books | 100-300/week |
| **Recruiting screening** | Parse resumes, score against JD, draft rejection/advancement emails | 50-200/week |
| **Support triage** | Classify tickets, draft responses for L1, escalate L2+, update CRM | 100-500/week |
| **Compliance monitoring** | Scan regulatory feeds, flag relevant changes, draft impact summaries | Daily |

**Qualification checklist:**
- [ ] Task happens 50+ times/week (volume = value)
- [ ] Currently done by humans who hate it (pain = urgency)
- [ ] Output is structured or semi-structured (buildable)
- [ ] Error rate is already high (AI can match or beat)
- [ ] No deep domain judgment required (80/20 rule: automate 80%, human-in-loop for 20%)
- [ ] Client can quantify current cost ($X/mo in labor or outsourcing)

---

## Phase 2: Discovery & Scoping (Week 2)

### The discovery call (45 min)

**Questions to ask:**
1. Walk me through exactly how [task] works today. Step by step.
2. How many times per week/day does this happen?
3. Who does it? How long does it take them per unit?
4. What are the inputs? (Email? Spreadsheet? CRM? Slack message?)
5. What are the outputs? (Report? Email? Database entry? Slack notification?)
6. What goes wrong? Where do errors happen?
7. What's this costing you? (Salary + overhead + opportunity cost)
8. If this just... worked... what would your team do with that time instead?

**What you're listening for:**
- Clear input → transformation → output pattern
- Identifiable data sources and destinations
- Pain that's costing real money (>$4K/mo)
- A decision-maker who can say yes in <2 weeks

### Scope document (1 page)

```
SYSTEM: [Name] — [Client Company]

TRIGGER: [What kicks off the task — email, schedule, webhook, Slack message]
INPUT:   [Data sources — CRM, email, spreadsheet, API]
PROCESS: [Step-by-step what the AI system does]
OUTPUT:  [What gets produced — report, email, database entry, notification]
HUMAN:   [What still needs a human — edge cases, approvals, exceptions]

VOLUME:  [X per week]
SLA:     [Turnaround time — e.g., "within 15 minutes of trigger"]
NOTIFY:  [Where results land — Slack channel, email, dashboard]

CURRENT COST:  $X,XXX/mo
OUR PRICE:     $X,XXX setup + $X,XXX/mo
CLIENT SAVING: $X,XXX/mo net
```

---

## Phase 3: Build (Weeks 3-4)

### Architecture (Agency-OS stack)

Every system follows the same pattern:

```
[Trigger] → [Ingestion Agent] → [Processing Agent(s)] → [Output Agent] → [Notify]
     ↑                                                          ↓
  Governance Layer (trust scores, circuit breakers, audit trail)
```

**Using Agency-OS:**

1. **Define agents in YAML** — one agent per discrete step. Keep them small and single-purpose.
2. **Set governance presets** — conservative for anything touching client data, balanced for internal processing.
3. **Wire trust scores** — new systems start conservative, earn autonomy as success rate proves out.
4. **Configure metering** — track token usage per agent per task. This is your cost basis.
5. **Set circuit breakers** — if error rate spikes above threshold, halt and notify you.

**Build checklist:**
- [ ] Trigger mechanism working (webhook, email parser, cron, Slack listener)
- [ ] Input ingestion tested with real client data (10+ samples)
- [ ] Processing pipeline produces correct output on 90%+ of samples
- [ ] Edge case routing to human-in-loop (Slack ping with context)
- [ ] Output delivery working (email, CRM update, Slack, whatever)
- [ ] Monitoring dashboard: success rate, latency, cost per unit
- [ ] Circuit breaker tested (force a failure, verify it halts)
- [ ] Governance audit trail capturing every agent action

### Testing protocol

1. **Shadow mode (3-5 days)**: System runs in parallel with human. Compare outputs. Fix discrepancies.
2. **Supervised mode (5-7 days)**: System handles live work. Human spot-checks 20% of outputs.
3. **Autonomous mode**: System runs. Human reviews exceptions only. Slack notification on completion.

---

## Phase 4: Deploy & Handoff (Week 5)

### Client deliverables

1. **System documentation** — what it does, how it works, what triggers it
2. **Monitoring dashboard** — success rate, volume processed, cost savings
3. **Escalation protocol** — when and how the system escalates to a human
4. **Slack integration** — completion notifications, error alerts, daily summary

### Go-live checklist
- [ ] Client team trained on escalation workflow
- [ ] Slack channel created for system notifications
- [ ] Monitoring alerts configured (you get paged on failures)
- [ ] First invoice sent (setup fee)
- [ ] Monthly billing set up (retainer starts)
- [ ] 30-day review meeting scheduled

---

## Phase 5: Run & Scale (Ongoing)

### Monthly retainer covers

- System monitoring and uptime
- Handling edge cases and system updates
- Monthly performance report to client
- Iterative improvements (prompt tuning, new edge cases, volume scaling)
- Infrastructure costs (compute, API calls, storage)

### Your weekly routine per client (30-60 min)

1. Check dashboard: success rate, error rate, volume trends
2. Review any escalated edge cases
3. Tune prompts or logic if error patterns emerge
4. Update client if anything notable happened

### Scaling to 10+ clients

**The leverage point:** Most of the work is in Phase 2-4 (discovery + build). Once a system is running, it costs you <1 hr/week per client. Your constraint is sales pipeline, not delivery capacity.

**Productize common patterns:**
- After building 2-3 "lead research" systems, you have a template. Client 4 is 60% faster to deploy.
- After 2-3 "client reporting" systems, same thing.
- Build a library of reusable agent configs, governance presets, and integration adapters.

**Hire when:**
- You're turning away clients (pipeline > capacity)
- You're spending >50% of time on build vs. sales
- A specific vertical is taking off (hire a domain specialist)

---

## Pricing Framework

| Complexity | Setup Fee | Monthly | Example |
|---|---|---|---|
| **Simple** (1-2 agents, single data source) | $3K | $1.5K | Email triage, content repurposing |
| **Medium** (3-5 agents, multiple data sources) | $5K | $2K | Lead research + outreach, invoice routing |
| **Complex** (5+ agents, integrations, compliance) | $8K+ | $3K+ | Compliance monitoring, multi-step recruiting pipeline |

**Pricing justification:** "You're currently paying $6K/mo for a person to do this. Our system does it for $2K/mo, faster, 24/7, with zero sick days. That's $48K/year in savings."

---

## Why Agency-OS Is the Platform for This

This isn't about writing scripts or chaining API calls. It's about deploying **governed, observable, trustworthy AI systems** that clients can rely on for critical operations.

What Agency-OS gives you that scripts don't:
- **Governance presets** — audit trails, circuit breakers, trust scoring. Clients trust it because there are guardrails.
- **Agent orchestration** — multi-agent pipelines with proper lifecycle management.
- **Metering** — exact cost per task, per agent. You know your margins.
- **Trust scores** — systems start conservative, earn autonomy. Clients see the system getting better.
- **Tenant isolation** — run 10 clients on one platform without data leakage.

**The pitch to clients:** "This isn't a chatbot. It's a governed AI operations system with audit trails, circuit breakers, and trust scoring. It's the difference between a script and infrastructure."

---

## Quick-Start: Your First Client in 30 Days

| Week | Action |
|---|---|
| **1** | Reach out to 20 companies. Book 5 discovery calls. |
| **2** | Run discovery. Pick the best fit. Send scope + proposal. |
| **3** | Build the system. Test with real data in shadow mode. |
| **4** | Supervised deployment. Daily check-ins with client. |
| **5** | Go autonomous. Send first invoice. Start prospecting for client #2. |

---

## Red Flags (Walk Away)

- Client can't articulate the task clearly (if they can't explain it, you can't automate it)
- Task requires deep domain judgment with no clear rules (legal strategy, creative direction)
- Client expects 100% automation day one (manage expectations or walk)
- Budget is <$1.5K/mo (not worth your time at this stage)
- No decision-maker in the room (you'll get stuck in committee)
- They want to own the system, not the outcome (you're selling a service, not software)
