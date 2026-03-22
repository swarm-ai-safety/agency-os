"""Reputation + audits pages: leaderboard, decay curves, audit log."""

from __future__ import annotations

import httpx
import streamlit as st


def render(api_url: str, api_key: str) -> None:
    st.title("Agent Reputation")

    if not api_key:
        st.warning("Enter your API key in the sidebar.")
        return

    org_id = st.text_input("Organization ID", key="rep_org_id")
    if not org_id:
        st.info("Enter an Organization ID.")
        return

    headers = {"X-API-Key": api_key}

    try:
        resp = httpx.get(
            f"{api_url}/api/v1/orgs/{org_id}/agents", headers=headers, timeout=5
        )
        if resp.status_code != 200:
            st.error("Failed to fetch agents")
            return
        agents = resp.json()
    except Exception as e:
        st.error(f"Error: {e}")
        return

    # Leaderboard
    st.subheader("Reputation Leaderboard")
    sorted_agents = sorted(agents, key=lambda a: a.get("reputation", 0), reverse=True)
    for i, a in enumerate(sorted_agents, 1):
        col1, col2, col3 = st.columns([1, 4, 2])
        col1.write(f"**#{i}**")
        col2.write(f"{a['name']} ({a.get('division', '')})")
        col3.progress(
            min(a.get("reputation", 0) / 2.0, 1.0), text=f"{a.get('reputation', 0):.2f}"
        )

    # Reputation chart
    st.subheader("Reputation Scores")
    rep_data = {a["name"]: a.get("reputation", 0) for a in agents}
    st.bar_chart(rep_data)
