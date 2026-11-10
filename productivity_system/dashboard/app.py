"""
Streamlit dashboard.  Ajilluulah: streamlit run dashboard/app.py
"""
import os
import sys
from pathlib import Path

import django
import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db.models import Sum  # noqa: E402

from core.models import CameraAnalytics, ComputerActivity  # noqa: E402

st.set_page_config(page_title="Productivity dashboard", layout="wide")
st.title("Ajiltnii buteemj")

act = pd.DataFrame(
    ComputerActivity.objects.values("employee__full_name")
    .annotate(active=Sum("active_seconds"), idle=Sum("idle_seconds"),
              keys=Sum("key_count"), clicks=Sum("click_count"))
)
if act.empty:
    st.info("Data baihgui. `python manage.py seed` ajilluulna uu.")
else:
    act["active_hours"] = act["active"] / 3600
    c1, c2 = st.columns(2)
    c1.plotly_chart(
        px.bar(act, x="employee__full_name", y="active_hours",
               title="Idevhtei tsag (tsag)"),
        use_container_width=True)
    c2.plotly_chart(
        px.bar(act, x="employee__full_name", y=["keys", "clicks"],
               barmode="group", title="Tovshilt / click too"),
        use_container_width=True)

cam = pd.DataFrame(CameraAnalytics.objects.values(
    "employee__full_name", "observed_at", "is_at_desk", "confidence"))
if not cam.empty:
    desk = cam.groupby("employee__full_name")["is_at_desk"].mean().reset_index()
    desk["is_at_desk"] *= 100
    st.plotly_chart(
        px.bar(desk, x="employee__full_name", y="is_at_desk",
               title="Suudald baisan huvi (%)"),
        use_container_width=True)
