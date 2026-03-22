"""Governance page: live lever sliders, RBAC matrix."""

from __future__ import annotations

import httpx
import streamlit as st


def render(api_url: str, api_key: str) -> None:
    st.title("Governance Controls")

    if not api_key:
        st.warning("Enter your API key in the sidebar.")
        return

    org_id = st.text_input("Organization ID", key="gov_org_id")
    if not org_id:
        st.info("Enter an Organization ID.")
        return

    headers = {"X-API-Key": api_key}

    try:
        resp = httpx.get(
            f"{api_url}/api/v1/orgs/{org_id}/governance", headers=headers, timeout=5
        )
        if resp.status_code != 200:
            st.error("Failed to fetch governance")
            return
        gov = resp.json()
    except Exception as e:
        st.error(f"Error: {e}")
        return

    st.subheader("Governance Preset")
    current_preset = gov.get("preset", "balanced")
    new_preset = st.selectbox(
        "Preset",
        ["conservative", "balanced", "aggressive"],
        index=["conservative", "balanced", "aggressive"].index(current_preset),
    )

    st.subheader("Governance Levers")
    overrides = gov.get("overrides", {})

    audit_freq = st.slider(
        "Audit Frequency", 0.0, 1.0, overrides.get("audit_frequency", 0.1), 0.01
    )
    tax_rate = st.slider("Tax Rate", 0.0, 0.5, overrides.get("tax_rate", 0.05), 0.01)

    cb = overrides.get("circuit_breaker", {})
    cb_enabled = st.checkbox("Circuit Breaker Enabled", value=cb.get("enabled", True))
    cb_threshold = st.number_input(
        "Circuit Breaker Threshold",
        min_value=1,
        max_value=10,
        value=cb.get("threshold", 3),
    )

    if st.button("Apply Changes"):
        update = {
            "preset": new_preset,
            "overrides": {
                "audit_frequency": audit_freq,
                "tax_rate": tax_rate,
                "circuit_breaker": {
                    "enabled": cb_enabled,
                    "threshold": cb_threshold,
                },
            },
        }
        try:
            resp = httpx.patch(
                f"{api_url}/api/v1/orgs/{org_id}/governance",
                headers=headers,
                json=update,
                timeout=5,
            )
            if resp.status_code == 200:
                st.success("Governance updated!")
                st.json(resp.json())
            else:
                st.error(f"Failed: {resp.json()}")
        except Exception as e:
            st.error(f"Error: {e}")

    # RBAC matrix
    st.subheader("RBAC Matrix")
    try:
        agents_resp = httpx.get(
            f"{api_url}/api/v1/orgs/{org_id}/agents", headers=headers, timeout=5
        )
        if agents_resp.status_code == 200:
            agents = agents_resp.json()
            st.dataframe(
                [
                    {
                        "Agent": a["name"],
                        "Allowed Tools": ", ".join(a.get("allowed_tools", [])) or "all",
                        "Denied Tools": ", ".join(a.get("denied_tools", [])) or "none",
                    }
                    for a in agents
                ],
                use_container_width=True,
            )
    except Exception:
        pass
