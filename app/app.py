"""Streamlit demo for the geo assistant — B2B layout.

Layout:
    ┌──────────┬───────────────────────────────────┬──────────────────┐
    │          │            HEADER                 │                  │
    │ Sidebar  ├───────────────────────────────────┼──────────────────┤
    │ (state)  │                                   │ [hex card]       │
    │ read-    │       MAP (H3 hex grid)           │ CHAT             │
    │ only     │       click hex → card on right   │ multi-turn       │
    │          │                                   │                  │
    └──────────┴───────────────────────────────────┴──────────────────┘

Запуск:
    streamlit run app/app.py
"""
from __future__ import annotations
import sys
from pathlib import Path

import streamlit as st

# --- path bootstrap ---------------------------------------------------------
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import h3  # noqa: E402
from agent.agent import run as run_agent  # noqa: E402
from agent.memory import ConversationMemory  # noqa: E402
from agent.prompts import SYSTEM_PROMPT  # noqa: E402

from core_utils.coverage import compute_opportunity_grid, HEX_SIZE_REFERENCE  # noqa: E402
from core_utils.search import search_places  # noqa: E402
from lib.data_types import Place  # noqa: E402
from map_visualization import opportunity_hex_map  # noqa: E402

from streamlit_folium import st_folium
import folium  # noqa: E402


