"""Effectiveness page: trust trends, success rates, governance history, agent comparison."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import httpx
import streamlit as st


def _fetch(
    api_url: str, path: str, headers: dict[str, str]
) -> dict[str, Any] | list[Any] | None:
    try:
        resp = httpx.get(f"{api_url}{path}", headers=headers, timeout=5)
        if resp.status_code == 200:
            payload = resp.json()
            if isinstance(payload, (dict, list)):
                return cast(dict[str, Any] | list[Any], payload)
    except Exception:
        pass
    return None


def render(api_url: str, api_key: str) -> None:
    st.title("Agent Effectiveness")

    if not api_key:
        st.warning("Enter your API key in the sidebar.")
        return

    org_id = st.text_input("Organization ID", key="eff_org_id")
    if not org_id:
        st.info("Enter an Organization ID.")
        return

    headers = {"X-API-Key": api_key}

    agents = _fetch(api_url, f"/api/v1/orgs/{org_id}/agents", headers)
    if agents is None:
        st.error("Failed to fetch agents")
        return

    if not isinstance(agents, list):
        st.error("Unexpected agents response")
        return
    if not agents:
        st.info("No agents in this organization.")
        return

    # ---- Agent Comparison (all agents at a glance) ----
    st.subheader("Agent Comparison")
    comparison_data = []
    for a in agents:
        comparison_data.append(
            {
                "Agent": a.get("name", a.get("agent_id", "")),
                "Trust Score": a.get("trust_score", 0.0),
                "Trust Tier": a.get("trust_tier", "n/a"),
                "Reputation": a.get("reputation", 0.0),
                "Tasks Done": a.get("tasks_completed", 0),
                "Tasks Failed": a.get("tasks_failed", 0),
            }
        )
    st.dataframe(comparison_data, use_container_width=True)

    # Trust score comparison bar chart
    trust_chart = {
        a.get("name", a.get("agent_id", "")): a.get("trust_score", 0.0) for a in agents
    }
    st.bar_chart(trust_chart)

    # ---- Per-Agent Deep Dive ----
    st.markdown("---")
    agent_names = {
        a.get("name", a.get("agent_id", "")): a.get("agent_id", "") for a in agents
    }
    selected_name = st.selectbox(
        "Select agent for detailed view", list(agent_names.keys())
    )
    if not selected_name:
        return
    agent_id = agent_names[selected_name]

    # Fetch effectiveness and history
    effectiveness = _fetch(
        api_url, f"/api/v1/orgs/{org_id}/agents/{agent_id}/effectiveness", headers
    )
    history = _fetch(
        api_url, f"/api/v1/orgs/{org_id}/agents/{agent_id}/history", headers
    )

    if not isinstance(effectiveness, dict):
        st.error("Failed to fetch effectiveness data")
        return
    history_dict = history if isinstance(history, dict) else {}

    # ---- Metrics Row ----
    current = effectiveness.get("current_trust")
    if current:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Trust Score", f"{current['score']:.2f}")
        col2.metric("Trust Tier", current["tier"].capitalize())
        col3.metric(
            "Trend", effectiveness.get("effectiveness_trend", "stable").capitalize()
        )
        sr = effectiveness.get("success_rate", {})
        col4.metric(
            "Success Rate",
            f"{sr.get('rate', 0) * 100:.0f}%",
            f"{sr.get('successes', 0)}/{sr.get('total_tasks', 0)}",
        )

    # ---- Trust Score Trend Line ----
    trust_history = effectiveness.get("trust_history", [])
    if trust_history:
        st.subheader("Trust Score Over Time")
        # trust_history is most-recent-first; reverse for chronological
        trust_history = list(reversed(trust_history))
        chart_data = []
        for h in trust_history:
            ts = h.get("computed_at", 0)
            chart_data.append(
                {
                    "time": datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                        "%H:%M:%S"
                    ),
                    "score": h["score"],
                }
            )
        scores = [d["score"] for d in chart_data]
        st.line_chart(scores)

        # Show tier progression
        tier_sequence = [h["tier"] for h in trust_history]
        unique_tiers: list[str] = []
        for t in tier_sequence:
            if not unique_tiers or unique_tiers[-1] != t:
                unique_tiers.append(t)
        if len(unique_tiers) > 1:
            st.caption(f"Governance tier progression: {' → '.join(unique_tiers)}")
    else:
        st.info("No trust score history yet. Complete tasks to build history.")

    # ---- Duration Percentiles ----
    percentiles = effectiveness.get("duration_percentiles", {})
    if any(v is not None for v in percentiles.values()):
        st.subheader("Task Duration Percentiles")
        pcol1, pcol2, pcol3 = st.columns(3)
        pcol1.metric(
            "p5 (fast)",
            f"{percentiles.get('p5', 0):.1f}s"
            if percentiles.get("p5") is not None
            else "n/a",
        )
        pcol2.metric(
            "p50 (median)",
            f"{percentiles.get('p50', 0):.1f}s"
            if percentiles.get("p50") is not None
            else "n/a",
        )
        pcol3.metric(
            "p95 (slow)",
            f"{percentiles.get('p95', 0):.1f}s"
            if percentiles.get("p95") is not None
            else "n/a",
        )

    # ---- Task Outcome History ----
    if history_dict:
        outcomes = history_dict.get("task_outcomes", [])
        if outcomes:
            st.subheader("Recent Task Outcomes")
            outcome_rows = []
            for o in outcomes:
                ts = o.get("timestamp", 0)
                outcome_rows.append(
                    {
                        "Time": datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        "Outcome": o.get("outcome", "unknown"),
                        "Duration": f"{o.get('duration_sec', 0):.1f}s"
                        if o.get("duration_sec") is not None
                        else "n/a",
                        "Task ID": o.get("task_id", "")[:12],
                    }
                )
            st.dataframe(outcome_rows, use_container_width=True)

        # ---- Wallet/Reputation History ----
        snapshots = history_dict.get("wallet_snapshots", [])
        if snapshots:
            st.subheader("Wallet & Reputation History")
            # snapshots are most-recent-first; reverse for chronological
            snapshots = list(reversed(snapshots))
            balances = [s.get("balance", 0) for s in snapshots]
            reputations = [s.get("reputation", 0) for s in snapshots]

            wcol1, wcol2 = st.columns(2)
            with wcol1:
                st.caption("Balance over time")
                st.line_chart(balances)
            with wcol2:
                st.caption("Reputation over time")
                st.line_chart(reputations)
