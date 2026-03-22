# Agency-OS Pricing

MRR-first pricing for paid tiers. The Free Demo is a one-time guided onboarding run, then upgrade to continue. No seat licenses. No per-agent fees.

---

## Plans

### Free Demo

Free Demo — $0 one-time onboarding: we set up the basics and run one example workflow on open-source models. Upgrade required for continued usage.

- 1 agent
- Guided setup included
- 1 example workflow run
- Open-source model pool for demo run
- Smart routing (model="auto")
- Balanced governance preset
- Real-time metering
- Community support

**Limits:**
- No recurring monthly token bucket
- Upgrade required after demo run
- No failover or eval harness
- Single governance preset

### Pro -- $49/month + usage

For teams running production agent workflows.

- Unlimited agents
- 1M tokens/month included
- All governance presets (conservative, balanced, aggressive)
- Cross-provider failover
- Eval harness (5 dimensions: toxicity, relevance, quality, hallucination, factuality)
- Trust score monitoring
- Per-agent budget caps
- Priority support
- 10% volume discount on overages

### Enterprise -- Custom

For organizations that need dedicated infrastructure and compliance controls.

- Everything in Pro
- Custom governance profiles
- Dedicated tenant isolation
- SLA guarantees
- SSO/SAML
- Audit log export
- Volume pricing (negotiated)
- Dedicated support channel

---

## Model Pricing

All token prices are per 1M tokens. Prices include platform margin. You choose the model; we handle routing, failover, caching, and metering.

### OpenAI Models

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|---|---|---|
| GPT-4o | $3.25 | $13.00 |
| GPT-4.1 | $2.60 | $10.40 |
| GPT-4.1 Mini | $0.52 | $2.08 |
| GPT-4o Mini | $0.26 | $1.01 |
| GPT-4.1 Nano | $0.13 | $0.52 |

### Anthropic Models

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|---|---|---|
| Claude Opus 4 | $19.50 | $97.50 |
| Claude Opus 4.5 | $6.50 | $32.50 |
| Claude Opus 4.6 | $6.50 | $32.50 |
| Claude Sonnet 4 | $3.90 | $19.50 |
| Claude Sonnet 4.5 | $3.90 | $19.50 |
| Claude Sonnet 4.6 | $3.90 | $19.50 |
| Claude Haiku 3.5 | $1.04 | $5.20 |
| Claude Haiku 4.5 | $1.30 | $6.50 |

Prices reflect a 30% platform margin over provider costs. This margin covers routing, failover, caching, governance, metering, and eval infrastructure.

---

## Agent Execution Pricing

Beyond raw token costs, agent tasks incur a small execution fee that covers orchestration, governance evaluation, trust scoring, and audit logging.

| Action | Price |
|---|---|
| Agent task (single model call + governance) | $0.01 |
| Agent workflow (multi-step pipeline) | $0.05 |
| Sandbox simulation (governance wind-tunnel test) | $0.10 |

Execution fees are additive to token costs. Example: an agent workflow that consumes 50K input tokens and 10K output tokens on Claude Sonnet 4 costs:

- Tokens: (50K / 1M x $3.90) + (10K / 1M x $19.50) = $0.195 + $0.195 = $0.39
- Execution: $0.05
- **Total: $0.44**

---

## What's Included at Every Tier

- **Smart routing** -- requests routed to the right model and provider automatically
- **Cross-provider failover** -- if one provider is down, requests fail over seamlessly (Pro+)
- **Response caching** -- identical prompts served from cache at zero token cost
- **Real-time metering** -- per-agent, per-tenant token and cost tracking
- **Governance presets** -- configurable audit probability, circuit breakers, and transaction tax rates
- **Trust scoring** -- rolling agent reliability scores that auto-adjust governance strictness
- **Task-type classification** -- automatic governance selection based on task complexity
- **Eval harness** -- 5-dimension evaluation (toxicity, relevance, quality, hallucination, factuality) (Pro+)

---

## Volume Discounts

| Monthly Token Usage | Discount |
|---|---|
| Under 1M tokens | -- |
| 1M -- 10M tokens | 10% |
| 10M -- 100M tokens | 20% |
| 100M+ tokens | Custom (contact sales) |

Volume discounts apply to token costs only, not execution fees.

---

## Billing

- Billed monthly via Stripe
- Usage metered in real-time, invoiced at period end
- Self-service billing portal for plan changes, payment methods, and invoice history
- All prices in USD

---

## FAQ

**Do I pay per agent?**
No. You pay for token consumption and task execution. Run as many agents as your plan allows.

**What happens if a provider is down?**
On Pro and Enterprise plans, requests automatically fail over to an equivalent model on a different provider. You pay the token rate of the model that actually serves the request.

**How does caching affect my bill?**
Cached responses cost zero tokens. You only pay for requests that hit a model provider.

**Can I set budget limits per agent?**
Yes. Agency-OS supports per-agent budget caps. When an agent hits its limit, it pauses until the next billing period or until you raise the cap.

**Can I use my own API keys (BYOK)?**
Default plans use Agency-OS managed model access and billing. BYOK is available as an enterprise exception on custom plans.

**What governance preset should I use?**
- **Conservative**: high audit rates, strict circuit breakers. Best for regulated environments.
- **Balanced**: moderate controls. Good default for production workloads.
- **Aggressive**: minimal oversight, maximum throughput. Use for trusted agents on low-risk tasks.

Trust scores adjust governance automatically -- high-trust agents get lighter oversight, low-trust agents get stricter controls.
