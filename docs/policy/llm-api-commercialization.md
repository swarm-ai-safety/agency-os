# LLM API Commercialization Policy

Date: 2026-03-08  
Owner: CPO

## Decision

We can monetize AI features built on third-party model APIs when customers buy product outcomes (workflow, automation, UX, support), not raw model access.

## Allowed Model

- Build SaaS features using vendor APIs and charge via subscription, usage, or markup.
- Route and orchestrate model calls in our backend.
- Keep provider credentials fully controlled by our infrastructure.

## Prohibited Model

- Selling or sharing upstream provider API keys.
- Offering pass-through "raw model API access" as a standalone marketplace.
- Using consumer chat plans as commercial backend infrastructure.
- Bypassing provider limits through pooling/account sharing schemes.

## Product Guardrails

- Users interact with our product surface; they do not directly access provider accounts.
- Billing artifacts describe our product value, not resale of a specific vendor key.
- Architecture keeps prompt routing, logging, rate limiting, and policy enforcement server-side.

## Execution Checklist (Before Launch)

- Confirm target provider commercial terms permit the intended use case.
- Confirm key-management and credential-isolation controls are in place.
- Confirm customer packaging and pricing describe product outcomes.
- Confirm legal review for public claims, enterprise contracts, and reseller-adjacent motions.

## Risk Note

This document is strategic product guidance, not legal advice. Provider terms can change and vary by product tier, geography, and contract.
