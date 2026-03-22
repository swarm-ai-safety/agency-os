# Agency-OS API Reference

Complete reference for the Agency-OS REST API. Interactive OpenAPI docs are available at `/docs` when the server is running.

**Base URL:** `http://localhost:8000` (default)

---

## Authentication

All authenticated endpoints require the `X-API-Key` header with your tenant API key:

```bash
curl -H "X-API-Key: ak-your-key-here" http://localhost:8000/api/v1/orgs
```

API keys are issued once during tenant signup (`POST /api/v1/tenants`) and are never stored in plaintext — only a SHA-256 hash is persisted. If you lose your key, rotate it via `POST /api/v1/tenants/me/rotate-key`.

---

## Rate Limits

| Limit | Value | Scope |
|---|---|---|
| API requests | **60 per minute** | Per tenant (sliding window) |
| Tenant signups | **5 per hour** | Per IP address |
| Waitlist signups | **5 per hour** | Per IP address |
| Concurrent streams | **10** | Per tenant (gateway SSE) |

When a rate limit is exceeded, the API returns `429 Too Many Requests`.

### Free Demo Limits

| Limit | Value |
|---|---|
| Example workflow runs | **1 total** |
| Agent count | **1 agent** |
| Model pool | **Open-source models for the demo run** |

The free demo is one-time onboarding and does not reset monthly.

---

## Error Codes

All errors return JSON with a `detail` field:

```json
{ "detail": "Human-readable error message" }
```

| Status | Meaning | Common Causes |
|---|---|---|
| `400` | Bad Request | Invalid model name, validation failure, malformed input |
| `401` | Unauthorized | Missing `X-API-Key` header, invalid API key |
| `402` | Payment Required | No active subscription, payment past due, billing not set up |
| `403` | Forbidden | Tenant deactivated, model not available on your plan |
| `404` | Not Found | Organization, agent, task, or package does not exist |
| `409` | Conflict | API key already rotated (tenants) |
| `429` | Too Many Requests | Rate limit exceeded, budget limit hit |
| `500` | Internal Server Error | Unhandled exception (logged server-side) |
| `502` | Bad Gateway | Upstream LLM provider returned an error |
| `503` | Service Unavailable | Gateway not configured, Stripe not configured, database unavailable |

### Error Detail Strings

These are the exact `detail` values returned for common errors:

**Authentication & Billing:**
- `"Missing API key"` — No `X-API-Key` header provided
- `"Invalid API key"` — Key does not match any tenant
- `"Tenant is deactivated"` — Tenant has been disabled
- `"Payment required. Set up billing at /api/v1/billing/checkout"` — No Stripe customer
- `"Payment past due. Update billing at /api/v1/billing/portal"` — Invoice unpaid
- `"Active subscription required. Subscribe at /api/v1/billing/checkout"` — No active sub
- `"Free demo already used (1 example workflow run). Upgrade to Pro for continued usage: POST /api/v1/billing/checkout."` — Free demo exhausted

**Rate Limiting:**
- `"Rate limit exceeded: 60 requests per minute"` — Per-tenant RPM limit hit
- `"Request would exceed tenant budget limit"` — Gateway budget cap reached

**Validation:**
- `"Unknown model: {model}. Available: {list}"` — Invalid model ID in gateway request
- `"Model {model} not available for your plan"` — Tier restriction on model access

---

## Endpoints

### Health

These endpoints do not require authentication.

#### `GET /health`

Returns basic health status.

```bash
curl http://localhost:8000/health
```

```json
{ "status": "ok" }
```

#### `GET /health/detailed`

Returns health checks, uptime, and error rate stats.

```json
{
  "status": "ok",
  "checks": {
    "database": { "healthy": true, "latency_ms": 1.2 },
    "database_tables": { "healthy": true, "latency_ms": 0.8 }
  },
  "uptime": { "started_at": "2026-03-07T12:00:00Z", "uptime_seconds": 3600 },
  "errors": { "error_rate": 0.0, "total_requests": 150, "alert": false }
}
```

---

### Pricing

These endpoints do not require authentication.

#### `GET /api/pricing`

Returns current pricing information including plans, models, execution pricing, volume discounts, and metadata. This endpoint is public and requires no authentication.

```bash
curl http://localhost:8000/api/pricing
```

