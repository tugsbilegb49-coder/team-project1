"""Streamlit dashboard for local CSV logs or the Django API.

Run with: streamlit run dashboard/app.py
"""

from __future__ import annotations

from datetime import date
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.logger import load_log, summarize, summarize_by_day, summarize_by_person


st.set_page_config(page_title="Worker Activity Monitor", layout="wide")
st.title("🖥️ Worker Activity Monitor")


def request_json(url: str, method: str = "GET", payload: dict | None = None, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"API error {exc.code}: {exc.read().decode('utf-8', errors='replace')}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach the API: {exc}") from exc


def render_seconds(seconds: float) -> str:
    return f"{float(seconds) / 60:.1f} min"


def render_api_dashboard() -> None:
    st.sidebar.subheader("Django API")
    api_url = st.sidebar.text_input("API URL", "http://127.0.0.1:8000").rstrip("/")
    username = st.sidebar.text_input("Username")
    password = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login", use_container_width=True):
        try:
            token_data = request_json(
                f"{api_url}/api/auth/login/",
                method="POST",
                payload={"username": username, "password": password},
            )
            st.session_state["dashboard_access_token"] = token_data["access"]
            st.session_state["dashboard_api_url"] = api_url
            st.success("Logged in for this browser session.")
        except (KeyError, RuntimeError) as exc:
            st.sidebar.error(str(exc))

    token = st.session_state.get("dashboard_access_token")
    connected_url = st.session_state.get("dashboard_api_url", api_url)
    if not token:
        st.info("Sign in in the sidebar to see your API data.")
        return

    report_date = st.sidebar.date_input("Report date", value=date.today())
    employee_id = st.sidebar.text_input("Employee ID (admin/manager only, optional)")
    params = {"date": report_date.isoformat()}
    if employee_id.strip():
        params["employee_id"] = employee_id.strip()
    try:
        data = request_json(f"{connected_url}/api/scores/dashboard/?{urlencode(params)}", token=token)
        consent = request_json(f"{connected_url}/api/consents/status/", token=token)
    except RuntimeError as exc:
        st.error(f"Session/API problem: {exc}")
        return

    employee = data["employee"]
    st.subheader(f"{employee['username']} — {data['date']}")
    score = data.get("score")
    metrics = st.columns(4)
    metrics[0].metric("Productivity score", f"{score['score']}" if score else "Not calculated")
    metrics[1].metric("Category", score["category"] if score else "—")
    metrics[2].metric("Task completion", f"{score['task_completion']}%" if score else "—")
    metrics[3].metric("Consent", "Active" if consent["active"] else "Not granted")

    camera = pd.DataFrame(data["camera"])
    applications = pd.DataFrame(data["applications"])
    categories = pd.DataFrame(data["application_categories"])
    left, right = st.columns(2)
    with left:
        st.subheader("Camera activity")
        if camera.empty:
            st.info("No camera data for this day.")
        else:
            camera["minutes"] = camera["seconds"] / 60
            st.plotly_chart(px.pie(camera, names="state", values="minutes", title="Camera state time"), use_container_width=True)
    with right:
        st.subheader("Computer activity")
        if categories.empty:
            st.info("No desktop-agent data for this day.")
        else:
            categories["minutes"] = categories["seconds"] / 60
            st.plotly_chart(px.pie(categories, names="category", values="minutes", title="Application categories"), use_container_width=True)

    st.subheader("Applications")
    if applications.empty:
        st.info("No application segments for this day.")
    else:
        applications["minutes"] = applications["seconds"] / 60
        st.plotly_chart(
            px.bar(applications, x="application", y="minutes", color="category", title="Time by application"),
            use_container_width=True,
        )
        st.dataframe(applications[["application", "category", "minutes"]], use_container_width=True, hide_index=True)


def render_local_dashboard() -> None:
    log_file = st.sidebar.text_input("Log file path", "data/activity_log.csv")
    df = load_log(log_file)
    if df.empty:
        st.info("No local data yet. Run `python main.py` to start logging activity.")
        return

    is_multi_person = "person_id" in df.columns
    if is_multi_person:
        people = sorted(df["person_id"].dropna().unique().tolist())
        selected = st.sidebar.selectbox("Person", ["All"] + [str(person) for person in people])
        if selected != "All":
            df = df[df["person_id"].astype(str) == selected]
    else:
        selected = "All"

    totals = summarize(df)
    total_seconds = sum(totals.values())
    st.subheader("Local CSV breakdown")
    cols = st.columns(len(totals) if totals else 1)
    for col, (state, seconds) in zip(cols, sorted(totals.items(), key=lambda item: -item[1])):
        pct = seconds / total_seconds * 100 if total_seconds else 0
        col.metric(state, render_seconds(seconds), f"{pct:.1f}%")
    st.plotly_chart(
        px.pie(names=list(totals.keys()), values=list(totals.values()), title="Time distribution by state"),
        use_container_width=True,
    )

    daily = summarize_by_day(df)
    daily["minutes"] = daily["duration_seconds"] / 60
    st.plotly_chart(
        px.bar(daily, x="date", y="minutes", color="state", barmode="stack", title="Minutes per state, per day"),
        use_container_width=True,
    )
    if is_multi_person and selected == "All":
        by_person = summarize_by_person(df)
        by_person["minutes"] = by_person["duration_seconds"] / 60
        by_person["person_id"] = by_person["person_id"].astype(str)
        st.plotly_chart(
            px.bar(by_person, x="person_id", y="minutes", color="state", barmode="stack", title="Minutes per state, per person"),
            use_container_width=True,
        )
    with st.expander("Raw local event log"):
        st.dataframe(df.sort_values("timestamp", ascending=False), use_container_width=True)


source = st.sidebar.radio("Data source", ["Django API", "Local CSV"])
if source == "Django API":
    render_api_dashboard()
else:
    render_local_dashboard()
