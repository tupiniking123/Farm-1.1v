"""
ui.py
Streamlit UI helpers (simple + reusable).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from db_local import get_setting, set_setting
from services import list_farms_local


DARK_CSS = """
<style>
:root {
  --bg: #0e1117;
  --panel: #111827;
  --text: #e5e7eb;
  --muted: #9ca3af;
  --border: rgba(255,255,255,0.08);
}

html, body, [class*="css"]  {
  background-color: var(--bg) !important;
  color: var(--text) !important;
}

section[data-testid="stSidebar"] {
  background-color: var(--panel) !important;
  border-right: 1px solid var(--border);
}

div[data-testid="stMetricValue"] { color: var(--text) !important; }
div[data-testid="stMetricLabel"] { color: var(--muted) !important; }

.stButton>button, .stDownloadButton>button {
  border-radius: 10px;
  border: 1px solid var(--border);
}

hr { border-color: var(--border); }
</style>
"""

LIGHT_CSS = """
<style>
.stButton>button, .stDownloadButton>button { border-radius: 10px; }
</style>
"""


def apply_theme(conn):
    dark = get_setting(conn, "dark_mode", "1") == "1"
    st.markdown(DARK_CSS if dark else LIGHT_CSS, unsafe_allow_html=True)


def sidebar_controls(conn) -> Dict[str, Any]:
    farms = list_farms_local(conn)
    farm_labels = {f["id"]: f["name"] for f in farms}
    active_farm_id = get_setting(conn, "active_farm_id", "")

    st.sidebar.title("🐄 Rural SaaS")

    # Dark mode
    dark = get_setting(conn, "dark_mode", "1") == "1"
    new_dark = st.sidebar.toggle("🌙 Dark mode", value=dark)
    if new_dark != dark:
        set_setting(conn, "dark_mode", "1" if new_dark else "0")
        st.rerun()

    # Farm selector
    if farms:
        options = list(farm_labels.keys())
        default_index = options.index(active_farm_id) if active_farm_id in options else 0
        selected = st.sidebar.selectbox("Fazenda ativa", options=options, format_func=lambda x: farm_labels.get(x, x), index=default_index)
        if selected != active_farm_id:
            set_setting(conn, "active_farm_id", selected)
            active_farm_id = selected
    else:
        st.sidebar.info("Crie uma fazenda para começar.")
        active_farm_id = ""

    # Period controls
    today = date.today()
    default_start = today - timedelta(days=30)
    start, end = st.sidebar.date_input("Período", value=(default_start, today))
    if isinstance(start, tuple) or isinstance(end, tuple):
        # streamlit older behavior
        start, end = start[0], start[1]

    st.sidebar.divider()

    menu = st.sidebar.radio(
        "Menu",
        ["Dashboard", "Financeiro", "Estoque", "Vacinação", "Cadastros", "Sync"],
        index=0,
    )

    return {
        "active_farm_id": active_farm_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "menu": menu,
    }


def download_csv_button(df: pd.DataFrame, filename: str, label: str = "Baixar CSV"):
    if df is None or df.empty:
        st.caption("Nada para exportar.")
        return
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label, data=csv, file_name=filename, mime="text/csv")


def table(df: pd.DataFrame, height: int = 320):
    if df is None or df.empty:
        st.info("Sem dados.")
        return
    st.dataframe(df, use_container_width=True, height=height)
