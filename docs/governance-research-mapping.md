# Governance Preset Research Mapping

This document maps SWARM findings to Agency-OS governance preset defaults so buyers can see exactly where defaults come from.

## Summary

- Evidence base: 146 simulations, 84 claims.
- Goal: make preset tradeoffs explicit, testable, and comparable.

## Finding-to-Preset Table

| SWARM Finding | Metric | Effect | Conservative | Balanced | Aggressive |
|---|---|---|---|---|---|
| Circuit breakers prevent cascading failures | +81% welfare, -11% toxicity | d = 1.64 | Freeze after 2 violations (`freeze_threshold_violations: 2`) | Freeze after 3 violations (`freeze_threshold_violations: 3`) | Freeze after 5 violations (`freeze_threshold_violations: 5`) |
| Tax >5% kills welfare | Phase transition | S-curve | 10% tax (`transaction_tax_rate: 0.10`) to maximize safety at welfare cost | 5% tax (`transaction_tax_rate: 0.05`) as balance point | 2% tax (`transaction_tax_rate: 0.02`) to maximize throughput |
| Diverse teams outperform uniform teams | 20% honest > 100% honest | 66 runs | Built into agent package composition and selection strategy | Built into agent package composition and templates | Built into agent package composition and templates |
| Collusion detection works | 137x wealth gap under monitoring | d = 3.51 | Enabled (`collusion_detection_enabled: true`) | Disabled by default (`collusion_detection_enabled: false`) | Disabled (`collusion_detection_enabled: false`) |
| Complex agents underperform simple ones | 2.3-2.8x less earnings | Depth-5 RLM | Preset defaults favor simpler operational policies and guardrails | Preset defaults favor simpler operational policies | Preset defaults favor simpler operational policies |
| Sybil attacks still work | 100% success | All configs | Open problem (explicitly disclosed) | Open problem (explicitly disclosed) | Open problem (explicitly disclosed) |

## Source of Preset Values

- Conservative profile: `agency_os/governance/profiles/conservative.yaml`
- Balanced profile: `agency_os/governance/profiles/balanced.yaml`
- Aggressive profile: `agency_os/governance/profiles/aggressive.yaml`

## Product Positioning Use

- "Our defaults are evidence-backed, not guessed."
- "Preset differences are explicit safety/throughput tradeoffs."
- "Known limits are documented instead of hidden."
