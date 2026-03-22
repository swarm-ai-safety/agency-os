"""Audits page: audit log, circuit breaker status."""

from __future__ import annotations

import httpx
import streamlit as st


def render(api_url: str, api_key: str) -> None:
    st.title("Audits & Circuit Breakers")

    if not api_key:
        st.warning("Enter your API key in the sidebar.")
        return

    org_id = st.text_input("Organization ID", key="audits_org_id")
    if not org_id:
        st.info("Enter an Organization ID.")
        return

    headers = {"X-API-Key": api_key}

    try:
        resp = httpx.get(
            f"{api_url}/api/v1/orgs/{org_id}/governance", headers=headers, timeout=5
        )
        if resp.status_code != 200:
            st.error("Failed to fetch governance config")
            return
        gov = resp.json()
    except Exception as e:
        st.error(f"Error: {e}")
        return

    # Governance status
    st.subheader("Governance Status")
    col1, col2 = st.columns(2)
    col1.metric("Preset", gov.get("preset", "unknown"))

    overrides = gov.get("overrides", {})
    cb = overrides.get("circuit_breaker", {})
    if cb:
        col2.metric("Circuit Breaker", "Enabled" if cb.get("enabled") else "Disabled")
        st.write(f"Threshold: {cb.get('threshold', 'N/A')} violations")

    # Audit frequency
    audit_freq = overrides.get("audit_frequency")
    if audit_freq is not None:
        st.metric("Audit Frequency", f"{audit_freq * 100:.0f}%")

    st.subheader("Audit Log")
    st.info(
        "Audit log entries will appear here when the SWARM audit system is integrated."
    )
