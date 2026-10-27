"""Offline visual QA; synthetic valuation only, no providers/bots/accounts."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
import importlib
from src import valuation_ui
importlib.reload(valuation_ui)
from src.ui_theme import stylesheet
from src.ui_theme import palette
from src import desk_grid
importlib.reload(desk_grid)
desk_dataframe, desk_data_editor = desk_grid.desk_dataframe, desk_grid.desk_data_editor
from src.valuation import assess_valuation, attach_valuation
from src.valuation_ui import render_valuation, vt, LANGS
from tests.test_valuation import snapshot, NOW

st.set_page_config(page_title="Valuation QA", layout="wide")
light = st.toggle("Light mode", value=True)
lang = st.selectbox("Language", LANGS)
st.html(stylesheet(light))
if st.button("Test notification"):
    st.toast("BOT · Thông báo thử nghiệm — không thực hiện giao dịch.", icon="⚠️", duration="infinite")
st.caption("QA · Synthetic data · No bot / provider calls")
p = palette(light)
table = pd.DataFrame({"time":["2026-08-26"],"symbol":["ACB"],"quantity":[500],"buy_price":[20.876],"Volatility20":[1.2],"bias":["BULLISH"]})
desk_dataframe(table, light=light, lang=lang)
with st.form("qa_editor"):
    edited = desk_data_editor(table[["symbol","quantity","buy_price"]], key="qa_stock", light=light, lang=lang,
        column_config={"symbol":st.column_config.TextColumn(disabled=True),
        "quantity":st.column_config.NumberColumn(min_value=0,step=100,format="%d"),
        "buy_price":st.column_config.NumberColumn(min_value=0,format="%.3f",step=.001)})
    st.text_area("Câu hỏi cho AI",placeholder="Nhập câu hỏi…")
    if st.form_submit_button("Test only") and edited is not None:
        st.session_state.qa_saved = edited.to_dict("records")
st.write(st.session_state.get("qa_saved", []))
with st.form("qa_futures"):
    futures = desk_data_editor(pd.DataFrame({"symbol":["VN30F1M"],"side":["LONG"],"quantity":[2],"entry_price":[1800.1]}),
        key="qa_futures_grid",light=light,lang=lang,column_config={
        "symbol":st.column_config.TextColumn(disabled=True),
        "side":st.column_config.SelectboxColumn(options=["LONG","SHORT"],required=True),
        "quantity":st.column_config.NumberColumn(min_value=0,step=1,format="%d"),
        "entry_price":st.column_config.NumberColumn(min_value=0,step=.1,format="%.1f")})
    if st.form_submit_button("Test futures only") and futures is not None:
        st.session_state.qa_futures_saved = futures.to_dict("records")
st.write(st.session_state.get("qa_futures_saved", []))
desk_dataframe(pd.DataFrame({"symbol":[f"QA{i:03}" for i in range(125)],"Score":range(-60,65),
    "Bài viết":["https://example.com"]*125}),light=light,lang=lang,column_config={
    "Score":st.column_config.ProgressColumn(min_value=-100,max_value=100,format="%+.1f"),
    "Bài viết":st.column_config.LinkColumn("Bài viết")})
with st.chat_message("assistant"):
    st.caption("AI ENGINE · INTERNAL")
value = assess_valuation(snapshot(), [snapshot(s, 12, 2) for s in ("VCB", "BID", "CTG")], now=NOW)
result = attach_valuation({"consensus_score": 30, "data_quality": {"data_quality": "GOOD"}}, value)
with st.expander(vt(lang, "title"), expanded=True):
    render_valuation(result, lang, light)
