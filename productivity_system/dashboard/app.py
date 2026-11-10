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

from django.db.models import Avg, Count, Q, Sum  # noqa: E402
from django.utils import timezone  # noqa: E402

from core.date_ranges import local_datetime_bounds  # noqa: E402
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
start_at, end_at = local_datetime_bounds(start_date, end_date)

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
        width="stretch")
    c2.plotly_chart(
        px.bar(act, x="employee__full_name", y=["keys", "clicks"],
               barmode="group", title="Tovshilt / click too",
               labels={"employee__full_name": "Employee", "value": "Too", "variable": "Turul"}),
        width="stretch")

cam = pd.DataFrame(
    CameraAnalytics.objects.filter(
        observed_at__gte=start_at,
        observed_at__lt=end_at,
    )
    .values("employee__full_name")
    .annotate(
        total=Count("pk"),
        at_desk=Count("pk", filter=Q(is_at_desk=True)),
        avg_confidence=Avg("confidence"),
    )
)
if not cam.empty:
    cam["desk_percent"] = cam["at_desk"] * 100 / cam["total"]
    st.plotly_chart(
        px.bar(cam, x="employee__full_name", y="desk_percent",
               title="Suudald baisan huvi (%)",
               labels={"employee__full_name": "Employee", "desk_percent": "Huvi (%)"}),
        width="stretch")
    st.dataframe(
        cam[["employee__full_name", "total", "avg_confidence"]].rename(
            columns={
                "employee__full_name": "Employee",
                "total": "Camera samples",
                "avg_confidence": "Average confidence",
            }
        ),
        hide_index=True,
        width="stretch",
    )
else:
    st.info("Songoson hugatsaand camera analytics alga.")
