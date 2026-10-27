"""Read-only visual fixture: streamlit run tests/preview_news_strategy.py.

Uses synthetic content; never imports app.py, data providers or trading bots.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from src.ui_theme import stylesheet

st.set_page_config(page_title="Appearance QA", layout="wide")
light = st.toggle("Light mode", value=True)
st.html(stylesheet(light))
st.caption("Dữ liệu giả lập — kiểm thử giao diện, không kết nối BOT.")
with st.expander("Tin tức và sự kiện ảnh hưởng trực tiếp", expanded=True):
    cols = st.columns(4)
    for col, label, value in zip(cols, ("Sắc thái tin", "Tác động tin", "Số tin", "Điểm kỹ thuật + tin"), ("Trung tính", "0", "0", "25.4")):
        col.metric(label, value)
    st.caption("Chưa có tin mới. Điểm kỹ thuật được giữ nguyên.")
with st.expander("Chiến lược và kế hoạch giao dịch tự động", expanded=True):
    st.markdown("**Chiến lược:** `WAIT_BREAKOUT_OR_PULLBACK`")
    st.markdown("**Trạng thái:** `WAIT_TRIGGER`")
    st.write("Chỉ kích hoạt khi giá và khối lượng xác nhận; không mua đuổi ngoài vùng vào.")
    st.table({"Thông số": ["Vùng vào", "Cắt lỗ"], "Giá trị": [22.31, 21.52]})
    st.code("Số CP = (Vốn × % rủi ro/lệnh) ÷ (Giá vào − Cắt lỗ)", language=None, wrap_lines=True)
    st.caption("Các mức trên chỉ phục vụ kiểm thử hiển thị.")
