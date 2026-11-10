"""
Streamlit dashboard.  Ajilluulah: streamlit run dashboard/app.py
"""
import os
import sys
from datetime import timedelta
from pathlib import Path

import django
import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db.models import Sum  # noqa: E402
from django.utils import timezone  # noqa: E402

from core.models import CameraAnalytics, ComputerActivity  # noqa: E402

st.set_page_config(page_title="Productivity dashboard", layout="wide")
st.title("Ajiltnii buteemj")

today = timezone.localdate()
date_selection = st.sidebar.date_input(
    "Ognoonii hugatsaa",
    value=(today - timedelta(days=6), today),
    max_value=today,
)
if isinstance(date_selection, (tuple, list)):
    if len(date_selection) == 2:
        start_date, end_date = date_selection
    elif len(date_selection) == 1:
        start_date = end_date = date_selection[0]
    else:
        start_date = end_date = today
else:
    start_date = end_date = date_selection

act = pd.DataFrame(
    ComputerActivity.objects.filter(date__range=(start_date, end_date))
    .values("employee__full_name")
    .annotate(active=Sum("active_seconds"), idle=Sum("idle_seconds"),
              keys=Sum("key_count"), clicks=Sum("click_count"))
)
if act.empty:
    st.info("Songoson hugatsaand activity alga. Demo data heregtei bol `python manage.py seed` ajilluulna uu.")
else:
    act["active_hours"] = act["active"] / 3600
    act["idle_hours"] = act["idle"] / 3600
    c1, c2 = st.columns(2)
    c1.plotly_chart(
        px.bar(
            act,
            x="employee__full_name",
            y=["active_hours", "idle_hours"],
            barmode="group",
            title="Active / idle tsag",
            labels={"employee__full_name": "Employee", "value": "Tsag", "variable": "Turul"},
        ),
        use_container_width=True)
    c2.plotly_chart(
        px.bar(act, x="employee__full_name", y=["keys", "clicks"],
               barmode="group", title="Tovshilt / click too",
               labels={"employee__full_name": "Employee", "value": "Too", "variable": "Turul"}),
        use_container_width=True)

cam = pd.DataFrame(
    CameraAnalytics.objects.filter(
        observed_at__date__range=(start_date, end_date)
    ).values("employee__full_name", "observed_at", "is_at_desk", "confidence")
)
if not cam.empty:
    desk = cam.groupby("employee__full_name")["is_at_desk"].mean().reset_index()
    desk["is_at_desk"] *= 100
    st.plotly_chart(
        px.bar(desk, x="employee__full_name", y="is_at_desk",
               title="Suudald baisan huvi (%)",
               labels={"employee__full_name": "Employee", "is_at_desk": "Huvi (%)"}),
        use_container_width=True)
else:
    st.info("Songoson hugatsaand camera analytics alga.")