```json
{
  "plans": [
    {
      "id": "free",
      "name": "Free Demo",
      "displayName": "Free Demo",
      "price": 0,
      "priceDisplay": "$0",
      "period": "one-time",
      "description": "Free Demo — $0 one-time onboarding: we set up the basics and run one example workflow on open-source models. Upgrade required for continued usage.",
      "features": [
        "1 agent",
        "Guided setup included",
        "1 example workflow run",
        "Open-source model pool for demo run",
        "Smart routing (model=\"auto\")",
        "Balanced governance preset",
        "Real-time metering",
        "Community support"
      ],
      "limits": [
        "No recurring monthly token bucket",
        "Upgrade required after demo run",
        "No failover or eval harness",
        "Single governance preset"
      ],
      "cta": "Start Free Demo",
      "highlight": false
    }
  ],
  "models": {
    "openai": [
      { "name": "GPT-4.1 Nano", "inputPer1M": 0.13, "outputPer1M": 0.52 },
      { "name": "GPT-4o Mini", "inputPer1M": 0.20, "outputPer1M": 0.78 }
    ],
    "anthropic": [
      { "name": "Claude Haiku 4", "inputPer1M": 1.04, "outputPer1M": 5.20 },
      { "name": "Claude Sonnet 4", "inputPer1M": 3.90, "outputPer1M": 19.50 }
    ]
  },
  "executionPricing": [
    { "action": "Agent task (single model call + governance)", "price": 0.01 },
    { "action": "Agent workflow (multi-step pipeline)", "price": 0.05 },
    { "action": "Sandbox simulation (governance wind-tunnel test)", "price": 0.10 }
  ],
  "volumeDiscounts": [
    { "minTokens": 0, "maxTokens": 1000000, "discount": 0 },
    { "minTokens": 1000000, "maxTokens": 10000000, "discount": 0.10 },
    { "minTokens": 10000000, "maxTokens": 100000000, "discount": 0.20 }
  ],
  "commonFeatures": {
    "all": [
      "Smart routing (requests routed to the right model and provider automatically)",
      "Response caching (identical prompts served from cache at zero token cost)"
    ],
    "proAndAbove": [
      "Cross-provider failover (if one provider is down, requests fail over seamlessly)",
      "Eval harness (5-dimension evaluation: toxicity, relevance, quality, hallucination, factuality)"
    ]
  },
  "metadata": {
    "platformMargin": 0.30,
    "currency": "USD",
    "billingCycle": "monthly",
    "lastUpdated": "2026-03-08"
  }
}
```

**Use cases:**
- Agents calculating costs before submitting work
- External integrations displaying pricing without authentication
- Client-side pricing calculators

**Pricing data source:** All pricing information is read from `pricing.schema.json` at the repository root, which serves as the canonical source of truth. The schema is validated in CI to ensure consistency across documentation, site components, and the API.

---

### Metering

All metering endpoints require authentication and are scoped to the current tenant.

#### `GET /api/v1/orgs/{org_id}/metering`

Query metering events for one organization.

Query params:
- `startTime`, `endTime` (unix timestamp seconds)
- `agentId`, `taskId`, `eventType`
- `limit` (default 100, max 500), `offset` (default 0)

#### `GET /api/v1/agents/{agent_id}/metering`

Query metering events for a specific agent across tenant data.

Query params:
- `startTime`, `endTime`
- `orgId`, `taskId`, `eventType`
- `limit`, `offset`

#### `GET /api/v1/tasks/{task_id}/metering`

Query metering events attributable to a single task.

Query params:
- `startTime`, `endTime`
- `orgId`, `agentId`, `eventType`
- `limit`, `offset`

Each endpoint returns:

```json
{
  "items": [],
  "total": 0,
  "limit": 100,
  "offset": 0
}
```

---

### Tenants

#### `POST /api/v1/tenants` — Sign up

Create a new tenant. **No authentication required.** Rate limited to 5 signups per IP per hour.

```bash
curl -X POST http://localhost:8000/api/v1/tenants \
  -H "Content-Type: application/json" \
  -d '{"name": "My Company", "email": "team@example.com"}'
```

```json
{
  "tenant_id": "tenant-a1b2c3d4...",
  "name": "My Company",
  "api_key": "ak-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

> **Save your API key.** It is returned only once and cannot be retrieved later.

#### `GET /api/v1/tenants/me` — Current tenant info

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/tenants/me
```

```json
{
  "tenant_id": "tenant-a1b2c3d4...",
  "name": "My Company",
  "active": true,
  "billing_status": "active"
}
```

#### `POST /api/v1/tenants/me/rotate-key` — Rotate API key

Invalidates the current key immediately and returns a new one.

```bash
curl -X POST -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/tenants/me/rotate-key
```

```json
{
  "api_key": "ak-new-key-here...",
  "message": "API key rotated successfully. Old key is now invalid."
}
```

---

### Organizations

#### `POST /api/v1/orgs` — Launch organization

Requires active billing.

```bash
curl -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/orgs \
  -d '{"package_name": "saas-dev-studio"}'
```

```json
{
  "org_id": "org-...",
  "status": "running",
  "package": "saas-dev-studio",
  "agent_count": 6
}
```

#### `GET /api/v1/orgs` — List organizations

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/orgs
```

#### `GET /api/v1/orgs/{org_id}` — Get organization

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/orgs/{org_id}
```