# --- page config ------------------------------------------------------------
st.set_page_config(
    page_title="Geo AI Assistant — B2B Site Selection",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.2rem; padding-bottom: 0.5rem; }
      section[data-testid="stSidebar"] .stCaption { margin-top: -0.5rem; }
      div.chat-panel-marker { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- constants --------------------------------------------------------------
CITY_CENTER = (56.8386, 60.6055)
DEFAULT_ZOOM = 12
CATEGORIES = ["cafe", "restaurant", "pharmacy", "bar"]
DEFAULT_HEX_RES = 8


# --- session state initialization ------------------------------------------
def _init_state() -> None:
    if "memory" not in st.session_state:
        st.session_state["memory"] = ConversationMemory(SYSTEM_PROMPT)
    if "chat_log" not in st.session_state:
        st.session_state["chat_log"] = []
    if "selected_category" not in st.session_state:
        st.session_state["selected_category"] = "pharmacy"
    if "pending_query" not in st.session_state:
        st.session_state["pending_query"] = None
    if "selected_hex" not in st.session_state:
        # Карточка с метриками гекса, ожидающая решения пользователя
        st.session_state["selected_hex"] = None


_init_state()


# --- helpers ----------------------------------------------------------------
def _find_hex_by_click(lat: float, lng: float) -> dict | None:
    """Найти гекс из текущей сетки по координатам клика.

    Используем тот же hex_resolution, что был при построении: считаем
    hex_id от координат клика и ищем совпадение в cells. Это надёжнее,
    чем искать «ближайший» по евклидову расстоянию.
    """
    opp = st.session_state.get("opportunity_grid")
    if not opp or not opp.get("cells"):
        return None

    args = opp.get("args", {})
    resolution = int(args.get("hex_resolution", DEFAULT_HEX_RES))

    try:
        target_hex_id = h3.latlng_to_cell(lat, lng, resolution)
    except Exception:
        return None

    for cell in opp["cells"]:
        if cell["hex_id"] == target_hex_id:
            return cell
    return None


def _format_hex_query(cell: dict, category: str) -> str:
    """Сформировать обогащённый запрос агенту по метрикам гекса."""
    return (
        f"Analyse the area around hex {cell['hex_id']} "
        f"(center: lat={cell['center_lat']:.5f}, lon={cell['center_lon']:.5f}) "
        f"for opening a new {category}.\n\n"
        f"Hex metrics:\n"
        f"- Opportunity score: {cell.get('opportunity_score', 0):.2f}\n"
        f"- Demand (other POI): {cell['demand_score']}\n"
        f"- Existing {category} competitors: {cell.get('competitor_count', 0)} "
        f"(avg rating {cell.get('competitor_avg_rating', 0):.1f})\n"
        f"- Total POI in hex: {cell['total_places']}\n\n"
        f"Use nearest_places to list real competitors in/near this hex and "
        f"give a verdict on whether it is a good location."
    )


# --- sidebar (read-only agent state) ----------------------------------------
def render_sidebar() -> None:
    """Read-only дашборд: показывает текущий контекст агента."""
    with st.sidebar:
        st.header("Agent context")
        st.caption("Read-only — обновляется по мере диалога")

        # --- City ----------------------------------------------------------
        st.markdown("**City**")
        st.markdown("Екатеринбург, Россия")

        st.divider()

        # --- Active analysis -----------------------------------------------
        opp = st.session_state.get("opportunity_grid")
        st.markdown("**Active analysis**")

        if opp and opp.get("cells"):
            args = opp.get("args", {})
            category = args.get("category", "—")
            resolution = args.get("hex_resolution", DEFAULT_HEX_RES)
            threshold = args.get("demand_threshold", 0.0)
            n_cells = len(opp["cells"])
            n_visible = sum(1 for c in opp["cells"] if c.get("is_visible"))

            st.markdown(f"**Opportunity grid** · `{category}`")
            col_a, col_b = st.columns(2)
            col_a.metric("Total hexes", n_cells)
            col_b.metric("Visible", n_visible)

            st.caption(f"H3 resolution: **{resolution}**")
            hex_ref = HEX_SIZE_REFERENCE.get(resolution)
            if hex_ref:
                st.caption(f"↳ {hex_ref}")
            if threshold > 0:
                st.caption(f"Demand threshold: {threshold}")
        else:
            st.markdown("_No analysis yet._")
            st.caption("Спросите агента или нажмите Quick action.")

        st.divider()

        # --- Heatmap state (если агент строил) ----------------------------
        hm = st.session_state.get("agent_heatmap")
        if hm:
            st.markdown("**Heatmap**")
            st.caption(f"Points: {len(hm.get('points', []))}")
            st.divider()

        # --- Conversation memory ------------------------------------------
        mem: ConversationMemory = st.session_state["memory"]
        n_msgs = max(len(mem.history) - 1, 0)
        n_user = sum(1 for m in mem.history if m.get("role") == "user")
        n_tool = sum(1 for m in mem.history if m.get("role") == "tool")

        st.markdown("**Conversation memory**")
        col_x, col_y, col_z = st.columns(3)
        col_x.metric("Messages", n_msgs)
        col_y.metric("Queries", n_user)
        col_z.metric("Tool calls", n_tool)

        st.caption(f"Window: last {mem.max_turns} turns")

        st.divider()

        st.markdown("**Map target category**")
        st.markdown(f"🎯 `{st.session_state['selected_category']}`")
        st.caption("Категория конкурентов на карте")


# --- map rendering ----------------------------------------------------------
def _build_map() -> folium.Map:
    """Собрать folium-карту из текущего состояния."""
    opp_config = st.session_state.get("opportunity_grid")

    if opp_config and opp_config.get("cells"):
        cells = opp_config["cells"]
        category = st.session_state["selected_category"]
        competitors = search_places(category=[category], limit=500)
        fmap = opportunity_hex_map(
            cells,
            places=competitors,
            zoom_start=DEFAULT_ZOOM,
        )
        return fmap

    return folium.Map(location=CITY_CENTER, zoom_start=DEFAULT_ZOOM)


@st.fragment
def render_map_fragment() -> None:
    """Фрагмент с картой.

    Клик по гексу → определяем hex_id → сохраняем в selected_hex →
    rerun → правая колонка показывает карточку с метриками.
    """
    fmap = _build_map()

    map_state = st_folium(
        fmap,
        key="main_map",
        height=600,
        use_container_width=True,
        returned_objects=["last_object_clicked", "last_clicked"],
    )

    clicked = map_state.get("last_object_clicked") if map_state else None
    if clicked and clicked != st.session_state.get("_last_click_handled"):
        lat = clicked.get("lat")
        lng = clicked.get("lng")
        if lat is not None and lng is not None:
            st.session_state["_last_click_handled"] = clicked
            cell = _find_hex_by_click(lat, lng)
            if cell is not None:
                st.session_state["selected_hex"] = cell
                st.rerun()
            # Если клик не попал в гекс (например, на маркер конкурента) —
            # тихо игнорируем. Можно добавить отдельный popup, но это уже сверху.


# --- chat panel -------------------------------------------------------------
def _send_to_agent(query: str) -> None:
    st.session_state["chat_log"].append({"role": "user", "content": query})
    try:
        answer = run_agent(query, memory=st.session_state["memory"])
    except Exception as exc:  # noqa: BLE001
        answer = f"⚠️ Agent error: {exc}"
    st.session_state["chat_log"].append({"role": "assistant", "content": answer})


def render_hex_card() -> None:
    """Карточка с метриками выбранного гекса.

    Показывается над чатом, ждёт явного решения пользователя:
    отправить запрос агенту или отклонить.
    """
    cell = st.session_state.get("selected_hex")
    if cell is None:
        return

    cat = st.session_state["selected_category"]
    opp_score = cell.get("opportunity_score", 0)

    # Визуальная подсказка: зелёный — хорошее место, красный — плохое
    if opp_score > 5:
        verdict_emoji = "🟢"
        verdict_text = "Promising location"
    elif opp_score > 0:
        verdict_emoji = "🟡"
        verdict_text = "Mixed signals"
    else:
        verdict_emoji = "🔴"
        verdict_text = "Saturated / weak"

    with st.container(border=True):
        st.markdown(f"### {verdict_emoji} Selected hex")
        st.caption(
            f"**{verdict_text}** for opening a new `{cat}` · "
            f"`{cell['center_lat']:.4f}, {cell['center_lon']:.4f}`"
        )

        m1, m2, m3 = st.columns(3)
        m1.metric(
            "Opportunity",
            f"{opp_score:.1f}",
            help="demand_score − competitor_density. Выше = лучше место.",
        )
        m2.metric(
            "Competitors",
            cell.get("competitor_count", 0),
            help=f"Существующие {cat} в этом гексе",
        )
        m3.metric(
            "Total POI",
            cell["total_places"],
            help="Любые места — прокси трафика и жизни района",
        )

        if cell.get("competitor_count", 0) > 0:
            st.caption(
                f"Средний рейтинг конкурентов: "
                f"⭐ {cell.get('competitor_avg_rating', 0):.1f}"
            )

        btn_ask, btn_dismiss = st.columns([2, 1])
        if btn_ask.button(
            "🔍 Ask agent about this area",
            use_container_width=True,
            type="primary",
            key="hex_card_ask",
        ):
            st.session_state["pending_query"] = _format_hex_query(cell, cat)
            st.session_state["selected_hex"] = None
            st.rerun()

        if btn_dismiss.button(
            "✕ Dismiss",
            use_container_width=True,
            key="hex_card_dismiss",
        ):
            st.session_state["selected_hex"] = None
            st.rerun()


def render_chat_panel() -> None:
    """Правая колонка: карточка гекса (если есть) + чат."""
    st.markdown('<div class="chat-panel-marker"></div>', unsafe_allow_html=True)

    # Карточка над чатом — самое видное место
    render_hex_card()

    # Контролы
    top_left, top_right = st.columns([3, 1])
    with top_left:
        st.session_state["selected_category"] = st.selectbox(
            "Target category",
            CATEGORIES,
            index=CATEGORIES.index(st.session_state["selected_category"]),
            help="Категория конкурентов на карте и в анализе гексов.",
        )
    with top_right:
        st.write("")
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state["chat_log"] = []
            st.session_state["memory"].clear()
            st.session_state.pop("opportunity_grid", None)
            st.session_state.pop("agent_heatmap", None)
            st.session_state.pop("_last_click_handled", None)
            st.session_state["selected_hex"] = None
            st.rerun()

    with st.expander("Quick actions", expanded=False):
        b1, b2 = st.columns(2)
        if b1.button("📍 Show opportunity grid", use_container_width=True):
            cat = st.session_state["selected_category"]
            cells = compute_opportunity_grid(
                category=cat, hex_resolution=DEFAULT_HEX_RES
            )
            st.session_state["opportunity_grid"] = {
                "cells": cells,
                "args": {
                    "category": cat,
                    "hex_resolution": DEFAULT_HEX_RES,
                    "demand_threshold": 0.0,
                },
            }
            st.session_state["chat_log"].append({
                "role": "assistant",
                "content": (
                    f"Built opportunity grid for **{cat}** "
                    f"({len(cells)} hex cells, "
                    f"{sum(1 for c in cells if c['is_visible'])} visible). "
                    f"Click a hex to see its metrics."
                ),
            })
            st.rerun()

        if b2.button("❓ Where to open?", use_container_width=True):
            cat = st.session_state["selected_category"]
            st.session_state["pending_query"] = (
                f"Where in the city would be the best location to open "
                f"a new {cat}? Use the opportunity grid to find hexes "
                f"with high demand and low competition."
            )
            st.rerun()

    st.divider()

    chat_container = st.container(height=380, border=False)
    with chat_container:
        if not st.session_state["chat_log"]:
            st.caption(
                "👋 Click a hex on the map, use Quick actions, "
                "or just ask me about the city."
            )
        for msg in st.session_state["chat_log"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    pending = st.session_state.pop("pending_query", None)
    if pending:
        with st.spinner("Thinking..."):
            _send_to_agent(pending)
        st.rerun()

    user_input = st.chat_input("Ask about the city or click a hex on the map...")
    if user_input:
        with st.spinner("Thinking..."):
            _send_to_agent(user_input)
        st.rerun()


# --- layout -----------------------------------------------------------------
render_sidebar()

st.title("🗺️ Geo AI Assistant — B2B Site Selection")
st.caption(
    "Анализ городской среды для открытия новой точки. "
    "Кликайте по гексам на карте — увидите метрики и сможете спросить агента."
)

map_col, chat_col = st.columns([3, 2], gap="medium")

with map_col:
    render_map_fragment()

with chat_col:
    render_chat_panel()
