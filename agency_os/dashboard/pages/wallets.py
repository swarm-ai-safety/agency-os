"""Wallets page: balances, transaction log, Sankey diagram."""

from __future__ import annotations

import httpx
import streamlit as st


def render(api_url: str, api_key: str) -> None:
    st.title("Agent Wallets")

    if not api_key:
        st.warning("Enter your API key in the sidebar.")
        return

    org_id = st.text_input("Organization ID", key="wallets_org_id")
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

    # Balance bar chart
    st.subheader("Agent Balances")
    chart_data = {a["name"]: a["balance"] for a in agents}
    st.bar_chart(chart_data)

    # Balance table
    st.subheader("Balance Details")
    st.dataframe(
        [
            {
                "Agent": a["name"],
                "Balance": f"{a['balance']:.2f}",
                "Strategy": a.get("bid_strategy", "default"),
                "Tasks Completed": a.get("tasks_completed", 0),
                "Tasks Failed": a.get("tasks_failed", 0),
            }
            for a in agents
        ],
        use_container_width=True,
    )

    # Sankey placeholder
    st.subheader("Token Flow (Sankey)")
    st.info(
        "Sankey diagram will visualize token flow between agents after task execution is tracked."
    )