#### `DELETE /api/v1/orgs/{org_id}` — Shutdown organization

```bash
curl -X DELETE -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/orgs/{org_id}
```

```json
{ "status": "stopped", "org_id": "org-..." }
```

---

### Tasks

#### `POST /api/v1/orgs/{org_id}/tasks` — Submit task

Requires active billing. Task is assigned via sealed-bid auction. Governance preset is auto-selected based on task type and agent trust score.

```bash
curl -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/orgs/{org_id}/tasks \
  -d '{
    "description": "Implement OAuth2 login for the API",
    "metadata": {"priority": "high"},
    "execute": true
  }'
```

```json
{
  "task_id": "task-...",
  "assigned_to": "agent-...",
  "status": "executing",
  "governance": {
    "preset": "balanced",
    "task_type": "pipeline",
    "trust_tier": "high",
    "reason": "Pipeline task + high trust → balanced preset"
  }
}
```

**Validation:**
- `description`: 1–10,000 characters
- `metadata`: max 20 keys, max 64 KB total size
- `execute`: if `true`, runs task asynchronously in background

#### `GET /api/v1/orgs/{org_id}/tasks` — List tasks

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/orgs/{org_id}/tasks
```

#### `GET /api/v1/orgs/{org_id}/tasks/{task_id}` — Get task

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/orgs/{org_id}/tasks/{task_id}
```

---

### Agents

#### `GET /api/v1/orgs/{org_id}/agents` — List agents

Returns all agents with trust scores.

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/orgs/{org_id}/agents
```

#### `GET /api/v1/orgs/{org_id}/agents/{agent_id}` — Get agent

Includes effectiveness trend (`improving` / `stable` / `declining`).

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/orgs/{org_id}/agents/{agent_id}
```

#### `GET /api/v1/orgs/{org_id}/agents/{agent_id}/effectiveness` — Agent effectiveness

Full trust history, duration percentiles (p5/p50/p95), and success rate.

```bash
curl -H "X-API-Key: $API_KEY" \
  http://localhost:8000/api/v1/orgs/{org_id}/agents/{agent_id}/effectiveness
```

```json
{
  "agent_id": "agent-...",
  "trust_history": [0.72, 0.78, 0.85],
  "current_trust": 0.85,
  "duration_percentiles": { "p5": 120, "p50": 450, "p95": 1200 },
  "success_rate": 0.92,
  "effectiveness_trend": "improving"
}
```

#### `GET /api/v1/orgs/{org_id}/agents/{agent_id}/history` — Agent history

Recent task outcomes and wallet snapshots.

```bash
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8000/api/v1/orgs/{org_id}/agents/{agent_id}/history?limit=50"
```

---

### Governance

#### `GET /api/v1/orgs/{org_id}/governance` — Get governance config

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/orgs/{org_id}/governance
```

```json
{
  "preset": "balanced",
  "overrides": {
    "audit_frequency": 0.10,
    "circuit_breaker": { "enabled": true, "threshold": 3 },
    "tax_rate": 0.05
  }
}
```

#### `PATCH /api/v1/orgs/{org_id}/governance` — Update governance

Adjust governance levers on a running organization.

```bash
curl -X PATCH -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/orgs/{org_id}/governance \
  -d '{
    "preset": "conservative",
    "overrides": {
      "audit_frequency": 0.25,
      "tax_rate": 0.10
    }
  }'
```

**Validation:**
- `preset`: `conservative`, `balanced`, or `aggressive`
- `audit_frequency`: 0.0–1.0
- `tax_rate`: 0.0–0.5

---

### Billing

#### `GET /api/v1/orgs/{org_id}/billing` — Usage summary

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/orgs/{org_id}/billing
```

```json
{
  "org_id": "org-...",
  "budget_limit_usd": 100.0,
  "total_agent_balance": 4200,
  "agent_count": 6
}
```

#### `POST /api/v1/billing/setup-customer` — Create Stripe customer

```bash
curl -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/billing/setup-customer \
  -d '{"email": "billing@example.com"}'
```

#### `POST /api/v1/billing/checkout` — Start checkout session

```bash
curl -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/billing/checkout \
  -d '{
    "price_id": "price_xxx",
    "success_url": "https://example.com/success",
    "cancel_url": "https://example.com/cancel"
  }'
```

> URLs must be HTTPS and match the `BILLING_ALLOWED_HOSTS` allowlist.

#### `POST /api/v1/billing/portal` — Billing portal

Returns a Stripe self-service portal URL for managing subscriptions.

#### `GET /api/v1/billing/subscription` — Current subscription

#### `POST /api/v1/billing/report-usage` — Report token usage

#### `POST /api/v1/billing/meter-event` — Record meter event (Stripe Meters API)

