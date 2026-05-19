"""Streamlit demo for the geo assistant.

Запуск:
    streamlit run app/app.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.data_types import Place
from agent.agent import run as run_agent  # noqa: E402
from map_visualization import places_map, heatmap, opportunity_hex_map # noqa: E402
from core_utils.coverage import compute_opportunity_grid  # noqa: E402
from core_utils.ranking import rank_by_distance, rank_by_score  # noqa: E402
from core_utils.search import search_places  # noqa: E402

st.set_page_config(page_title="Geo AI Assistant", layout="wide")

# ---- Sidebar ---------------------------------------------------------------
st.sidebar.header("Settings")
city = st.sidebar.selectbox(
    "City (для real OSM-данных; sample dataset уже сгенерирован для Yerevan)",
    ["Yerevan, Armenia", "Tbilisi, Georgia", "Other"],
    index=0,
)
categories = st.sidebar.multiselect(
    "Categories",
    ["cafe", "restaurant", "pharmacy", "bar"],
    default=["cafe", "restaurant", "pharmacy", "bar"],
)
ranking_strategy = st.sidebar.radio(
    "Ranking strategy",
    ["score (rating - distance)", "distance"],
    index=0,
)
# Фоллбэк-чекбокс (используется, если агент не вызвал tool для heatmap)
show_heatmap = st.sidebar.checkbox("Show Heatmap Overlay", value=True)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Без LLM-ключа агент работает в offline-режиме (эвристический роутинг). "
    "С `OPENAI_API_KEY` или `LLM_BASE_URL` — полный tool-calling pipeline."
)

# ---- Main pane -------------------------------------------------------------
st.title("Geo AI Assistant")

PRESETS = {
    "(custom query)": "",
    "Golden path: low pharmacy coverage": "Find areas with low pharmacy coverage",
    "Find cafes near center": "Find cafe near center",
    "Quiet bar in Arabkir": "Find bar in Arabkir",
}
preset = st.selectbox("Preset", list(PRESETS.keys()))
query = st.text_input("Query", value=PRESETS[preset])

col_go, col_demo, col_clear = st.columns([1, 1, 1])
go = col_go.button("Run agent")
demo = col_demo.button("Run golden-path demo (no LLM)")
clear = col_clear.button("Clear")

# ---- Session state management ----------------------------------------------
if clear:
    st.session_state.pop("result", None)
    st.session_state.pop("agent_heatmap", None)
    st.session_state.pop("opportunity_grid", None)

if demo:
    cells = compute_opportunity_grid(category="pharmacy", hex_resolution=8)
    st.session_state["result"] = {
        "kind": "demo_opportunity",
        "cells": cells,
    }
    st.session_state.pop("agent_heatmap", None)
    st.session_state.pop("opportunity_grid", None)

elif go and query:
    # Сбрасываем перед новым запросом
    st.session_state.pop("agent_heatmap", None)
    st.session_state.pop("opportunity_grid", None)

    with st.spinner("Thinking..."):
        answer = run_agent(query)
        places: list[Place] = search_places(category=categories, limit=80) or list()
        if ranking_strategy.startswith("score"):
            places = rank_by_score(places)[:80]
        else:
            places = rank_by_distance(places)[:80]

    st.session_state["result"] = {
        "kind": "agent",
        "answer": answer,
        "places": places,
        "strategy": ranking_strategy,
    }

# ---- Render the latest result ----------------------------------------------
result = st.session_state.get("result")
if result is None:
    st.info("Введите запрос и нажмите Run agent или Run golden-path demo.")
else:
    try:
        from streamlit_folium import folium_static
    except ImportError as exc:
        st.error(f"streamlit-folium не установлен: {exc}")
        st.stop()

    hm_config = st.session_state.get("agent_heatmap")
    opp_config = st.session_state.get("opportunity_grid")  # 🆕

    if result["kind"] == "demo_opportunity":
        st.subheader("Golden path: Opportunity Grid")
        demo_places = search_places(category=categories, limit=500)
        fmap = opportunity_hex_map(result["cells"], places=demo_places)
        folium_static(fmap, width=900, height=520)
        st.write("Hex cells with demand & competitor density:")
        st.dataframe(result["cells"])

    elif result["kind"] == "agent":
        st.subheader("Answer")
        st.write(result["answer"])

        if opp_config and opp_config.get("cells"):
            st.subheader("Market Saturation & Opportunity Grid")
            fmap = opportunity_hex_map(opp_config["cells"], places=result["places"])
            folium_static(fmap, width=900, height=520)
            st.caption(f"Grid built with {len(opp_config['cells'])} hexes")
            st.dataframe(opp_config["cells"])
        elif hm_config:
            st.subheader("Agent-generated Heatmap")
            fmap = heatmap(hm_config["points"], zoom_start=hm_config.get("zoom_start", 13))
            folium_static(fmap, width=900, height=520)
            st.caption(f"Heatmap built from {len(hm_config['points'])} points")
        else:
            st.subheader("Map preview (filtered by sidebar)")
            folium_static(places_map(result["places"], show_heatmap=show_heatmap), width=900, height=520)
            st.caption(f"Showing {len(result['places'])} places · strategy: {result['strategy']}")
