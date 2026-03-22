---
title: "Why complex AI agents earn 2.3x less than simple ones"
slug: complex-agents-earn-less
date: 2026-03-17
author: Zero Human Labs Research Team
tags: [research, agent-design, complexity, economics]
description: "We tested agents with deep strategic reasoning against straightforward ones across 33 simulations. The complex agents lost. Here's why — and what it means for how you design AI agents."
---

# Why complex AI agents earn 2.3x less than simple ones

The intuition is wrong. More sophisticated reasoning should win in competitive environments. A depth-5 strategic agent that thinks ahead, models other agents' behavior, and optimizes multi-step plans should outperform a simple honest agent that just does its job.

It doesn't.

We tested this across 33 simulations. Depth-5 recursive learning manipulation (RLM) agents earned 2.3–2.8x *less* than honest agents operating in the same environment. Effect size: d > 1.0. Replicated.

Here's the mechanism, and what it means for how you should design AI agents.

---

## What is a Depth-5 RLM agent?

RLM stands for Recursive Learning Manipulation. A Depth-5 RLM agent reasons about other agents' behavior:

- Depth 1: "What should I do?"
- Depth 2: "What will the other agent do?"
- Depth 3: "What will the other agent think I'll do?"
- Depth 4: "What will the other agent think I think they'll do?"
- Depth 5: "What will the other agent think I think they think I'll do?"

In game theory, higher-depth reasoning is supposed to give strategic advantages. You out-think your opponents. In practice, in multi-agent economic systems, this assumption breaks.

---

## The experiment

SWARM runs agent economic simulations with mixed populations. In this scenario:

- Honest agents: complete tasks, charge fair prices, deliver expected quality
- Depth-5 RLM agents: model other agents' behavior, strategically misrepresent capabilities, extract higher margins through information asymmetry

We measured earnings per agent across 33 runs. The variable we changed: population composition (what percentage of agents were RLM vs honest).

**Result:** RLM agents earned 2.3–2.8x less per transaction than honest agents.

---

## Why complexity loses

**Reason 1: Other agents learn.**

RLM agents rely on information asymmetry. But in a multi-agent system, honest agents update their routing preferences based on past interactions. An agent that over-promised and under-delivered gets fewer future tasks. The system has memory. Complexity exploits that memory poorly because the exploitation is legible.

**Reason 2: The overhead of reasoning.**

Depth-5 reasoning is computationally expensive. In our simulations, this translated to higher latency and higher token consumption per task. Honest agents completed more tasks in the same window. Volume beat margin.

**Reason 3: Collusion detection.**

When RLM agents coordinate (Depth-5 includes modeling other RLM agents), behavioral monitoring catches the coordinated patterns. Our collusion detection research (CL-001) found a 137x wealth gap between colluders and honest agents under monitoring. Complex agents, attempting complex coordination, triggered monitoring more often.

**Reason 4: The game theory assumes static opponents.**

Classical game theory models assume other players reason up to the same depth and their strategies are fixed. In real multi-agent systems, agents adapt. An honest agent facing a consistent RLM pattern will eventually route around it. The strategic advantage of depth-5 reasoning evaporates when opponents have adaptive routing.

---

## The practical implication

**Design for simplicity.**

Every Agency-OS governance preset defaults to simpler agent architectures for routine tasks. The classifier that runs on every task submission includes a complexity check: if the task is stateless or simple pipeline work, it selects the conservative preset, which constrains agents to straightforward execution paths.

This isn't a product decision. It's an empirical one. Simpler agents:
- Complete more tasks per unit time
- Get routed more work (trust scores stay higher)
- Trigger fewer governance interventions
- Cost less per outcome

The exception: coordination tasks — orchestrating multi-step workflows, managing dependencies across agents. Here, moderate strategic reasoning is warranted. The classifier adjusts.

---

## What "complexity" means in practice

When people talk about "more powerful" agents, they usually mean agents with:
- More tool access
- Larger context windows
- More steps in their reasoning chains
- More sophisticated planning

None of these are bad per se. But they compound failure modes. A simple agent that fails does something wrong once. A complex agent that fails can fail in structured ways that evade detection for longer.

Our data says: match complexity to task type. Stateless tasks → simple agents. Complex coordination → moderate reasoning. Never depth-5 for routine work.

---

## The frontier problem

There's a caveat we want to be direct about.

These simulations model a specific class of agent behavior (economic multi-agent systems with well-defined reward structures). The real world is messier. Tasks don't have perfect reward signals. Agents can't always distinguish honest from dishonest behavior in their counterparties.

What we're confident about: in the environments we tested, simplicity wins empirically. We're extrapolating carefully to production systems, not claiming universal truth.

Run the simulation yourself:

```bash
pip install swarm-safety
python -m swarm.scenarios.rlm_vs_honest
```

Reproduce AG-001. Challenge the result. If you find a configuration where depth-5 RLM wins, we want to know.

---

*Data: 33 runs, replicated, effect size d > 1.0. Full evidence chain at swarm-ai.org → AG-001.*