```bash
curl -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/billing/meter-event \
  -d '{
    "event_name": "llm_tokens",
    "value": 42,
    "extra_payload": {
      "model": "claude-sonnet-4"
    }
  }'
```

#### `POST /api/v1/billing/credit-grants` — Grant prepaid credits

Creates a Stripe billing credit grant for the current tenant's Stripe customer.

```bash
curl -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/billing/credit-grants \
  -d '{
    "amount_value": 2500,
    "currency": "usd",
    "category": "paid",
    "name": "Starter Credits",
    "price_ids": ["price_metered_xxx"]
  }'
```

#### `GET /api/v1/billing/credit-balance-summary` — Current credit balance

Returns Stripe's credit balance summary for the current customer, filtered to metered applicability by default.

#### `GET /api/v1/billing/credit-topup-config` — Credit top-up offer

Returns whether a one-time prepaid credit checkout is enabled and which Stripe price backs it.

#### `POST /api/v1/billing/credit-topup-checkout` — Start prepaid credit checkout

Starts a `mode=payment` Stripe Checkout session for a one-time credit pack. When the resulting `checkout.session.completed` webhook arrives, Agency-OS creates the corresponding Stripe credit grant automatically.

#### `POST /api/v1/billing/stripe-webhook` — Stripe webhook receiver

No authentication required. Validates `stripe-signature` header. Handles:
- `checkout.session.completed`
- `invoice.payment_succeeded`
- `invoice.payment_failed`
- `customer.subscription.deleted`

---

### Gateway (LLM Proxy)

OpenAI-compatible chat completions API with smart routing, caching, and cost tracking. All gateway endpoints require active billing.

#### `POST /api/v1/gateway/chat/completions` — Chat completion

```bash
curl -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/gateway/chat/completions \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Hello, world!"}
    ]
  }'
```

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1709827200,
  "model": "gpt-4o",
  "choices": [{
    "message": { "role": "assistant", "content": "Hello! How can I help?" },
    "finish_reason": "stop",
    "index": 0
  }],
  "usage": { "prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20 },
  "x_cache": "MISS",
  "x_routed_model": "gpt-4o",
  "x_routing": { "strategy": "cost_optimized", "complexity": "simple" }
}
```

**Request fields:**
- `model` (required): Model ID or `"auto"` for smart routing
- `messages` (required): 1–256 messages, total content max 1 MB
- `stream`: SSE streaming (max 10 concurrent per tenant)
- `temperature`: 0.0–2.0 (deterministic requests at 0 or null are cached)
- `max_tokens`: 1–1,000,000
- `top_p`: 0.0–1.0
- `stop`: string or list of stop sequences
- `budget`: `"low"`, `"medium"`, or `"high"` (used by smart router)
- `task_class`: `"quality"`, `"latency"`, or `"cost"` policy target for `model="auto"`

**Features:**
- **Smart routing:** `model="auto"` selects by complexity + task class policy (`quality`/`latency`/`cost`)
- **Response caching:** Deterministic requests (temperature=0 or null) are cached and served at zero cost
- **Failover:** Automatic retry on different provider if primary fails
- **Cost tracking:** Per-request `provider_cost`, `customer_cost`, `margin` (internal only)

#### `GET /api/v1/gateway/models` — List available models

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/gateway/models
```

#### `GET /api/v1/gateway/stats` — Gateway statistics

Per-tenant cache and routing statistics.

#### `GET /api/v1/gateway/requests` — Request history

```bash
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/api/v1/gateway/requests?limit=50"
```

Returns up to 200 recent requests with `request_id`, `model_id`, `tokens_in`, `tokens_out`, `latency_ms`, `cached`, `status`.

#### `GET /api/v1/gateway/admin/provider-keys` — Provider key status (platform admin + RBAC)

Returns provider credential configuration status (`configured`, `created_at`, `updated_at`) plus last rotation actor/timestamp from immutable audit logs.

#### `POST /api/v1/gateway/admin/provider-keys/{provider}/rotate` — Rotate provider key (platform admin + RBAC + approval)

Requires:
- Tenant metadata `is_platform_admin=true`
- Tenant metadata permission `gateway.provider_key.admin` (include in `permissions`)
- `X-Manager-Approval: true`
- `X-Approval-Reason: <reason>`

Request body:
- `api_key`: new provider API key
- `reason`: audit reason for rotation (min 8 chars)

Rotation invalidates cached provider clients immediately and appends a `gateway.provider_key.rotated` audit event with key fingerprints (hash prefixes only, no plaintext secret logging).

#### `GET /api/v1/gateway/admin/provider-keys/audit` — Provider key rotation audit trail (platform admin + RBAC)

Query params:
- `limit` (default 50, max 200)
- `provider` (optional filter)

#### `POST /api/v1/gateway/eval` — Submit routing feedback

