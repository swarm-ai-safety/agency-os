"""Tasks page: task DAG visualization, bid history."""

from __future__ import annotations

import httpx
import streamlit as st


def render(api_url: str, api_key: str) -> None:
    st.title("Tasks")

    if not api_key:
        st.warning("Enter your API key in the sidebar.")
        return

    org_id = st.text_input("Organization ID", key="tasks_org_id")
    if not org_id:
        st.info("Enter an Organization ID.")
        return

    headers = {"X-API-Key": api_key}

    # Submit new task
    st.subheader("Submit Task")
    task_desc = st.text_area("Task Description")
    if st.button("Submit") and task_desc:
        try:
            resp = httpx.post(
                f"{api_url}/api/v1/orgs/{org_id}/tasks",
                headers=headers,
                json={"description": task_desc},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                st.success(
                    f"Task {data['task_id']} assigned to **{data['assigned_to']}**"
                )

                # Show bids
                st.subheader("Bid Results")
                st.dataframe(
                    [
                        {"Agent": b["agent_id"], "Bid": f"{b['bid']:.2f}"}
                        for b in data.get("bids", [])
                    ],
                    use_container_width=True,
                )
            else:
                st.error(f"Failed: {resp.json().get('detail', 'Unknown')}")
        except Exception as e:
            st.error(f"Error: {e}")

    st.subheader("Task DAG")
    st.info(
        "Task dependency visualization will be available when workflow execution tracking is implemented."
    )
