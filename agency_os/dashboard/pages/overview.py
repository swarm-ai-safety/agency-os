"""Overview page: org health, throughput, budget burn."""

from __future__ import annotations

import httpx
import streamlit as st


def render(api_url: str, api_key: str) -> None:
    st.title("Organization Overview")

    if not api_key:
        st.warning("Enter your API key in the sidebar to connect.")
        return

    headers = {"X-API-Key": api_key}

    try:
        resp = httpx.get(f"{api_url}/health", timeout=5)
        if resp.status_code == 200:
            st.success("API Connected")
        else:
            st.error(f"API unhealthy: {resp.status_code}")
            return
    except httpx.ConnectError:
        st.error(f"Cannot connect to API at {api_url}")
        return

    # Fetch orgs (placeholder — real impl would list tenant orgs)
    org_id = st.text_input("Organization ID")
    if not org_id:
        st.info("Enter an Organization ID to view details.")
        return

    try:
        resp = httpx.get(f"{api_url}/api/v1/orgs/{org_id}", headers=headers, timeout=5)
        if resp.status_code != 200:
            st.error(f"Org not found: {resp.json().get('detail', 'Unknown error')}")
            return

        data = resp.json()
    except Exception as e:
        st.error(f"Error fetching org: {e}")
        return

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Status", data.get("status", "unknown"))
    col2.metric("Agents", data.get("agent_count", 0))
    col3.metric("Tasks", data.get("tasks_submitted", 0))
    col4.metric("Budget", f"${data.get('budget_limit_usd', 0):.2f}")

    # Agent table
    st.subheader("Agents")
    agents = data.get("agents", [])
    if agents:
        st.dataframe(
            [
                {
                    "Name": a.get("name", ""),
                    "Division": a.get("division", ""),
                    "Balance": a.get("balance", 0),
                    "Reputation": f"{a.get('reputation', 0):.2f}",
                    "Tasks Done": a.get("tasks_completed", 0),
                }
                for a in agents
            ],
            use_container_width=True,
        )