```bash
curl -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/gateway/eval \
  -d '{
    "request_id": "chatcmpl-...",
    "model_id": "gpt-4o",
    "complexity": "simple",
    "score": 0.95
  }'
```

#### `GET /api/v1/gateway/eval/stats` — Routing feedback stats

---

### Packages

#### `GET /api/v1/packages` — List built-in packages

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/packages
```

```json
[
  { "name": "saas-dev-studio", "display_name": "SaaS Development Studio", "tier": "professional", "agent_count": 6 },
  { "name": "marketing-agency", "display_name": "Marketing Agency", "tier": "professional", "agent_count": 6 }
]
```

#### `GET /api/v1/packages/{name}` — Package details

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/packages/saas-dev-studio
```

---

### Webhooks

#### `POST /api/v1/webhooks` — Register webhook

```bash
curl -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/webhooks \
  -d '{
    "url": "https://example.com/webhook",
    "events": ["task.completed", "budget.alert"]
  }'
```

**Validation:**
- URL must be HTTPS (no private/loopback IPs)
- Max 10 webhooks per tenant
- Valid events: `task.assigned`, `task.completed`, `budget.alert`, `circuit_breaker.tripped`, `org.started`, `org.stopped`

#### `GET /api/v1/webhooks` — List webhooks

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/webhooks
```

#### `GET /api/v1/webhooks/{webhook_id}/deliveries` — Delivery status history

```bash
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8000/api/v1/webhooks/<webhook_id>/deliveries?limit=100"
```

Returns recent delivery attempts with:
- `attempt_count` and `max_attempts`
- `success`, `status_code`, and `error`
- `next_retry_at` for pending retries
- `created_at` / `updated_at` / `completed_at`

#### Retry Policy

- Up to 5 attempts total per delivery
- Exponential backoff between retries: `1s`, `2s`, `4s`, `8s`
- Retryable failures: network errors and HTTP `408`, `425`, `429`, `500`, `502`, `503`, `504`
- Circuit breaker: endpoint is suspended after 5 consecutive failures and auto-resets after 5 minutes

#### Verifying Webhook Signatures

Agency-OS signs all webhook deliveries with HMAC-SHA256 to ensure authenticity and integrity. **You MUST verify signatures before processing webhooks** to prevent attackers from forging events.

**Signature Header Format:**

```
X-AgencyOS-Signature: sha256=<hex_digest>
```

**Verification Algorithm:**

1. Extract the raw request body as bytes (before JSON parsing)
2. Compute HMAC-SHA256 using your webhook secret as the key
3. Format the result as `sha256=<hex_digest>` (lowercase hex)
4. Compare using constant-time comparison to prevent timing attacks

**Code Examples:**

<details>
<summary><strong>Python</strong></summary>

```python
import hmac
import hashlib
from flask import request

