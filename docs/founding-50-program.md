# Founding 50 Program Spec

## Overview

The Founding 50 is an early-access validation program. First 50 customers get 50% off Pro for 6 months. Card-on-file required. Purpose: separate real demand from polite interest — if they won't enter a card at half price, they won't pay full price.

## Pricing

| Item | Standard Pro | Founding 50 |
|------|-------------|-------------|
| Platform fee | $49/mo | **$24.50/mo** |
| Token usage | At-cost + 30% margin | At-cost + 30% margin (no usage discount) |
| Execution fees | Standard rates | Standard rates |
| Volume discounts | Standard tiers | Standard tiers |

**Total savings per customer:** $147 over 6 months ($24.50 × 6).

After 6 months, auto-converts to standard Pro ($49/mo). No action required from customer.

## Terms

1. **Eligibility:** First 50 customers who sign up through the Founding 50 landing page or waitlist conversion.
2. **Card-on-file required:** Must enter valid payment method at signup. No free trial, no "pay later."
3. **Duration:** 6 months from activation date. Non-transferable.
4. **Auto-conversion:** After 6 months, billing switches to standard Pro rate ($49/mo). 14-day advance email notification before rate change.
5. **Cancellation:** Can cancel anytime. No refunds on months already billed. Re-subscribing after cancellation forfeits Founding 50 pricing.
6. **Usage billing:** Token and execution usage billed at standard rates from day one. The discount applies only to the platform fee.
7. **Exclusions:** Cannot combine with other promotions. Enterprise plan customers are not eligible.

## Stripe Implementation

### Coupon Setup

```
Stripe Coupon:
  id: founding-50
  name: "Founding 50 — 50% off Pro"
  percent_off: 50
  duration: repeating
  duration_in_months: 6
  max_redemptions: 50
  applies_to:
    products: [pro_platform_fee]  # Only the $49/mo platform fee product
  metadata:
    program: founding_50
    created_by: cmo
```

### Promotion Code

```
Stripe Promotion Code:
  coupon: founding-50
  code: FOUNDING50
  max_redemptions: 50
  active: true
  metadata:
    program: founding_50
```

### Checkout Flow

1. Customer clicks "Join the Founding 50" CTA on landing page or waitlist email.
2. Redirect to Stripe Checkout with `promotion_code: FOUNDING50` pre-applied.
3. Customer sees: "Pro — $24.50/mo (50% off for 6 months), then $49/mo."
4. Customer enters payment method and subscribes.
5. Stripe creates subscription with coupon attached. Coupon auto-expires after 6 months.

### Tracking

- Use Stripe subscription metadata `{ "program": "founding_50", "cohort_number": N }` to track which Founding 50 slot was filled.
- Dashboard query: `Subscription.list(metadata: { program: "founding_50" })` to see current count and conversion rate.
- Set up Stripe webhook for `customer.subscription.updated` to detect when coupons expire (transition to full price).

## Engineering Coordination

### Required from Engineering

1. **Stripe product setup:** Create `pro_platform_fee` product with $49/mo price if not already separated from usage billing.
2. **Coupon creation:** Create the Stripe coupon and promotion code as specified above.
3. **Checkout integration:** Support pre-applied promo codes in the signup/checkout flow.
4. **Counter display:** Expose remaining Founding 50 slots on the landing page (50 - active redemptions). Creates urgency.
5. **Webhook handler:** Listen for coupon expiry events to trigger the 14-day advance notification email.

### Not Required (Out of Scope)

- No changes to the gateway, governance, or metering systems.
- No special feature flags — Founding 50 customers get standard Pro features.
- No custom billing logic — Stripe handles the coupon lifecycle automatically.

## Marketing Execution

### Landing Page Copy

> **Join the Founding 50**
>
> The first 50 teams to deploy governed agent workflows get Pro at half price for 6 months. Card required — we're looking for builders, not browsers.
>
> ~~$49/mo~~ **$24.50/mo** for 6 months, then $49/mo.
>
> [X of 50 spots remaining]

### Distribution Channels

1. **Waitlist conversion:** Email existing waitlist with Founding 50 offer. This is the primary conversion channel.
2. **Blog announcement:** Tie to launch post. "We're opening Pro access to 50 teams."
3. **Direct outreach:** Send to companies on the niche prospect list (ZERA-342).
4. **Social:** Twitter/X announcement with counter updates as spots fill.

### Success Metrics

| Metric | Target |
|--------|--------|
| Founding 50 fill rate | 50 customers within 30 days of launch |
| Card-on-file conversion | >60% of waitlist contacts who open the email |
| 6-month retention | >70% convert to full-price Pro after coupon expires |
| Usage activation | >80% run at least one agent workflow in first 14 days |

## Timeline

| Phase | Action | Owner |
|-------|--------|-------|
| Pre-launch | Create Stripe coupon + promo code | Engineering |
| Pre-launch | Build landing page with counter | Engineering + CMO |
| Launch | Email waitlist with Founding 50 offer | CMO |
| Launch | Publish blog post | CMO |
| Ongoing | Monitor fill rate and activation | CMO |
| Month 5 | Send advance notification of rate change | Automated (Stripe webhook) |
| Month 6 | Auto-conversion to standard Pro | Automated (Stripe coupon expiry) |

## Open Questions for Board

1. Should we require a minimum commitment (e.g., 3-month minimum before cancellation)?
2. Should Founding 50 customers get any exclusive access beyond pricing (e.g., direct Slack channel with the team, input on roadmap)?
3. Is the $24.50/mo price point low enough to be a no-brainer, or should we go to $19/mo (61% off) for stronger validation signal?
