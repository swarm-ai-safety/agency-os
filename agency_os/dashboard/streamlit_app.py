"""Streamlit MVP dashboard for agency-os."""

from __future__ import annotations

import os

import streamlit as st

st.set_page_config(
    page_title="Agency-OS Dashboard",
    page_icon="🏢",
    layout="wide",
)

# Sidebar navigation
st.sidebar.title("Agency-OS")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    [
        "Overview",
        "Effectiveness",
        "Wallets",
        "Reputation",
        "Tasks",
        "Audits",
        "Governance",
    ],
)

# API connection config
api_url = st.sidebar.text_input(
    "API URL", value=os.environ.get("API_URL", "http://localhost:8000")
)
api_key = st.sidebar.text_input("API Key", type="password")

if page == "Overview":
    from agency_os.dashboard.pages.overview import render

    render(api_url, api_key)
elif page == "Effectiveness":
    from agency_os.dashboard.pages.effectiveness import render

    render(api_url, api_key)
elif page == "Wallets":
    from agency_os.dashboard.pages.wallets import render

    render(api_url, api_key)
elif page == "Reputation":
    from agency_os.dashboard.pages.reputation import render

    render(api_url, api_key)
elif page == "Tasks":
    from agency_os.dashboard.pages.tasks import render

    render(api_url, api_key)
elif page == "Audits":
    from agency_os.dashboard.pages.audits import render

    render(api_url, api_key)
elif page == "Governance":
    from agency_os.dashboard.pages.governance import render

    render(api_url, api_key)