def verify_webhook_signature(payload_bytes: bytes, signature: str, secret: str) -> bool:
    """
    Verify Agency-OS webhook signature.

    Args:
        payload_bytes: Raw request body as bytes
        signature: Value from X-AgencyOS-Signature header
        secret: Your webhook signing secret (from registration response)

    Returns:
        True if signature is valid, False otherwise
    """
    expected = "sha256=" + hmac.new(
        secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()

    # CRITICAL: Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(signature, expected)

# Flask example
@app.route('/webhook', methods=['POST'])
def handle_webhook():
    signature = request.headers.get('X-AgencyOS-Signature')
    if not signature:
        return {'error': 'Missing signature'}, 401

    payload_bytes = request.get_data()
    if not verify_webhook_signature(payload_bytes, signature, WEBHOOK_SECRET):
        return {'error': 'Invalid signature'}, 401

    event = request.json
    # Process verified webhook...
    return {'status': 'ok'}, 200
```
</details>

<details>
<summary><strong>JavaScript / Node.js</strong></summary>

```javascript
const crypto = require('crypto');
const express = require('express');

/**
 * Verify Agency-OS webhook signature.
 *
 * @param {string} payloadString - Raw request body as string
 * @param {string} signature - Value from X-AgencyOS-Signature header
 * @param {string} secret - Your webhook signing secret
 * @returns {boolean} True if signature is valid
 */
function verifyWebhookSignature(payloadString, signature, secret) {
  const expected = 'sha256=' + crypto
    .createHmac('sha256', secret)
    .update(payloadString, 'utf8')
    .digest('hex');

  // CRITICAL: Use timingSafeEqual to prevent timing attacks
  try {
    return crypto.timingSafeEqual(
      Buffer.from(signature),
      Buffer.from(expected)
    );
  } catch (e) {
    return false;
  }
}

// Express example
const app = express();

app.post('/webhook', express.raw({ type: 'application/json' }), (req, res) => {
  const signature = req.headers['x-agencyos-signature'];
  if (!signature) {
    return res.status(401).json({ error: 'Missing signature' });
  }

  const payloadString = req.body.toString('utf8');
  if (!verifyWebhookSignature(payloadString, signature, process.env.WEBHOOK_SECRET)) {
    return res.status(401).json({ error: 'Invalid signature' });
  }

  const event = JSON.parse(payloadString);
  // Process verified webhook...
  res.json({ status: 'ok' });
});
```
</details>

<details>
<summary><strong>Go</strong></summary>

```go
package main

import (
    "crypto/hmac"
    "crypto/sha256"
    "crypto/subtle"
    "encoding/hex"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
)

// VerifyWebhookSignature verifies Agency-OS webhook signature.
func VerifyWebhookSignature(payload []byte, signature, secret string) bool {
    mac := hmac.New(sha256.New, []byte(secret))
    mac.Write(payload)
    expected := "sha256=" + hex.EncodeToString(mac.Sum(nil))

    // CRITICAL: Use constant-time comparison to prevent timing attacks
    return subtle.ConstantTimeCompare([]byte(signature), []byte(expected)) == 1
}

func webhookHandler(w http.ResponseWriter, r *http.Request) {
    signature := r.Header.Get("X-AgencyOS-Signature")
    if signature == "" {
        http.Error(w, "Missing signature", http.StatusUnauthorized)
        return
    }

    payload, err := io.ReadAll(r.Body)
    if err != nil {
        http.Error(w, "Failed to read body", http.StatusBadRequest)
        return
    }

    secret := os.Getenv("WEBHOOK_SECRET")
    if !VerifyWebhookSignature(payload, signature, secret) {
        http.Error(w, "Invalid signature", http.StatusUnauthorized)
        return
    }

    var event map[string]interface{}
    if err := json.Unmarshal(payload, &event); err != nil {
        http.Error(w, "Invalid JSON", http.StatusBadRequest)
        return
    }

    // Process verified webhook...
    w.WriteHeader(http.StatusOK)
    json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}
```
</details>

**Test Fixtures:**

Use these known-good test vectors to validate your implementation:

```
Secret: test-secret-key-123

Payload:
{"event_type":"task.completed","org_id":"org-abc123","timestamp":"2026-03-08T00:00:00Z","payload":{"task_id":"task-1","status":"success"}}

Expected Signature:
sha256=44604ce4f1b8e7db21223267db9f4a9249bfe61929e1b2b1918cd63d31d7f626
```

```
Secret: production-webhook-key-xyz

Payload:
{"event_type":"budget.alert","org_id":"org-prod-456","timestamp":"2026-03-08T12:00:00Z","payload":{"budget_remaining":100,"threshold":0.1}}

Expected Signature:
sha256=3d18cedc520c8b72f0bc26679d73ee47dd7ff02542fc63dc1bb2dd5e2c9a86b8
```

**Security Best Practices:**

1. **Always verify signatures FIRST** — Before parsing JSON, updating databases, or triggering actions
2. **Use constant-time comparison** — `hmac.compare_digest()` (Python), `crypto.timingSafeEqual()` (Node.js), `subtle.ConstantTimeCompare()` (Go) prevent timing attacks
3. **Protect your signing secret** — Store in environment variables or secrets manager, never commit to source control
4. **Log failed verifications** — Monitor for potential attacks or configuration issues
5. **Combine with timestamp validation** — Reject webhooks older than 5 minutes to prevent replay attacks (see webhook payload `timestamp` field)
6. **Use HTTPS for your webhook endpoint** — Prevents MITM attacks from capturing signatures
7. **Return 401 for invalid signatures** — Don't reveal whether the signature or other validation failed

**Webhook Payload Structure:**

```json
{
  "event_type": "task.completed",
  "org_id": "org-abc123",
  "timestamp": "2026-03-08T12:34:56.789Z",
  "payload": {
    "task_id": "task-1",
    "status": "success",
    "duration_ms": 1234
  }
}
```

All webhook deliveries include:
- `event_type` — Event identifier (e.g., `task.completed`, `budget.alert`)
- `org_id` — Organization that triggered the event
- `timestamp` — ISO 8601 timestamp of event generation
- `payload` — Event-specific data

---

#### Preventing Replay Attacks

After verifying the signature, you SHOULD implement replay protection to prevent attackers from capturing and re-sending valid webhooks. Agency-OS provides two defense mechanisms:

**Method 1: Timestamp Validation (Recommended)**

Agency-OS includes `X-AgencyOS-Timestamp` header (Unix epoch seconds) and `timestamp` field (ISO 8601) in every webhook. Reject requests older than 5 minutes to prevent replay attacks.

<details>
<summary><strong>Python Example</strong></summary>

```python
from datetime import datetime, timezone, timedelta

def is_webhook_fresh(timestamp_header: str, tolerance_minutes: int = 5) -> bool:
    """
    Verify webhook timestamp is recent to prevent replay attacks.

    Args:
        timestamp_header: Value from X-AgencyOS-Timestamp header (Unix epoch)
        tolerance_minutes: Maximum age in minutes (default: 5)

    Returns:
        True if webhook is fresh, False if too old or invalid
    """
    try:
        webhook_time = datetime.fromtimestamp(int(timestamp_header), tz=timezone.utc)
        now = datetime.now(timezone.utc)
        age = now - webhook_time

        # Reject webhooks older than tolerance window
        if age > timedelta(minutes=tolerance_minutes):
            return False

        # Reject webhooks from the future (clock skew attacks)
        if age < timedelta(minutes=-1):
            return False

        return True
    except (ValueError, OSError):
        return False

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    signature = request.headers.get('X-AgencyOS-Signature')
    timestamp = request.headers.get('X-AgencyOS-Timestamp')

    if not signature or not timestamp:
        return {'error': 'Missing required headers'}, 401

    # Step 1: Verify signature
    payload_bytes = request.get_data()
    if not verify_webhook_signature(payload_bytes, signature, WEBHOOK_SECRET):
        return {'error': 'Invalid signature'}, 401

    # Step 2: Verify timestamp freshness
    if not is_webhook_fresh(timestamp):
        return {'error': 'Webhook timestamp too old'}, 401

    event = request.json
    # Process verified webhook...
    return {'status': 'ok'}, 200
```
</details>

<details>
<summary><strong>JavaScript / Node.js Example</strong></summary>

```javascript
/**
 * Verify webhook timestamp is recent to prevent replay attacks.
 *
 * @param {string} timestampHeader - Value from X-AgencyOS-Timestamp header
 * @param {number} toleranceMinutes - Maximum age in minutes (default: 5)
 * @returns {boolean} True if webhook is fresh
 */
function isWebhookFresh(timestampHeader, toleranceMinutes = 5) {
  try {
    const webhookTime = parseInt(timestampHeader, 10) * 1000; // Convert to milliseconds
    const now = Date.now();
    const ageMs = now - webhookTime;
    const toleranceMs = toleranceMinutes * 60 * 1000;

    // Reject old webhooks
    if (ageMs > toleranceMs) {
      return false;
    }

    // Reject future webhooks (clock skew)
    if (ageMs < -60000) { // -1 minute
      return false;
    }

    return true;
  } catch (e) {
    return false;
  }
}

app.post('/webhook', express.raw({ type: 'application/json' }), (req, res) => {
  const signature = req.headers['x-agencyos-signature'];
  const timestamp = req.headers['x-agencyos-timestamp'];

  if (!signature || !timestamp) {
    return res.status(401).json({ error: 'Missing required headers' });
  }

  // Step 1: Verify signature
  const payloadString = req.body.toString('utf8');
  if (!verifyWebhookSignature(payloadString, signature, process.env.WEBHOOK_SECRET)) {
    return res.status(401).json({ error: 'Invalid signature' });
  }

  // Step 2: Verify timestamp freshness
  if (!isWebhookFresh(timestamp)) {
    return res.status(401).json({ error: 'Webhook timestamp too old' });
  }

  const event = JSON.parse(payloadString);
  // Process verified webhook...
  res.json({ status: 'ok' });
});
```
</details>

**Method 2: Nonce-Based Deduplication (High-Security)**

For stronger protection against replay attacks within the 5-minute window, implement nonce-based deduplication:

1. **Extract delivery identifier:** Parse the webhook payload and generate a unique identifier (e.g., `hash(event_type + org_id + timestamp + payload)`)
2. **Check for duplicates:** Query your cache (Redis) or database to see if this identifier has been processed
3. **Store with TTL:** If new, store the identifier with a TTL of 10 minutes (2× the timestamp tolerance)
4. **Reject duplicates:** Return 200 OK for duplicate deliveries (idempotent behavior)

<details>
<summary><strong>Python + Redis Example</strong></summary>

```python
import hashlib
import json
import redis

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

def get_webhook_nonce(payload_bytes: bytes) -> str:
    """Generate deterministic nonce from webhook payload."""
    return hashlib.sha256(payload_bytes).hexdigest()

def is_webhook_duplicate(nonce: str, ttl_seconds: int = 600) -> bool:
    """
    Check if webhook has been processed (returns True if duplicate).
    Stores nonce with TTL if new.
    """
    key = f"webhook_nonce:{nonce}"

    # Try to set key with NX (only if not exists)
    was_set = redis_client.set(key, "1", ex=ttl_seconds, nx=True)

    # If set failed, key already existed (duplicate)
    return not was_set

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    signature = request.headers.get('X-AgencyOS-Signature')
    timestamp = request.headers.get('X-AgencyOS-Timestamp')

    if not signature or not timestamp:
        return {'error': 'Missing required headers'}, 401

    payload_bytes = request.get_data()

    # Step 1: Verify signature
    if not verify_webhook_signature(payload_bytes, signature, WEBHOOK_SECRET):
        return {'error': 'Invalid signature'}, 401

    # Step 2: Verify timestamp
    if not is_webhook_fresh(timestamp):
        return {'error': 'Webhook timestamp too old'}, 401

    # Step 3: Check for replay (nonce deduplication)
    nonce = get_webhook_nonce(payload_bytes)
    if is_webhook_duplicate(nonce):
        # Already processed - return success for idempotency
        return {'status': 'ok', 'duplicate': True}, 200

    event = request.json
    # Process verified, fresh, unique webhook...
    return {'status': 'ok'}, 200
```
</details>

**Recommendation:**
- **For most use cases:** Implement timestamp validation (Method 1) — simple, effective, no infrastructure dependencies
- **For high-security or financial applications:** Implement both timestamp validation AND nonce deduplication (Method 1 + Method 2)
- **Acceptable replay window:** Timestamp validation allows ~5 minute replay window. This is acceptable for most event types (status updates, alerts). For payment/billing webhooks, add nonce deduplication.

---

**Troubleshooting:**

| Issue | Solution |
|-------|----------|
| Signature always fails | Ensure you're using the raw request body bytes, not parsed JSON |
| Intermittent failures | Check for character encoding issues (use UTF-8) |
| "Missing signature" errors | Verify header name is `X-AgencyOS-Signature` (case-insensitive in HTTP) |
| Timing attack warnings | Switch to constant-time comparison functions |

---

### Waitlist

#### `POST /api/v1/waitlist` — Join waitlist

No authentication required. Rate limited to 5 per IP per hour.

```bash
curl -X POST http://localhost:8000/api/v1/waitlist \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'
```

---

## Python Examples

### Using `httpx`

```python
import httpx

BASE = "http://localhost:8000"
HEADERS = {"X-API-Key": "ak-your-key-here"}

# Sign up (no auth needed)
resp = httpx.post(f"{BASE}/api/v1/tenants", json={"name": "My Team"})
api_key = resp.json()["api_key"]

# Launch an organization
headers = {"X-API-Key": api_key}
org = httpx.post(f"{BASE}/api/v1/orgs",
                 json={"package_name": "saas-dev-studio"},
                 headers=headers).json()

# Submit a task
task = httpx.post(f"{BASE}/api/v1/orgs/{org['org_id']}/tasks",
                  json={"description": "Build a REST API for user management",
                        "execute": True},
                  headers=headers).json()

print(f"Task {task['task_id']} → {task['status']}")
print(f"Governance: {task['governance']['preset']} ({task['governance']['reason']})")
```

### Gateway (OpenAI-compatible)

```python
import httpx

resp = httpx.post("http://localhost:8000/api/v1/gateway/chat/completions",
                  headers={"X-API-Key": "ak-your-key"},
                  json={
                      "model": "auto",
                      "messages": [{"role": "user", "content": "Explain REST APIs"}],
                      "temperature": 0
                  })
print(resp.json()["choices"][0]["message"]["content"])
```

### Streaming

```python
import httpx

with httpx.stream("POST", "http://localhost:8000/api/v1/gateway/chat/completions",
                   headers={"X-API-Key": "ak-your-key"},
                   json={
                       "model": "auto",
                       "messages": [{"role": "user", "content": "Tell me a story"}],
                       "stream": True
                   }) as resp:
    for line in resp.iter_lines():
        if line.startswith("data: ") and line != "data: [DONE]":
            print(line[6:])
```

---

## JavaScript Examples

### Using `fetch`

```javascript
const BASE = "http://localhost:8000";
const headers = {
  "X-API-Key": "ak-your-key-here",
  "Content-Type": "application/json",
};

// Launch organization
const org = await fetch(`${BASE}/api/v1/orgs`, {
  method: "POST",
  headers,
  body: JSON.stringify({ package_name: "saas-dev-studio" }),
}).then((r) => r.json());

// Submit task
const task = await fetch(`${BASE}/api/v1/orgs/${org.org_id}/tasks`, {
  method: "POST",
  headers,
  body: JSON.stringify({
    description: "Build a REST API for user management",
    execute: true,
  }),
}).then((r) => r.json());

console.log(`Task ${task.task_id}: ${task.status}`);
```

### Gateway with streaming

```javascript
const resp = await fetch(`${BASE}/api/v1/gateway/chat/completions`, {
  method: "POST",
  headers,
  body: JSON.stringify({
    model: "auto",
    messages: [{ role: "user", content: "Hello" }],
    stream: true,
  }),
});

const reader = resp.body.getReader();
const decoder = new TextDecoder();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const text = decoder.decode(value);
  process.stdout.write(text);
}
```
