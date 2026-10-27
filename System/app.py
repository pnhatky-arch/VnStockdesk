from __future__ import annotations

import json
import os
import base64
import importlib
import io
import time
import wave
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import streamlit.components.v1 as components
from src.branding import PROJECT_NAME
from src.background_reads import BackgroundReads
from src import desk_grid as desk_grid_module
desk_grid_module = importlib.reload(desk_grid_module)
desk_dataframe, desk_data_editor = desk_grid_module.desk_dataframe, desk_grid_module.desk_data_editor
from src import timeframes as timeframes_module
timeframes_module = importlib.reload(timeframes_module)

from src import universe as universe_module
universe_module = importlib.reload(universe_module)
get_market_listing = universe_module.get_market_listing
MARKET_SCOPES = universe_module.MARKET_SCOPES
from src import data as data_module
data_module = importlib.reload(data_module)
get_history = data_module.get_history
refresh_history_incremental = data_module.refresh_history_incremental
from src import analyzer as analyzer_module
analyzer_module = importlib.reload(analyzer_module)
analyze_symbol = analyzer_module.analyze_symbol
from src.news import fetch_company_news, score_news
from src import valuation as valuation_module
valuation_module = importlib.reload(valuation_module)
load_valuation, attach_valuation, valuation_columns = valuation_module.load_valuation, valuation_module.attach_valuation, valuation_module.valuation_columns
from src import valuation_ui as valuation_ui_module
valuation_ui_module = importlib.reload(valuation_ui_module)
render_valuation, vt = valuation_ui_module.render_valuation, valuation_ui_module.vt
from src.watchlist import add_favorite, remove_favorite, is_favorite, load_watchlist
from src.portfolio_store import PortfolioStore
from src import ui_theme as ui_theme_module
ui_theme_module = importlib.reload(ui_theme_module)
FONT_STACK = ui_theme_module.FONT_STACK
palette, signal_colors, stylesheet = ui_theme_module.palette, ui_theme_module.signal_colors, ui_theme_module.stylesheet
from src.timeframes import resample_ohlcv, TIMEFRAME_ORDER, TIMEFRAME_CONFIG
from src.indicators import add_indicators
from src.wyckoff import analyze_wyckoff
from src.paths import PROJECT_ROOT, PROCESSED_DIR, ENV_FILE, RAW_DIR, STATE_DIR, DATA_ROOT, MARKET_DIR
from src.data_jobs import DataJobs, configure_next_data_directory
from src.paper_broker import PaperBroker
from src.bot_alerts import is_recent_alert
from src.trade_alerts import dismiss_fill, pending_fill, sync_latest_fill_from_ledgers
from src.alert_preferences import (
    load_alert_preferences, reset_alert_sound, save_alert_sound,
    selected_alert_sound, set_push_enabled,
)
from src import futures_data as futures_data_module
futures_data_module = importlib.reload(futures_data_module)
load_futures_bundle = futures_data_module.load_futures_bundle
load_futures_contracts = futures_data_module.load_futures_contracts
load_futures_quote = futures_data_module.load_futures_quote
from src import futures_engine as futures_engine_module
futures_engine_module = importlib.reload(futures_engine_module)
analyze_vn30f1m = futures_engine_module.analyze_vn30f1m
futures_ai_brief = futures_engine_module.futures_ai_brief
futures_wyckoff_events = futures_engine_module.futures_wyckoff_events
fibonacci_analysis = futures_engine_module.fibonacci_analysis
analyze_futures_chart_frame = futures_engine_module.analyze_futures_chart_frame
FUTURES_CHART_TIMEFRAMES = futures_engine_module.FUTURES_CHART_TIMEFRAMES
from src.portfolio_timeframes import portfolio_frame_evidence
from src.futures_broker import PaperFuturesBroker
from src.futures_trading_engine import futures_paper_cycle, futures_paper_scan_cycle
from src.futures_bot_manager import futures_bot_status, start_futures_bot, stop_futures_bot
from src import bot_manager as bot_manager_module
bot_manager_module = importlib.reload(bot_manager_module)
bot_status = bot_manager_module.bot_status
start_bot = bot_manager_module.start_bot
stop_bot = bot_manager_module.stop_bot
cleanup_legacy_bot_workers = bot_manager_module.cleanup_legacy_bot_workers
from src import validation as validation_module
validation_module = importlib.reload(validation_module)
walk_forward_validation = validation_module.walk_forward_validation
from src import i18n as i18n_module
i18n_module = importlib.reload(i18n_module)
LANGUAGES, tr, period, guide, ui_sentence = i18n_module.LANGUAGES, i18n_module.tr, i18n_module.period, i18n_module.guide, i18n_module.ui_sentence
from src import ai_assistant as ai_assistant_module
ai_assistant_module = importlib.reload(ai_assistant_module)
compact_ai_context = ai_assistant_module.compact_context
local_ai_answer = ai_assistant_module.local_answer
online_ai_answer = ai_assistant_module.online_answer
from src.index_engine import load_index_history, load_hose_breadth, analyze_vnindex, load_index_quote

# Executable code always lives in System. Data may be redirected to another
# drive, so deriving the worker root from PROCESSED_DIR breaks Windows launch.
ROOT = PROJECT_ROOT
BUILD_ID = "VNINDEX-20260903-1123"


# ============================================================
# CONFIG
# ============================================================

TF_LABELS = {
    "1D": "1D",
    "1W": "1W",
    "1M": "1M",
    "1Y": "1Y",
}

TF_LONG = {key: f"Nến {value['period']}" for key, value in TIMEFRAME_CONFIG.items()}
TF_ORDER = TIMEFRAME_ORDER

SIGNAL_STYLE = {
    "STRONG_BUY": ("#00c853", "STRONG BUY"),
    "BUY": ("#2ecc71", "BUY"),
    "WATCH_BUY": ("#7bd88f", "WATCH BUY"),
    "HOLD": ("#64b5f6", "HOLD"),
    "WATCH": ("#9aa4b2", "WATCH"),
    "REDUCE": ("#ffb74d", "REDUCE"),
    "AVOID": ("#ff8a65", "AVOID"),
    "SELL": ("#ef5350", "SELL"),
    "STRONG_SELL": ("#d32f2f", "STRONG SELL"),
}

SIGNAL_HELP = {
    "STRONG_BUY": "Mua mạnh: nhiều khung thời gian đồng thuận tăng với điểm tổng hợp cao. Vẫn cần xác định điểm vào và mức cắt lỗ.",
    "BUY": "Mua: cấu trúc, xu hướng và động lượng đang ủng hộ chiều tăng; có thể xem xét vị thế theo kế hoạch quản trị rủi ro.",
    "WATCH_BUY": "Theo dõi mua: tín hiệu tăng đang hình thành nhưng chưa đủ mạnh hoặc chưa đủ xác nhận để mua ngay.",
    "HOLD": "Nắm giữ: xu hướng vẫn tích cực nhưng lợi thế mua mới chưa rõ; ưu tiên quản lý vị thế đang có.",
    "WATCH": "Theo dõi: tín hiệu trung tính hoặc xung đột; chưa có lợi thế rõ cho hành động mua hay bán.",
    "REDUCE": "Giảm tỷ trọng: cấu trúc đang suy yếu; cân nhắc hạ rủi ro thay vì giữ toàn bộ vị thế.",
    "AVOID": "Tránh mua: xu hướng hoặc động lượng đang bất lợi; không phù hợp để mở vị thế mua mới.",
    "SELL": "Bán: cấu trúc và động lượng nghiêng mạnh về chiều giảm; ưu tiên bảo vệ vốn theo kế hoạch.",
    "STRONG_SELL": "Bán mạnh: nhiều khung thời gian đồng thuận giảm với điểm tổng hợp rất thấp.",
}

WYCKOFF_EVENT_HELP = {
    "SPRING": "Rũ bỏ: giá xuyên xuống hỗ trợ nhưng đóng cửa trở lại phía trên; có thể cho thấy lực bán đang được hấp thụ.",
    "SOS": "Sign of Strength: giá vượt kháng cự với khối lượng tương đối cao, thể hiện lực mua mạnh.",
    "LPS": "Last Point of Support: giá điều chỉnh về gần hỗ trợ/MA20 trong xu hướng tăng với khối lượng không quá lớn.",
    "UT": "Upthrust: giá xuyên lên kháng cự nhưng đóng cửa trở lại phía dưới; có thể là bẫy tăng giá.",
    "SOW": "Sign of Weakness: giá phá xuống hỗ trợ với khối lượng tương đối cao, thể hiện lực bán mạnh.",
    "NONE": "Chưa phát hiện sự kiện Wyckoff rõ ràng tại cây nến hiện tại.",
}

WYCKOFF_PHASE_HELP = {
    "ACCUMULATION": "Tích lũy: lực bán có thể đang được hấp thụ trước một xu hướng tăng.",
    "MARKUP": "Tăng giá: giá đã thoát vùng tích lũy và đang hình thành xu hướng tăng.",
    "DISTRIBUTION": "Phân phối: lực mua có thể đang được hấp thụ trước một xu hướng giảm.",
    "MARKDOWN": "Giảm giá: giá đã phá vùng phân phối và bước vào xu hướng giảm.",
    "TRADING_RANGE": "Đi ngang: giá chưa thể hiện xu hướng rõ ràng.",
    "UPPER_RANGE": "Giá nằm trong khoảng 30% phía trên của vùng giao dịch.",
    "LOWER_RANGE": "Giá nằm trong khoảng 30% phía dưới của vùng giao dịch.",
    "INSUFFICIENT_HISTORY": "Không đủ dữ liệu để phân tích cấu trúc Wyckoff.",
}

WYCKOFF_BIAS_HELP = {
    "BULLISH": "Thiên hướng tăng: cấu trúc hiện tại nghiêng về kịch bản tăng giá.",
    "BEARISH": "Thiên hướng giảm: cấu trúc hiện tại nghiêng về kịch bản giảm giá.",
    "NEUTRAL": "Trung tính: chưa đủ bằng chứng xác nhận hướng tăng hoặc giảm.",
}

MA_REGIME_HELP = {
    "STRONG_BULLISH": "Giá > MA20 > MA50 > MA100 > MA200: cấu trúc tăng mạnh và đồng bộ.",
    "BULLISH": "Giá và các MA ngắn hạn nghiêng tăng; xu hướng tích cực nhưng chưa đồng bộ hoàn toàn.",
    "RECOVERY": "Giá phục hồi trên MA20 nhưng hệ MA trung-dài hạn chưa xác nhận xu hướng tăng hoàn chỉnh.",
    "MIXED": "Các đường MA đan xen; cấu trúc xu hướng chưa rõ ràng.",
    "PULLBACK": "Giá đang điều chỉnh dưới MA20 trong bối cảnh cấu trúc lớn chưa gãy hoàn toàn.",
    "BEARISH": "Giá và các MA ngắn hạn nghiêng giảm; áp lực bán đang chiếm ưu thế.",
    "STRONG_BEARISH": "Giá < MA20 < MA50 < MA100 < MA200: cấu trúc giảm mạnh và đồng bộ.",
    "INSUFFICIENT_HISTORY": "Chưa đủ số nến để tính và phân loại đầy đủ hệ MA.",
}

st.set_page_config(
    page_title=PROJECT_NAME,
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)
if "legacy_bot_cleanup_done" not in st.session_state:
    cleanup_legacy_bot_workers(ROOT)
    st.session_state.legacy_bot_cleanup_done = True

if "ui_language" not in st.session_state:
    st.session_state.ui_language = "vi"
with st.sidebar:
    st.markdown(
        f'<div class="control-heading"><div class="control-symbol"><svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M4 7h16M4 17h16" stroke-width="1.6" stroke-linecap="round"/>'
        '<circle cx="9" cy="7" r="3" stroke-width="1.6" fill="var(--panel)"/>'
        '<circle cx="16" cy="17" r="3" stroke-width="1.6" fill="var(--panel)"/></svg></div>'
        f'<div><strong>{tr(st.session_state.ui_language, "control")}</strong><small>{PROJECT_NAME} · TRADING DESK</small></div></div>',
        unsafe_allow_html=True,
    )
    with st.expander("⚙ Cài đặt hệ thống", expanded=False):
        st.selectbox(
            tr(st.session_state.ui_language, "language"),
            list(LANGUAGES),
            format_func=lambda code: LANGUAGES[code],
            key="ui_language",
        )
        LANG = st.session_state.ui_language
        if "ui_light_mode" not in st.session_state:
            st.session_state.ui_light_mode = False
        st.toggle(
            f"☼ {tr(LANG, 'light')}",
            key="ui_light_mode",
            help=tr(LANG, "theme_help"),
        )
        alert_preferences = load_alert_preferences()
        if "push_notifications_enabled" not in st.session_state:
            st.session_state.push_notifications_enabled = alert_preferences["push_enabled"]
        push_enabled = st.toggle(
            "Thông báo đẩy", key="push_notifications_enabled",
            help="Bật hoặc tắt thông báo khớp lệnh cơ sở và hợp đồng tương lai.",
        )
        if bool(push_enabled) != alert_preferences["push_enabled"]:
            set_push_enabled(bool(push_enabled))
            if push_enabled:
                # Rendered after the dialog helpers are defined below.  A
                # token keeps its audio from replaying on unrelated reruns.
                st.session_state.push_notification_test_pending = True
                st.session_state.push_notification_test_token = str(time.time_ns())
        settings_sound = st.file_uploader(
            "Âm thanh thông báo", type=["mp3", "wav", "m4a", "ogg"],
            key="settings_alert_sound_upload", max_upload_size=5,
            help="MP3, WAV, M4A hoặc OGG · tối đa 5 MB",
        )
        if settings_sound is not None:
            if save_alert_sound(settings_sound.name, settings_sound.getvalue()):
                st.session_state.pop("trade_alert_sound_event", None)
                st.success(f"Đã tích hợp: {settings_sound.name}")
            else:
                st.error("Tệp âm thanh vượt quá 5 MB.")
        _, settings_sound_name = selected_alert_sound()
        st.caption(f"Âm đang dùng: {settings_sound_name}")
        if settings_sound_name != "Bốn kênh" and st.button(
            "Khôi phục âm mặc định", key="settings_reset_alert_sound", width="stretch"
        ):
            reset_alert_sound()
            st.session_state.pop("trade_alert_sound_event", None)
            st.rerun()
LANG = st.session_state.ui_language
UI_LIGHT = bool(st.session_state.ui_light_mode)
# Derived portfolio reports from the old engine must not survive a hot reload.
# Saved holdings and in-progress form inputs are intentionally left untouched.
if st.session_state.get("portfolio_analysis_engine") != "PRO_DECISION_4TF_CANDLES":
    for derived_key in ("portfolio_algorithm_result", "futures_portfolio_algorithm_result"):
        st.session_state.pop(derived_key, None)
    st.session_state.portfolio_analysis_engine = "PRO_DECISION_4TF_CANDLES"
if "system_operation_mode" not in st.session_state:
    st.session_state.system_operation_mode = "PAPER"
with st.sidebar:
    st.segmented_control(
        tr(LANG,"system_mode"), ["PAPER","LIVE"], default="PAPER",
        key="system_operation_mode", width="stretch",
        format_func=lambda mode: tr(LANG, "paper_system" if mode == "PAPER" else "live_system"),
    )
    if st.session_state.system_operation_mode == "LIVE":
        st.caption(f"● {tr(LANG,'live_readonly')}")
SYSTEM_MODE = st.session_state.system_operation_mode
CHART_THEME = "light" if UI_LIGHT else "dark"
UI_COLORS = palette(UI_LIGHT)
CHART_BG = UI_COLORS["panel"]
CHART_TEXT = UI_COLORS["text"]
CHART_GRID = UI_COLORS["grid"]
CHART_BORDER = UI_COLORS["border"]
CHART_CONTROL_BG = UI_COLORS["panel2"]
SIGNAL_STYLE = {key: (signal_colors(UI_LIGHT)[key], value[1]) for key, value in SIGNAL_STYLE.items()}

# ============================================================
# CSS — single shared appearance system for PAPER and LIVE.
# ============================================================
st.html(stylesheet(UI_LIGHT))
st.html("""<style>
.st-key-bot_start_control button,.st-key-futures_bot_start_control button{background:#2563eb!important;border-color:#2563eb!important;color:white!important}
.st-key-bot_stop_control button,.st-key-futures_bot_stop_control button{background:#dc2626!important;border-color:#dc2626!important;color:white!important}
.index-refresh-label{font-size:.875rem;font-weight:400;line-height:1.25rem;margin:0 0 .45rem 0;color:var(--text-color)}
.st-key-index_refresh_button button{min-height:2.5rem;margin:0!important}
.st-key-futures_bot_scan_scope [data-testid="stButtonGroup"],
.st-key-futures_bot_interval [data-testid="stButtonGroup"],
.st-key-futures_bot_risk_level [data-testid="stButtonGroup"],
.st-key-equity_bot_risk_level [data-testid="stButtonGroup"]{width:100%!important}
.st-key-futures_bot_scan_scope [data-testid="stButtonGroup"] button,
.st-key-futures_bot_interval [data-testid="stButtonGroup"] button,
.st-key-futures_bot_risk_level [data-testid="stButtonGroup"] button,
.st-key-equity_bot_risk_level [data-testid="stButtonGroup"] button{flex:1 1 0!important;justify-content:center!important;min-height:2.5rem!important}
.st-key-futures_bot_start_control button,.st-key-futures_bot_stop_control button,
.st-key-run_futures_once button{min-height:2.6rem!important}
.trade-fill-alert{--trade-accent:#22c55e;text-align:center;color:var(--text);padding:0 2px 2px}
.trade-fill-alert.trade-sell,.trade-fill-alert.trade-short,.trade-fill-alert.trade-stop{--trade-accent:#ef4444}
.trade-fill-alert.trade-profit{--trade-accent:#22c55e}
.trade-fill-pulse,.trade-fill-enter .trade-fill-pulse{width:62px;height:62px;margin:0 auto 9px;display:grid;place-items:center;border-radius:50%;color:#fff;background:var(--trade-accent);animation:trade-fill-icon-motion 1.15s ease-in-out infinite,trade-fill-icon-glow 1.15s ease-in-out infinite!important;transform-origin:center}
.trade-fill-pulse span{font-size:34px;line-height:1;font-weight:800}.trade-fill-title{color:var(--trade-accent);font-size:22px;font-weight:800;letter-spacing:.025em}.trade-fill-symbol{margin-top:2px;color:var(--text);font-size:15px;font-weight:700}.trade-fill-direction{display:inline-block;margin:7px 0 10px;padding:4px 11px;border-radius:999px;color:var(--trade-accent);background:color-mix(in srgb,var(--trade-accent) 12%,var(--panel));font-weight:800}
.trade-fill-grid{display:grid;grid-template-columns:1fr 1fr;column-gap:18px;row-gap:2px;text-align:left;padding:8px 12px;border-top:1px solid var(--border);border-bottom:1px solid var(--border);font-size:13px}.trade-fill-grid span,.trade-fill-grid strong{min-height:30px;padding:4px 0;display:flex;align-items:center}.trade-fill-grid span{color:var(--muted)}.trade-fill-grid strong{color:var(--text);justify-content:flex-end;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.trade-fill-grid strong:nth-child(4),.trade-fill-grid strong:nth-child(8){color:var(--trade-accent);font-size:16px}
.trade-fill-sound,.trade-fill-persistent{min-height:42px;margin-top:9px;padding:9px 12px;box-sizing:border-box;display:flex;align-items:center;text-align:left;border:1px solid var(--border);border-radius:10px;background:var(--panel2);font-size:13px}.trade-fill-sound strong{color:var(--trade-accent)}.trade-fill-persistent{color:var(--text);background:color-mix(in srgb,#ef4444 7%,var(--panel))}.trade-fill-persistent span{color:#ef4444;margin-right:8px}
.push-test-button-spacer{height:16px;min-height:16px}
.trade-fill-grid strong.pnl-positive{color:#16a34a!important;font-size:16px;font-weight:800}.trade-fill-grid strong.pnl-negative{color:#dc2626!important;font-size:16px;font-weight:800}.trade-fill-grid strong.pnl-flat{color:var(--text)!important}
@keyframes trade-fill-icon-motion{0%,100%{transform:translateY(0) scale(1)}45%{transform:translateY(-7px) scale(1.06)}65%{transform:translateY(1px) scale(.98)}}
@keyframes trade-fill-icon-glow{0%,100%{box-shadow:0 0 0 7px color-mix(in srgb,var(--trade-accent) 12%,transparent),0 0 14px color-mix(in srgb,var(--trade-accent) 28%,transparent)}50%{box-shadow:0 0 0 13px color-mix(in srgb,var(--trade-accent) 5%,transparent),0 0 30px color-mix(in srgb,var(--trade-accent) 55%,transparent)}}
.risk-confirm-icon{--risk-accent:#f59e0b;width:58px;height:58px;margin:2px auto 14px;display:grid;place-items:center;border-radius:50%;background:var(--risk-accent);color:#fff;font-size:30px;font-weight:850;animation:risk-confirm-motion 1.15s ease-in-out infinite,risk-confirm-glow 1.15s ease-in-out infinite}
.risk-confirm-icon.risk-low{--risk-accent:#16a34a}.risk-confirm-icon.risk-medium{--risk-accent:#f59e0b}.risk-confirm-icon.risk-high{--risk-accent:#dc2626}
.risk-confirm-title{text-align:center;color:var(--text);font-size:20px;font-weight:800;margin-bottom:12px}
@keyframes risk-confirm-motion{0%,100%{transform:translateY(0) scale(1)}45%{transform:translateY(-6px) scale(1.06)}65%{transform:translateY(1px) scale(.98)}}
@keyframes risk-confirm-glow{0%,100%{box-shadow:0 0 0 6px color-mix(in srgb,var(--risk-accent) 12%,transparent),0 0 12px color-mix(in srgb,var(--risk-accent) 25%,transparent)}50%{box-shadow:0 0 0 12px color-mix(in srgb,var(--risk-accent) 5%,transparent),0 0 28px color-mix(in srgb,var(--risk-accent) 55%,transparent)}}
@media(prefers-reduced-motion:reduce){.trade-fill-pulse,.risk-confirm-icon{animation:none!important}.trade-fill-pulse{box-shadow:0 0 0 8px color-mix(in srgb,var(--trade-accent) 14%,transparent)}}
</style>""")


# ============================================================
# HELPERS
# ============================================================

@st.cache_data(show_spinner=False, ttl=3600)
def load_universe(scope: str):
    return get_market_listing(scope)


@st.cache_data(show_spinner=False, ttl=1800)
def load_symbol(symbol: str):
    return get_history(symbol)


@st.cache_data(show_spinner=False, ttl=1800)
def load_vnindex_cached(symbol: str = "VNINDEX", refresh_token: int = 0):
    return load_index_history(symbol=symbol, refresh=bool(refresh_token))


@st.cache_data(show_spinner=False, ttl=900)
def load_company_news(symbol: str, refresh_news: bool = False):
    return fetch_company_news(symbol, refresh=refresh_news)


@st.cache_data(show_spinner=False, ttl=900)
def analyze_cached(symbol: str, df: pd.DataFrame):
    # Source change invalidates Streamlit's cached five-timeframe results.
    assert timeframes_module.TIMEFRAME_ORDER == ["1D", "1W", "1M", "1Y"]
    return analyze_symbol(symbol, df)


@st.cache_data(show_spinner=False, ttl=3600)
def validate_cached(df: pd.DataFrame, horizon: int, step: int, engine_version: str):
    return walk_forward_validation(df, horizon=horizon, step=step)


@st.cache_resource
def dashboard_reads():
    return BackgroundReads()


def load_vn30f1m_cached(refresh_token: int = 0, symbol: str = "VN30F1M"):
    path = RAW_DIR / "futures"
    job = dashboard_reads().poll(
        ("futures_bars", symbol), lambda: load_futures_bundle(path, refresh=True, symbol=symbol),
        ttl=300, force=bool(refresh_token),
    )
    return job["value"] if job["value"] is not None else load_futures_bundle(path, symbol=symbol, cache_only=True)


def load_futures_contracts_cached(refresh_token: int = 0):
    job = dashboard_reads().poll("contracts", load_futures_contracts, ttl=900, force=bool(refresh_token))
    if job["value"] is not None:
        return job["value"]
    from src.futures_data import _contract_info
    # Show saved exchange codes too, without pretending the list is current.
    codes = {"VN30F1M"}
    for path in (RAW_DIR / "futures").glob("*_1d.csv"):
        codes.add(path.stem.rsplit("_", 1)[0].upper())
    return [_contract_info(code) for code in sorted(codes)], {
        "provider": "CACHE", "source_label": "Danh sách lưu · đang cập nhật nền",
        "count": len(codes), "errors": {},
    }


def load_futures_quote_cached(symbol: str):
    job = dashboard_reads().poll(("quote", symbol), lambda: load_futures_quote(symbol), ttl=2)
    quote = job["value"]
    if quote is None:
        return {"status": "PENDING", "symbol": symbol, "price": None, "errors": {}}
    # Never label a retained quote as fresh while its provider is stalled.
    quote = dict(quote)
    if quote.get("market_time"):
        stamp = pd.to_datetime(quote["market_time"], utc=True, errors="coerce")
        if pd.notna(stamp):
            quote["market_age_seconds"] = max(0, (pd.Timestamp.now(tz="UTC") - stamp).total_seconds())
    return quote


def active_futures_paper_positions() -> dict[str, dict]:
    """Return only genuinely open PAPER futures ledgers, keyed by contract."""
    positions: dict[str, dict] = {}
    for path in sorted(STATE_DIR.glob("paper_futures_*.json")):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            side, quantity = str(state.get("side", "FLAT")).upper(), int(state.get("quantity", 0))
            if side not in {"LONG", "SHORT"} or quantity <= 0:
                continue
            symbol = path.stem.removeprefix("paper_futures_").upper()
            positions[symbol] = {"symbol": symbol, "path": path, **state}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return positions


@st.fragment(run_every=5)
def realtime_futures_panel(symbol: str, *, compact: bool = False) -> None:
    """Independent low-latency quote/P&L panel; candle analytics remain close-confirmed."""
    quote = load_futures_quote_cached(symbol)
    if quote.get("status") == "PENDING":
        st.caption(f"◌ {symbol}: đang chờ quote nền · dữ liệu nến lưu vẫn hiển thị bên dưới")
        return
    if quote.get("status") != "OK":
        st.error(f"● Realtime {symbol}: mất quote · đang giữ dữ liệu nến gần nhất")
        return
    live_quotes = dict(st.session_state.get("realtime_futures_quotes", {}))
    live_quotes[symbol] = quote
    st.session_state.realtime_futures_quotes = live_quotes
    price = float(quote["price"])
    received = pd.Timestamp(quote["received_at"]).tz_convert("Asia/Ho_Chi_Minh")
    live_readonly = globals().get("SYSTEM_MODE", "PAPER") == "LIVE"
    broker = None if live_readonly else PaperFuturesBroker(STATE_DIR / f"paper_futures_{symbol.lower()}.json")
    account = {"side":"READ-ONLY","quantity":0,"unrealized_pnl_vnd":0} if live_readonly else broker.snapshot(price)
    pnl = float(account.get("unrealized_pnl_vnd", 0))
    source = quote.get("source_label", "N/A")
    latency = int(quote.get("request_latency_ms", 0))
    market_age = quote.get("market_age_seconds")
    freshness = f"age {float(market_age):.1f}s" if market_age is not None else "age N/A"
    bid_ask = f"{fmt(quote.get('bid'),1)} / {fmt(quote.get('ask'),1)}"
    if compact:
        st.markdown(
            f"<div class='bot-status bot-running'>● Realtime · {symbol}<br>"
            f"{price:,.1f} · {'READ-ONLY' if live_readonly else f'P&L {pnl:+,.0f} ₫'}</div>", unsafe_allow_html=True,
        )
        st.caption(f"Bid/Ask {bid_ask} · {source} · {received:%H:%M:%S} · {freshness} · {latency} ms")
        if market_age is not None and float(market_age) > 15:
            st.warning(f"Quote {symbol} chậm {float(market_age):.1f} giây; không dùng nhãn realtime để kích hoạt lệnh.")
        return
    rt1, rt2, rt3, rt4 = st.columns(4)
    rt1.metric(f"{symbol} · Realtime", f"{price:,.1f}")
    rt2.metric("Bid / Ask", bid_ask)
    rt3.metric("Unrealized P&L realtime", "—" if live_readonly else f"{pnl:+,.0f} ₫")
    rt4.metric("Nguồn · thời điểm nhận", source, delta=f"{received:%H:%M:%S} · {freshness} · {latency} ms")
    if live_readonly:
        st.caption("● LIVE QUOTE · READ-ONLY · tự cập nhật mỗi 5 giây · không sử dụng dữ liệu PAPER.")
        return
    performance = broker.performance_report(price)
    multiplier = float(broker.config.contract_multiplier_vnd)
    live_quantity = int(account.get("quantity", 0))
    lv1, lv2, lv3, lv4 = st.columns(4)
    lv1.metric("Vị thế LIVE", f"{account.get('side','FLAT')} · {live_quantity} HĐ")
    lv2.metric("Giá trị 1 hợp đồng", f"{price * multiplier:,.0f} ₫")
    lv3.metric("Realized / Unrealized P&L", f"{performance['realized_pnl_vnd']:+,.0f} / {performance['unrealized_pnl_vnd']:+,.0f} ₫")
    lv4.metric("Equity · hiệu suất", f"{performance['equity_after_total_vnd']:,.0f} ₫", delta=f"{performance['return_pct']:+.2f}%")
    st.caption("● LIVE QUOTE · tự cập nhật mỗi 5 giây · P&L định giá theo quote mới; chỉ báo kỹ thuật xác nhận theo nến đóng.")
    if market_age is not None and float(market_age) > 15:
        st.warning(f"Quote {symbol} đang trễ {float(market_age):.1f} giây; hệ thống không coi đây là giá realtime để kích hoạt lệnh.")


@st.fragment(run_every=5)
def realtime_index_panel(symbol: str, fallback_close: float | None = None) -> None:
    """Update index points independently, without rerunning the dashboard."""
    # Community VNStock is shared with scanners/futures. Refresh the fragment at
    # 5s for a responsive UI, but cap provider calls to four/minute per symbol.
    job = dashboard_reads().poll(("index_quote", symbol), lambda: load_index_quote(symbol), ttl=15)
    quote = job.get("value")
    if quote is None:
        st.metric(f"{symbol} · đang kết nối live", "—" if fallback_close is None else f"{fallback_close:,.2f} điểm")
        st.caption("◌ Đang lấy quote nền; số đang hiển thị là nến đóng gần nhất, không gắn nhãn realtime.")
        return
    if quote.get("status") != "OK":
        st.metric(f"{symbol} · nến đóng gần nhất", "—" if fallback_close is None else f"{fallback_close:,.2f} điểm")
        st.warning("Mất nguồn quote live; biểu đồ và phân tích vẫn dùng dữ liệu nến đã xác nhận.")
        return
    price = float(quote["price"])
    change, change_pct = quote.get("change"), quote.get("change_pct")
    delta = "Chưa có giá tham chiếu"
    if change is not None:
        delta = f"{float(change):+.2f} điểm"
        if change_pct is not None:
            delta += f" ({float(change_pct):+.2f}%)"
    received = pd.to_datetime(quote.get("received_at"), utc=True, errors="coerce")
    stamp = "—" if pd.isna(received) else received.tz_convert("Asia/Ho_Chi_Minh").strftime("%H:%M:%S")
    c1, c2, c3 = st.columns([1.3, 1, 1])
    c1.metric(f"{symbol} · Live", f"{price:,.2f} điểm", delta=delta)
    c2.metric("Thay đổi", "—" if change is None else f"{float(change):+.2f} điểm",
              delta="—" if change_pct is None else f"{float(change_pct):+.2f}%")
    c3.metric("Cập nhật", stamp, delta=f"{quote.get('request_latency_ms', 0)} ms")
    st.caption(f"● Hiển thị tự cập nhật mỗi 5 giây, quote mới tối đa mỗi 15 giây, không refresh trang · {quote.get('source_label', 'N/A')}"
               + (f" · giờ thị trường {quote['market_time']}" if quote.get("market_time") else ""))


def fmt(v, digits=2):
    if v is None or pd.isna(v):
        return "—"
    return f"{float(v):,.{digits}f}"


RISK_CONFIRMATION = {
    "LOW": {
        "name":"Thấp", "tone":"An toàn cao",
        "summary":"Ưu tiên bảo toàn vốn; BOT khó vào lệnh hơn và sử dụng vị thế nhỏ hơn.",
        "rules":["Confidence tối thiểu 78%", "Đồng thuận đa khung tối thiểu 75%",
                 "Khoảng 60% ngân sách rủi ro và 70% quy mô vị thế chuẩn"],
    },
    "MEDIUM": {
        "name":"Trung bình", "tone":"Cân bằng",
        "summary":"Giữ nguyên tiêu chuẩn vào lệnh và quy mô quản trị mặc định của hệ thống.",
        "rules":["Ngưỡng xác nhận tiêu chuẩn", "100% ngân sách rủi ro chuẩn",
                 "Phù hợp vận hành PAPER thông thường"],
    },
    "HIGH": {
        "name":"Cao", "tone":"Linh hoạt cao",
        "summary":"BOT dễ vào lệnh hơn và có thể xét WATCH BUY mạnh; biến động tài khoản có thể lớn hơn.",
        "rules":["Confidence tối thiểu 62%", "Đồng thuận đa khung tối thiểu 55%",
                 "Tối đa 125% ngân sách rủi ro và 115% quy mô vị thế chuẩn"],
    },
}


@st.dialog("Xác nhận quản trị rủi ro", width="small")
def confirm_bot_risk_and_start(*, market: str, level: str, interval: int,
                               symbol: str | None = None, scope: str | None = None) -> None:
    detail = RISK_CONFIRMATION[level]
    market_name = "BOT cổ phiếu" if market == "equity" else "BOT hợp đồng tương lai"
    st.markdown(
        f"<div class='risk-confirm-icon risk-{level.lower()}'>!</div><div class='risk-confirm-title'>{detail['name']} · {detail['tone']}</div>",
        unsafe_allow_html=True,
    )
    st.write(detail["summary"])
    st.markdown("\n".join(f"- {rule}" for rule in detail["rules"]))
    st.warning(
        "Stop Loss, Take Profit, khóa lỗ ngày, giới hạn tiền mặt/tỷ trọng và điều kiện dữ liệu "
        "vẫn luôn hoạt động. Mức Cao không bảo đảm có lợi nhuận."
    )
    target = scope or symbol or "—"
    st.caption(f"{market_name} · {target} · chu kỳ {interval} phút")
    agree_col, cancel_col = st.columns(2)
    if agree_col.button("Đồng ý và chạy BOT", type="primary", width="stretch", key=f"confirm_risk_{market}_{level}"):
        try:
            with st.spinner("Đang khởi động BOT…"):
                if market == "equity":
                    start_bot(ROOT, int(interval), symbol=symbol, scope=scope, risk_level=level)
                    st.session_state.equity_bot_risk_applied = level
                else:
                    start_futures_bot(ROOT, int(interval), str(symbol), level)
                    st.session_state.futures_bot_risk_applied = level
            st.session_state.pop("pending_bot_risk_confirmation", None)
            st.toast(f"Đã chạy {market_name} · Rủi ro {detail['name']}")
            st.rerun()
        except (RuntimeError, ValueError, OSError) as exc:
            st.error(str(exc))
    if cancel_col.button("Hủy", width="stretch", key=f"cancel_risk_{market}_{level}"):
        applied_key = f"{'equity' if market == 'equity' else 'futures'}_bot_risk_applied"
        choice_key = f"{'equity' if market == 'equity' else 'futures'}_bot_risk_level"
        st.session_state[f"{choice_key}_reset"] = st.session_state.get(applied_key, "MEDIUM")
        st.session_state.pop("pending_bot_risk_confirmation", None)
        st.rerun()


def _trade_alert_presentation(order: dict) -> tuple[str, str, str]:
    reason = str(order.get("reason") or "").upper()
    action = str(order.get("action") or order.get("side") or "").upper()
    if "STOP" in reason:
        return "ĐÃ CẮT LỖ", "STOP LOSS", "trade-stop"
    if "TARGET" in reason or "TAKE_PROFIT" in reason:
        return "ĐÃ CHỐT LỜI", "TAKE PROFIT", "trade-profit"
    if "SHORT" in action:
        return "ĐÃ KHỚP LỆNH", "SHORT", "trade-short"
    if action == "SELL" or action.startswith("CLOSE_"):
        return "ĐÃ KHỚP LỆNH", "BÁN / ĐÓNG", "trade-sell"
    return "ĐÃ KHỚP LỆNH", "MUA / LONG", "trade-long"


def _selected_trade_alert_sound() -> tuple[Path | None, str]:
    return selected_alert_sound()


def _save_trade_alert_sound(uploaded_file) -> bool:
    """Persist one user-selected alert sound outside the System package."""
    return save_alert_sound(uploaded_file.name, uploaded_file.getvalue())


def _reset_trade_alert_sound() -> None:
    reset_alert_sound()
    st.session_state.pop("trade_alert_sound_event", None)


def _play_trade_alert_sound() -> None:
    """Play the user's saved alert sound, or the built-in four-note cue."""
    custom_sound, _ = _selected_trade_alert_sound()
    if custom_sound is not None:
        mime = {".mp3": "audio/mp3", ".wav": "audio/wav", ".m4a": "audio/mp4", ".ogg": "audio/ogg"}.get(
            custom_sound.suffix.lower(), "audio/mpeg"
        )
        st.audio(custom_sound.read_bytes(), format=mime, autoplay=True, width="stretch")
        return
    sample_rate, duration = 16_000, 1.05
    timeline = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    tone = np.zeros_like(timeline, dtype=np.float32)
    for index, frequency in enumerate((523.25, 659.25, 783.99, 1046.50)):
        start, length = 0.04 + index * 0.13, 0.42
        mask = (timeline >= start) & (timeline < start + length)
        local_time = timeline[mask] - start
        envelope = np.sin(np.pi * local_time / length) ** 2
        tone[mask] += (.095 * envelope * np.sin(2 * np.pi * frequency * local_time)).astype(np.float32)
    st.audio(tone, sample_rate=sample_rate, autoplay=True, width="stretch")


def _repeating_trade_alert_sound(*, event_id: str, interval_seconds: int = 30) -> None:
    """Play now, then replay while the persistent alert remains mounted."""
    custom_sound, _ = _selected_trade_alert_sound()
    if custom_sound is not None:
        payload = custom_sound.read_bytes()
        mime = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".ogg": "audio/ogg"}.get(
            custom_sound.suffix.lower(), "audio/mpeg"
        )
    else:
        sample_rate, duration = 16_000, 1.05
        timeline = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        tone = np.zeros_like(timeline, dtype=np.float32)
        for index, frequency in enumerate((523.25, 659.25, 783.99, 1046.50)):
            start, length = 0.04 + index * 0.13, 0.42
            mask = (timeline >= start) & (timeline < start + length)
            local_time = timeline[mask] - start
            envelope = np.sin(np.pi * local_time / length) ** 2
            tone[mask] += (.095 * envelope * np.sin(2 * np.pi * frequency * local_time)).astype(np.float32)
        pcm = (np.clip(tone, -1, 1) * 32767).astype("<i2").tobytes()
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(sample_rate); wav.writeframes(pcm)
        payload, mime = output.getvalue(), "audio/wav"
    encoded = base64.b64encode(payload).decode("ascii")
    safe_id = "alert_" + "".join(character for character in event_id if character.isalnum())[:40]
    components.html(
        f"""<audio id="{safe_id}" preload="auto" src="data:{mime};base64,{encoded}"></audio>
        <script>
        (() => {{
          const audio = document.getElementById({json.dumps(safe_id)});
          const play = () => {{ audio.currentTime = 0; audio.play().catch(() => {{}}); }};
          play(); window.setInterval(play, {max(1, int(interval_seconds)) * 1000});
        }})();
        </script>""",
        height=1,
    )


@st.dialog("Kiểm tra thông báo đẩy", width="small")
def render_push_notification_test() -> None:
    """Confirm visually and audibly that alerts were enabled by the user."""
    token = st.session_state.get("push_notification_test_token", "push-test")
    _, alert_sound_name = _selected_trade_alert_sound()
    _repeating_trade_alert_sound(event_id=f"push_test_{token}", interval_seconds=30)
    st.markdown(
        f"""
        <div class="trade-fill-alert trade-long trade-fill-enter">
          <div class="trade-fill-pulse"><span>✓</span></div>
          <div class="trade-fill-title">THÔNG BÁO ĐẨY ĐÃ BẬT</div>
          <div class="trade-fill-symbol">VnStockDesk · Kiểm tra hệ thống</div>
          <div class="trade-fill-direction">HOẠT ĐỘNG</div>
          <div class="trade-fill-sound">🔊 &nbsp; Âm báo:&nbsp; <strong>{alert_sound_name}</strong></div>
          <div class="trade-fill-persistent"><span>●</span> Bạn sẽ nhận cảnh báo khi BOT khớp lệnh.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.html('<div class="push-test-button-spacer" aria-hidden="true"></div>')
    if st.button("Đóng thông báo kiểm tra", type="primary", width="stretch", key=f"close_push_test_{token}"):
        st.session_state.pop("push_notification_test_pending", None)
        st.session_state.pop("push_notification_test_sound_token", None)
        st.rerun()


# Show the test alert before the dashboard starts its heavier market analysis.
# Streamlit streams this dialog to the client as soon as it is built.
if st.session_state.get("push_notification_test_pending"):
    render_push_notification_test()


def render_trade_fill_alert(event: dict) -> None:
    order = event.get("order", {})
    title, badge, color_class = _trade_alert_presentation(order)
    event_id = str(event["id"])
    market = str(event.get("market", "equity"))
    price = float(order.get("price", 0) or 0)
    quantity = int(order.get("quantity", 0) or 0)
    pnl = order.get("pnl_vnd")
    pnl_value = None if pnl is None else float(pnl)
    pnl_class = "pnl-flat" if pnl_value is None or pnl_value == 0 else ("pnl-positive" if pnl_value > 0 else "pnl-negative")
    pnl_display = "—" if pnl_value is None else f"{pnl_value:+,.0f} ₫".replace(",", ".")
    unit = "HĐ" if market == "futures" else "CP"
    amount = price * quantity * (100_000 if market == "futures" else 1_000)
    action = str(order.get("action") or order.get("side") or badge).replace("_", " ")
    _, alert_sound_name = _selected_trade_alert_sound()
    alert_is_new = st.session_state.get("trade_alert_visual_event") != event_id
    if alert_is_new:
        st.session_state.trade_alert_visual_event = event_id
    entrance_class = " trade-fill-enter" if alert_is_new else ""
    try:
        order_time = pd.Timestamp(order.get("time"))
        order_time = order_time.tz_localize("UTC") if order_time.tzinfo is None else order_time
        display_time = order_time.tz_convert("Asia/Ho_Chi_Minh").strftime("%d/%m/%Y %H:%M:%S")
    except (TypeError, ValueError):
        display_time = str(order.get("time") or "—")
    with st.container(key="trade_fill_overlay"):
        st.markdown('<div class="trade-fill-modal-heading">THÔNG BÁO KHỚP LỆNH</div>', unsafe_allow_html=True)
        _repeating_trade_alert_sound(event_id=event_id, interval_seconds=30)
        st.markdown(
            f"""
            <div class="trade-fill-alert {color_class}{entrance_class}">
              <div class="trade-fill-pulse"><span>✓</span></div>
              <div class="trade-fill-title">{title}</div>
              <div class="trade-fill-symbol">{event.get('symbol','—')} · {event.get('mode','—')}</div>
              <div class="trade-fill-direction">{badge}</div>
              <div class="trade-fill-grid">
                <span>Trạng thái</span><strong>{action}</strong>
                <span>Giá khớp</span><strong>{price:,.3f}</strong>
                <span>Khối lượng</span><strong>{quantity:,} {unit}</strong>
                <span>Thành tiền tham chiếu</span><strong>{f'{amount:,.0f}'.replace(',', '.')} ₫</strong>
                <span>Lãi/lỗ ghi nhận</span><strong class="{pnl_class}">{pnl_display}</strong>
                <span>Thời gian</span><strong>{display_time}</strong>
              </div>
              <div class="trade-fill-sound">🔊 &nbsp; Âm báo:&nbsp; <strong>{alert_sound_name}</strong></div>
              <div class="trade-fill-persistent"><span>●</span> Thông báo giữ nguyên cho đến khi bấm tắt.</div>
            </div>
            """, unsafe_allow_html=True,
        )
        with st.expander("🔊 Chọn âm báo khớp lệnh", expanded=False):
            uploaded_alert_sound = st.file_uploader(
                "Chọn tệp âm thanh", type=["mp3", "wav", "m4a", "ogg"],
                key=f"trade_alert_sound_upload_{event_id}",
                help="MP3, WAV, M4A hoặc OGG · tối đa 5 MB", max_upload_size=5,
                label_visibility="collapsed",
            )
            if uploaded_alert_sound is not None:
                if _save_trade_alert_sound(uploaded_alert_sound):
                    st.session_state.pop("trade_alert_sound_event", None)
                    st.success(f"Đã tích hợp: {uploaded_alert_sound.name}")
                else:
                    st.error("Tệp âm thanh vượt quá 5 MB.")
            _, current_sound_name = _selected_trade_alert_sound()
            st.caption(f"Đang dùng: {current_sound_name}")
            if current_sound_name != "Bốn kênh" and st.button(
                "Khôi phục âm mặc định", key=f"reset_trade_alert_sound_{event_id}", width="stretch"
            ):
                _reset_trade_alert_sound()
                st.rerun()
        replay, details, close = st.columns(3)
        if replay.button("🔊 Phát lại âm báo", width="stretch", key=f"replay_fill_{event_id}"):
            _play_trade_alert_sound()
        if details.button("Xem chi tiết lệnh", width="stretch", key=f"details_fill_{event_id}"):
            st.session_state[f"show_fill_{event_id}"] = not st.session_state.get(f"show_fill_{event_id}", False)
        if close.button(
            "Tắt thông báo",
            type="primary",
            width="stretch",
            key=f"dismiss_fill_{event_id}",
        ):
            _dismiss_trade_fill_alert(event_id)
            # A full rerun is intentional: some Streamlit clients retain a
            # position:fixed fragment node after a fragment-only refresh.
            st.rerun()
        if st.session_state.get(f"show_fill_{event_id}"):
            st.markdown("**Chi tiết lệnh đã ghi nhận**")
            desk_dataframe(themed_dataframe(pd.DataFrame([order])), width="stretch", hide_index=True)


def _dismiss_trade_fill_alert(event_id: str) -> None:
    """Persist dismissal before Streamlit's fragment rerun begins."""
    dismiss_fill(event_id)
    st.session_state.pop("trade_alert_sound_event", None)
    st.session_state.pop("trade_alert_visual_event", None)
    st.session_state.pop(f"show_fill_{event_id}", None)


@st.fragment(run_every=1)
def watch_trade_fill_alert() -> None:
    alert_slot = st.empty()
    if not load_alert_preferences()["push_enabled"]:
        alert_slot.empty()
        return
    event = pending_fill()
    if not event:
        try:
            sync_latest_fill_from_ledgers(STATE_DIR)
        except (OSError, ValueError, TypeError):
            pass
        event = pending_fill()
    if event:
        with alert_slot.container():
            render_trade_fill_alert(event)
    else:
        # Explicitly clear the previous fragment tree. A no-output fragment
        # rerun can otherwise leave the fixed modal mounted in some clients.
        alert_slot.empty()


def performance_analytics_chart(report: dict, *, key: str, title: str) -> None:
    """Render the shared professional PAPER performance dashboard."""
    fig = make_subplots(
        rows=2, cols=2, shared_xaxes=False, vertical_spacing=.16, horizontal_spacing=.09,
        row_heights=[.70, .30], specs=[[{}, {}], [{"colspan": 2}, None]],
        subplot_titles=(tr(LANG,"equity_curve_title"), tr(LANG,"trade_pnl_title"), tr(LANG,"drawdown_title")),
    )
    curve = pd.DataFrame(report.get("equity_curve", []))
    if not curve.empty:
        curve["time"] = pd.to_datetime(curve["time"], errors="coerce", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")
        curve["equity_vnd"] = pd.to_numeric(curve["equity_vnd"], errors="coerce")
        curve["drawdown_pct"] = pd.to_numeric(curve.get("drawdown_pct", 0), errors="coerce").fillna(0)
        line_color = UI_COLORS['green'] if float(report.get("total_pnl_vnd", 0)) >= 0 else UI_COLORS['red']
        fig.add_trace(go.Scatter(
            x=curve["time"], y=curve["equity_vnd"], mode="lines", name="Equity glow",
            line={"color":line_color,"width":11,"shape":"spline"}, opacity=.12,
            hoverinfo="skip", showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=curve["time"], y=curve["equity_vnd"], mode="lines+markers", name="Equity",
            line={"color":line_color,"width":3.5,"shape":"spline"},
            marker={"size":7,"color":UI_COLORS['amber'],"line":{"width":1.5,"color":CHART_BG}},
            customdata=curve[["kind","drawdown_pct"]].astype(str).to_numpy(),
            hovertemplate="%{x|%d/%m/%Y %H:%M}<br><b>Equity %{y:,.0f} ₫</b><br>%{customdata[0]}<br>Drawdown %{customdata[1]}%<extra></extra>",
        ), row=1, col=1)
        fig.add_hline(
            y=float(report.get("capital_before_pnl_vnd", 0)), line_dash="dot", line_width=1.4,
            line_color=UI_COLORS['amber'], annotation_text=tr(LANG,"capital_before_pnl"), annotation_position="top left",
            row=1, col=1,
        )
        fig.add_trace(go.Scatter(
            x=curve["time"], y=curve["drawdown_pct"], mode="lines", name="Drawdown",
            line={"color":UI_COLORS['red'],"width":2.2,"shape":"spline"}, fill="tozeroy",
            fillcolor="rgba(255,90,103,.18)",
            hovertemplate="%{x|%d/%m %H:%M}<br>Drawdown <b>%{y:.2f}%</b><extra></extra>",
        ), row=2, col=1)
    trades = pd.DataFrame(report.get("close_orders", []))
    if not trades.empty:
        trades["time"] = pd.to_datetime(trades["time"], errors="coerce", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")
        trades["pnl_vnd"] = pd.to_numeric(trades["pnl_vnd"], errors="coerce").fillna(0)
        trades["cumulative_pnl_vnd"] = trades["pnl_vnd"].cumsum()
        for field, default in (("action","CLOSE"),("quantity",0),("price",0),("reason","—")):
            if field not in trades:
                trades[field] = default
        fig.add_trace(go.Bar(
            x=trades["time"], y=trades["pnl_vnd"], name="P&L từng lệnh",
            marker={"color":[UI_COLORS['green'] if pnl >= 0 else UI_COLORS['red'] for pnl in trades["pnl_vnd"]],
                    "line":{"width":0}, "cornerradius":"28%"}, opacity=.88,
            customdata=trades[["action","quantity","price","reason"]].astype(str).to_numpy(),
            hovertemplate=("%{x|%d/%m/%Y %H:%M}<br><b>P&L %{y:+,.0f} ₫</b><br>"
                           "%{customdata[0]} · %{customdata[1]} @ %{customdata[2]}<br>%{customdata[3]}<extra></extra>"),
        ), row=1, col=2)
        fig.add_trace(go.Scatter(
            x=trades["time"], y=trades["cumulative_pnl_vnd"], name="P&L lũy kế",
            mode="lines+markers", line={"color":UI_COLORS['purple'],"width":2.7,"shape":"spline"},
            marker={"size":6,"color":UI_COLORS['amber']},
            hovertemplate="P&L lũy kế <b>%{y:+,.0f} ₫</b><extra></extra>",
        ), row=1, col=2)
    else:
        fig.add_annotation(text=tr(LANG,"no_closed_trades"), x=.77, y=.72, xref="paper", yref="paper",
                           showarrow=False, font={"color":CHART_TEXT,"size":15})
    fig.add_hline(y=0, line_dash="dot", line_color=CHART_BORDER, line_width=1, row=1, col=2)
    fig.add_hline(y=0, line_color=CHART_BORDER, line_width=1, row=2, col=1)
    fig.update_layout(
        title={"text":title,"x":.012,"xanchor":"left","font":{"size":18,"color":UI_COLORS['purple']}},
        height=590, margin={"l":30,"r":25,"t":85,"b":30}, paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG, font={"color":CHART_TEXT,"size":12,"family":FONT_STACK}, hovermode="x unified",
        legend={"orientation":"h","y":1.095,"x":1,"xanchor":"right","bgcolor":"rgba(0,0,0,0)"},
        bargap=.38, uirevision=key,
    )
    fig.update_annotations(font={"color":CHART_TEXT,"size":12})
    fig.update_xaxes(gridcolor=CHART_GRID, showline=True, linecolor=CHART_BORDER, zeroline=False)
    fig.update_yaxes(gridcolor=CHART_GRID, showline=True, linecolor=CHART_BORDER, zeroline=False, tickformat=",.0f")
    fig.update_yaxes(ticksuffix="%", tickformat=".2f", row=2, col=1)
    if UI_LIGHT:
        # The app's appearance switch is independent of Streamlit's native
        # theme. Pin every text surface so dark-template tick/legend colors
        # cannot survive on a white report canvas.
        report_font = {"family": FONT_STACK, "color": CHART_TEXT, "size": 13}
        fig.update_layout(
            template="plotly_white",
            font=report_font,
            legend={"font": report_font, "bgcolor": CHART_BG},
            hoverlabel={
                "bgcolor": CHART_BG, "bordercolor": UI_COLORS["muted"],
                "font": {**report_font, "size": 14},
            },
            modebar={"color": UI_COLORS["muted"], "activecolor": UI_COLORS["blue"], "bgcolor": CHART_BG},
        )
        fig.update_xaxes(tickfont=report_font, title_font=report_font, automargin=True)
        fig.update_yaxes(tickfont=report_font, title_font=report_font, automargin=True)
        fig.update_annotations(font=report_font)
    st.plotly_chart(
        fig, width="stretch", key=key, theme=None if UI_LIGHT else "streamlit",
        config={"displaylogo":False,"scrollZoom":True,"responsive":True,
                "modeBarButtonsToRemove":["lasso2d","select2d"]},
    )


def _refresh_data_health(symbol: str, *, check_all_futures: bool = False) -> dict:
    """Refresh underlying + futures data and recompute analysis without trading."""
    checked_at = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh")
    report = {"checked_at": checked_at.isoformat(), "symbol": symbol, "spot": {}, "futures": {}, "errors": []}
    try:
        spot_frame = refresh_history_incremental(symbol)
        spot_result = analyze_symbol(symbol, spot_frame)
        spot_info = data_module.cache_diagnostics(spot_frame)
        report["spot"] = {
            "status":"OK", "latest":pd.Timestamp(spot_frame.iloc[-1]["time"]).isoformat(),
            "price":float(spot_frame.iloc[-1]["close"]), "rows":len(spot_frame),
            "quality":spot_info.get("data_quality"), "action":spot_result.get("system_action"),
            "score":spot_result.get("consensus_score"),
        }
    except Exception as exc:
        report["spot"] = {"status":"ERROR", "error":f"{type(exc).__name__}: {exc}"}
        report["errors"].append(f"Cơ sở {symbol}: {exc}")
    try:
        contracts, contract_meta = load_futures_contracts()
        targets = contracts if check_all_futures else contracts[:1]
        contract_reports = []
        for contract in targets:
            contract_symbol = contract["symbol"]
            try:
                frames_check, meta_check = load_futures_bundle(
                    RAW_DIR / "futures", refresh=True, symbol=contract_symbol
                )
                analysis_check = analyze_vn30f1m(frames_check, symbol=contract_symbol)
                item = {
                    "symbol":contract_symbol,"label":contract["label"],"status":analysis_check.get("status"),
                    "latest":{tf:meta.get("latest") for tf,meta in meta_check.items()},
                    "rows":{tf:meta.get("rows") for tf,meta in meta_check.items()},
                    "price":analysis_check.get("price"),"action":analysis_check.get("action"),
                    "score":analysis_check.get("score"),
                    "sources":{tf:meta.get("source_label") for tf,meta in meta_check.items()},
                }
                contract_reports.append(item)
                if item["status"] != "OK": report["errors"].append(f"{contract_symbol}: không đủ dữ liệu phân tích.")
            except BaseException as contract_exc:
                contract_reports.append({"symbol":contract_symbol,"label":contract["label"],"status":"ERROR","error":str(contract_exc)})
                report["errors"].append(f"{contract_symbol}: {contract_exc}")
        first = contract_reports[0] if contract_reports else {}
        report["futures"] = {
            **first, "status":"OK" if contract_reports and all(item.get("status") == "OK" for item in contract_reports) else "WARNING",
            "contracts":contract_reports,"checked_contracts":len(contract_reports),
            "available_contracts":len(contracts),"list_source":contract_meta.get("source_label"),
        }
    except Exception as exc:
        report["futures"] = {"status":"ERROR", "error":f"{type(exc).__name__}: {exc}"}
        report["errors"].append(f"Phái sinh: {exc}")
    equity_bot_check, futures_bot_check = bot_status(ROOT), futures_bot_status(ROOT)
    report["bots"] = {
        "equity_running":bool(equity_bot_check.get("running")),
        "equity_heartbeat_age":equity_bot_check.get("heartbeat_age_seconds"),
        "futures_running":bool(futures_bot_check.get("running")),
        "futures_heartbeat_age":futures_bot_check.get("heartbeat_age_seconds"),
    }
    return report


@st.cache_data(show_spinner=False, ttl=300)
def _auto_data_health(symbol: str, five_minute_bucket: int) -> dict:
    return _refresh_data_health(symbol, check_all_futures=False)


@st.fragment(run_every=300)
def auto_data_health_panel(symbol: str) -> None:
    job = dashboard_reads().poll(("health", symbol), lambda: _refresh_data_health(symbol), ttl=300)
    report = job["value"]
    if report is None:
        st.caption("◌ Đang kiểm tra dữ liệu nền; dashboard sử dụng dữ liệu đã lưu.")
        if job["error"]:
            st.warning("Nguồn dữ liệu chưa phản hồi: " + job["error"])
        return
    if job["running"]:
        st.caption("◌ Đang cập nhật nền; kết quả dưới đây là lần kiểm tra hoàn tất gần nhất.")
    spot, futures = report.get("spot", {}), report.get("futures", {})
    if report.get("errors"):
        st.warning("Tự kiểm tra dữ liệu: " + " • ".join(report["errors"][:2]))
    else:
        checked = pd.Timestamp(report["checked_at"]).strftime("%H:%M:%S")
        st.caption(
            f"● AUTO DATA {checked} · {symbol} {fmt(spot.get('price'))} · "
            f"VN30F1M {fmt(futures.get('price'),1)} · phân tích đã cập nhật"
        )
    signature = (spot.get("latest"), json.dumps(futures.get("latest", {}), sort_keys=True))
    previous = st.session_state.get("auto_data_signature")
    st.session_state.auto_data_signature = signature
    if previous is not None and previous != signature:
        st.session_state.auto_data_changed = True


@st.fragment(run_every=10)
def bot_risk_alert_panel() -> None:
    """Poll background BOT alerts without rerunning the full dashboard."""
    alert_path = STATE_DIR / "bot_alerts.json"
    try:
        alerts = json.loads(alert_path.read_text(encoding="utf-8"))
        if not isinstance(alerts, list) or not alerts:
            return
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return
    latest_alert = alerts[-1]
    try:
        alert_time = pd.Timestamp(latest_alert.get("time")).tz_convert("Asia/Ho_Chi_Minh").strftime("%H:%M:%S")
    except (TypeError, ValueError):
        alert_time = "—"
    message = (
        f"⚠ BOT {latest_alert.get('scope','—')} · {latest_alert.get('symbol','—')} · {alert_time}\n\n"
        f"{latest_alert.get('reason','Lệnh đã bị khóa bởi quản trị rủi ro.')}"
    )
    recent_alert = is_recent_alert(latest_alert)
    if recent_alert:
        st.warning(message)
    else:
        st.caption("Có cảnh báo cũ trong lịch sử BOT; đây không phải trạng thái chặn lệnh hiện tại.")
    alert_id = latest_alert.get("id")
    if recent_alert and alert_id and st.session_state.get("last_audible_bot_alert") != alert_id:
        st.toast(f"BOT: {latest_alert.get('symbol','—')} — {latest_alert.get('reason','Cảnh báo rủi ro')}", icon="⚠️")
        sample_rate = 16_000
        duration = .48
        timeline = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        envelope = np.sin(np.pi * timeline / duration) ** 2
        gentle_tone = (.065 * envelope * (
            np.sin(2 * np.pi * 523.25 * timeline) + .42 * np.sin(2 * np.pi * 659.25 * timeline)
        )).astype(np.float32)
        st.audio(gentle_tone, sample_rate=sample_rate, autoplay=True, width="stretch")
        st.session_state.last_audible_bot_alert = alert_id
    with st.expander("Lịch sử cảnh báo BOT", expanded=False):
        alert_rows = pd.DataFrame(alerts[-10:][::-1])
        if not alert_rows.empty:
            desk_dataframe(themed_dataframe(alert_rows[[c for c in ["time","scope","symbol","code","reason"] if c in alert_rows]]),
                         hide_index=True, width="stretch")


def themed_dataframe(data):
    """The desk grid owns header, body and input colors in both appearances."""
    return data if isinstance(data, pd.DataFrame) else data.data


def pct_change(a, b):
    if b in (None, 0) or pd.isna(b):
        return None
    return (a / b - 1) * 100


def signal_badge(signal: str):
    color, label = SIGNAL_STYLE.get(signal, (UI_COLORS['muted'], signal or "—"))
    return (
        f'<span style="display:inline-block;padding:5px 10px;'
        f'border-radius:999px;background:{color}22;color:{color};'
        f'border:1px solid {color}55;font-weight:700;font-size:12px">'
        f'{label}</span>'
    )


def signal_explanation(signal: str) -> str:
    return SIGNAL_HELP.get(signal, "Chưa đủ dữ liệu để xác định hoặc giải thích signal.")


def wyckoff_explanation(phase: str, event: str, bias: str) -> str:
    return (
        f"**Event `{event}`:** {WYCKOFF_EVENT_HELP.get(event, 'Chưa có mô tả.')}  \n"
        f"**Phase `{phase}`:** {WYCKOFF_PHASE_HELP.get(phase, 'Chưa có mô tả.')}  \n"
        f"**Bias `{bias}`:** {WYCKOFF_BIAS_HELP.get(bias, 'Chưa có mô tả.')}"
    )


def metric_explanation(kind: str, value, frame: dict) -> str:
    if LANG != "vi":
        generic = {
            "en": "System interpretation for {kind}: {value}. Use it together with score, trend, momentum, volume, and higher timeframes.",
            "zh": "系统对{kind}的解释：{value}。请结合评分、趋势、动量、成交量和更高周期使用。",
            "ru": "Интерпретация системы — {kind}: {value}. Используйте вместе с оценкой, трендом, импульсом, объёмом и старшими таймфреймами.",
            "de": "Systeminterpretation für {kind}: {value}. Zusammen mit Score, Trend, Momentum, Volumen und höheren Zeitrahmen verwenden.",
        }
        return generic[LANG].format(kind=kind, value="—" if value is None else value)
    if kind == "Signal":
        return SIGNAL_HELP.get(str(value), "Tín hiệu chưa có định nghĩa.")
    if kind == "Event":
        return WYCKOFF_EVENT_HELP.get(str(value), "Sự kiện Wyckoff chưa có định nghĩa.")
    if kind == "Phase":
        return WYCKOFF_PHASE_HELP.get(str(value), "Giai đoạn Wyckoff chưa có định nghĩa.")
    if kind == "Bias":
        return WYCKOFF_BIAS_HELP.get(str(value), "Thiên hướng chưa có định nghĩa.")
    if kind == "MA":
        return MA_REGIME_HELP.get(str(value), "Trạng thái MA chưa có định nghĩa.")
    if kind == "Điểm":
        components = frame.get("component_scores", {})
        detail = " · ".join(f"{name.upper()} {float(score):+.1f}" for name, score in components.items())
        return f"Điểm riêng của khung, giới hạn −100 đến +100. Thành phần: {detail or 'chưa đủ dữ liệu'}."
    if kind == "RSI14":
        if value is None or pd.isna(value):
            return "Chưa đủ 14 nến để tính RSI."
        state = "quá mua" if value >= 70 else "quá bán" if value <= 30 else "tích cực" if value >= 50 else "yếu"
        return f"RSI14 = {float(value):.1f}: trạng thái {state}. RSI đo động lượng giá trên thang 0–100."
    if kind == "RVOL":
        if value is None or pd.isna(value):
            return "Chưa đủ dữ liệu khối lượng để tính RVOL."
        state = "khối lượng xác nhận mạnh" if value >= 1.2 else "khối lượng bình thường hoặc chưa xác nhận"
        return f"RVOL = {float(value):.2f}x: {state}. RVOL so sánh khối lượng hiện tại với trung bình 20 nến."
    return str(value)


def interactive_timeframe_table(result: dict) -> None:
    specs = (
        (tr(LANG,"timeframe"), None), ("Signal", "signal"), (tr(LANG,"score"), "signal_score"),
        (tr(LANG,"event"), "wyckoff_event"), (tr(LANG,"phase"), "wyckoff_phase"),
        (tr(LANG,"bias"), "wyckoff_bias"), ("MA", "ma_regime"),
        ("RSI14", "rsi14"), ("RVOL", "rvol"),
    )
    widths = [.52, .82, .62, .78, 1.05, .8, 1.12, .65, .65]
    headers = st.columns(widths)
    for column, (label, _) in zip(headers, specs):
        column.markdown(f"**{label}**")
    for timeframe in TF_ORDER:
        frame = result["timeframes"].get(timeframe, {})
        columns = st.columns(widths)
        columns[0].markdown(f"**{timeframe}**")
        for column, (label, key) in zip(columns[1:], specs[1:]):
            value = frame.get(key)
            if key == "signal_score" and value is not None:
                shown = f"{float(value):+.1f}"
            elif label == "RSI14" and value is not None:
                shown = f"{float(value):.1f}"
            elif label == "RVOL" and value is not None:
                shown = f"{float(value):.2f}x"
            else:
                shown = "—" if value is None else str(value)
            with column.popover(shown, width="stretch"):
                st.markdown(f"**{timeframe} · {label}: `{shown}`**")
                st.write(metric_explanation(label, value, frame))
                st.caption(tr(LANG, "each_candle", period=period(LANG,timeframe), confidence=frame.get('confidence', 0)))


def save_api_key(key: str) -> None:
    key = key.strip()
    if not key.startswith("vnstock_") or len(key) <= 20:
        raise ValueError("API key Vnstock không hợp lệ.")
    existing = []
    if ENV_FILE.exists():
        existing = ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
    kept = [line for line in existing if not line.strip().startswith("VNSTOCK_API_KEY=")]
    kept.append(f"VNSTOCK_API_KEY={key}")
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
    os.environ["VNSTOCK_API_KEY"] = key


def save_openai_api_key(key: str) -> None:
    key = key.strip()
    if not key.startswith("sk-") or len(key) < 20:
        raise ValueError("OPENAI_API_KEY không hợp lệ.")
    existing = ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines() if ENV_FILE.exists() else []
    kept = [line for line in existing if not line.strip().startswith("OPENAI_API_KEY=")]
    kept.append(f"OPENAI_API_KEY={key}")
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
    os.environ["OPENAI_API_KEY"] = key


def render_data_download_panel(lang: str, key_prefix: str) -> None:
    """Render the same resumable downloader in sidebar, main tab, or recovery UI."""
    st.caption(f"System: {ROOT} · Data: {MARKET_DIR}")
    st.caption(tr(lang, "download_note"))
    data_job = DataJobs()
    download_scope = st.selectbox(
        tr(lang, "download_scope"),
        ["VN30", "VN100", "HOSE", "HNX", "UPCOM", "ALL", "FAVORITES"],
        key=f"{key_prefix}_scope",
    )
    download_mode = st.radio(
        tr(lang, "download_method"), ["missing", "update", "initial"], horizontal=True,
        format_func=lambda value: {
            "missing": tr(lang, "download_missing"),
            "update": tr(lang, "download_update"),
            "initial": tr(lang, "download_initial"),
        }[value],
        key=f"{key_prefix}_mode",
    )
    download_components = st.multiselect(
        tr(lang, "download_components"), ["prices", "news", "valuation", "futures"],
        default=["prices", "news", "valuation", "futures"],
        format_func=lambda value: {
            "prices": "OHLCV", "news": tr(lang, "download_news"),
            "valuation": tr(lang, "download_valuation"), "futures": tr(lang, "download_futures"),
        }[value],
        key=f"{key_prefix}_components",
    )
    load_a, load_b, load_c = st.columns(3)
    if load_a.button("▶", help=tr(lang, "download_start"), width="stretch", key=f"{key_prefix}_start"):
        try:
            data_job.start({"scope": download_scope, "mode": download_mode, "components": download_components})
            st.session_state.data_action_message = tr(lang, "download_started")
            st.rerun()
        except (OSError, ValueError, RuntimeError) as exc:
            st.error(str(exc))
    if load_b.button("Ⅱ", help=tr(lang, "download_pause"), width="stretch", key=f"{key_prefix}_pause"):
        data_job.pause()
        st.session_state.data_action_message = tr(lang, "download_paused")
        st.rerun()
    if load_c.button("↻", help=tr(lang, "download_resume"), width="stretch", key=f"{key_prefix}_resume"):
        try:
            data_job.start(resume=True)
            st.session_state.data_action_message = tr(lang, "download_resumed")
            st.rerun()
        except (OSError, ValueError, RuntimeError) as exc:
            st.error(str(exc))
    if st.session_state.get("data_action_message"):
        st.caption(st.session_state.data_action_message)
    download_status = data_job.status()
    if download_status:
        total, completed = len(download_status.get("tasks", [])), len(download_status.get("done", []))
        st.progress(
            completed / total if total else 0,
            text=f"{download_status.get('status', '—')} · {completed}/{total} · "
                 f"{download_status.get('current') or download_status.get('message', '')}",
        )
        if download_status.get("errors"):
            st.warning(f"{len(download_status['errors'])} {tr(lang, 'download_failed')}")
    with st.popover(tr(lang, "download_init"), width="stretch"):
        new_market_dir = st.text_input(
            tr(lang, "download_path"), value=str(MARKET_DIR), key=f"{key_prefix}_market_dir"
        )
        st.caption(tr(lang, "download_path_note"))
        if st.button(tr(lang, "download_init_action"), key=f"{key_prefix}_initialize"):
            try:
                st.success(configure_next_data_directory(new_market_dir))
            except (OSError, ValueError) as exc:
                st.error(str(exc))


@st.cache_data(show_spinner=False, ttl=900)
def resampled(df, tf):
    # Changed cache identity: older entries used future calendar-end timestamps.
    actual_candles = resample_ohlcv(df, tf)
    return add_indicators(actual_candles)


def tradingview_chart(symbol: str, timeframe: str, exchange: str = "HOSE", height: int = 760) -> None:
    """Nhúng widget chính thức; TradingView quản lý dữ liệu và renderer nến."""
    interval = {
        "1D": "D",
        "1W": "W",
        "1M": "M",
        "1Y": "12M",
    }.get(timeframe, "D")
    tv_exchange = "HOSE" if exchange in {"HOSE", "VN30", "VN100"} else exchange
    tv_symbol = f"{tv_exchange}:{symbol.upper()}"
    params = {
        "symbol": tv_symbol,
        "interval": interval,
        "timezone": "Asia/Ho_Chi_Minh",
        "theme": CHART_THEME,
        "style": "1",
        "locale": "vi_VN",
        "hidesidetoolbar": "0",
        "symboledit": "0",
        "saveimage": "1",
        "withdateranges": "1",
        "hideideas": "1",
    }
    widget_url = "https://s.tradingview.com/widgetembed/?" + urlencode(params)
    st.iframe(widget_url, height=height)
    symbol_path = tv_symbol.replace(":", "-")
    st.markdown(
        f'<a href="https://www.tradingview.com/symbols/{symbol_path}/" target="_blank">'
        f'{tv_symbol} chart</a> by TradingView',
        unsafe_allow_html=True,
    )


def lightweight_system_chart(
    x_all: pd.DataFrame,
    tf: str,
    show_ma20: bool = True,
    show_ma50: bool = True,
    show_ma100: bool = True,
    show_ma200: bool = True,
    show_wyckoff_structure: bool = True,
    height: int = 720,
) -> None:
    """TradingView Lightweight Charts với dữ liệu và tín hiệu nội bộ."""
    x = chart_window(x_all, tf).copy()
    x["date"] = pd.to_datetime(x["time"]).dt.strftime("%Y-%m-%d")
    candles = [
        {
            "time": row.date,
            "open": round(float(row.open), 4),
            "high": round(float(row.high), 4),
            "low": round(float(row.low), 4),
            "close": round(float(row.close), 4),
        }
        for row in x.itertuples()
    ]
    volumes = [
        {
            "time": row.date,
            "value": float(row.volume),
            "color": "rgba(38,166,154,.55)" if row.close >= row.open else "rgba(239,83,80,.55)",
        }
        for row in x.itertuples()
    ]
    ma_options = [(20, show_ma20, UI_COLORS["blue"]), (50, show_ma50, UI_COLORS["orange"]),
                  (100, show_ma100, UI_COLORS["purple"]), (200, show_ma200, UI_COLORS["amber"])]
    ma_payload = []
    for length, enabled, color in ma_options:
        column = f"ma{length}"
        if enabled and column in x.columns:
            points = [
                {"time": row.date, "value": round(float(getattr(row, column)), 4)}
                for row in x.itertuples()
                if pd.notna(getattr(row, column))
            ]
            if points:
                ma_payload.append({"name": f"MA{length}", "color": color, "data": points})

    event_source = x_all.tail(max(400, len(x) + 30))
    events = wyckoff_events(event_source)
    markers = []
    if not events.empty:
        visible_dates = set(x["date"])
        # Chỉ giữ các sự kiện mới nhất trong cửa sổ. Nhãn lịch sử dày đặc làm
        # che nến, đặc biệt trên màn hình hẹp.
        visible_events = events[events["time"] >= x["time"].min()].tail(12)
        for row in visible_events.itertuples():
            date_text = pd.Timestamp(row.time).strftime("%Y-%m-%d")
            if date_text not in visible_dates:
                continue
            bullish = row.event in {"SPRING", "SOS", "LPS"}
            markers.append({
                "time": date_text,
                "position": "belowBar" if bullish else "aboveBar",
                "color": UI_COLORS['green'] if bullish else UI_COLORS['red'],
                "shape": "arrowUp" if bullish else "arrowDown",
                "text": row.event,
            })
    markers.sort(key=lambda item: item["time"])

    wy = analyze_wyckoff(x_all)
    structure_lines = []
    if show_wyckoff_structure:
        base_levels = [
            ("range_high", "Creek / Range High", "#ab47bc", 2),
            ("range_low", "Ice / Range Low", "#7e57c2", 2),
            ("resistance", "Resistance", UI_COLORS['red'], 0),
            ("support", "Support", "#26a69a", 0),
        ]
        for key, title, color, style in base_levels:
            value = wy.get(key)
            if value is not None:
                structure_lines.append({"price": round(float(value), 4), "title": title, "color": color, "style": style})
        if wy.get("range_high") is not None and wy.get("range_low") is not None:
            equilibrium = (float(wy["range_high"]) + float(wy["range_low"])) / 2
            structure_lines.append({"price": round(equilibrium, 4), "title": "EQ 50%", "color": UI_COLORS['muted'], "style": 1})

        # Event đã có marker ngay trên nến. Không tạo thêm price-line cho từng
        # loại event vì các nhãn bên phải sẽ chồng lên MA và hỗ trợ/kháng cự.

        # Gộp các mức gần như trùng nhau; ưu tiên Support/Resistance trước
        # Range và EQ để trục giá chỉ hiển thị thông tin quan trọng nhất.
        deduped = []
        tolerance = max(float(x["close"].iloc[-1]) * 0.0025, 0.01)
        priority = {"Support": 0, "Resistance": 0, "Creek / Range High": 1, "Ice / Range Low": 1, "EQ 50%": 2}
        for line in sorted(structure_lines, key=lambda item: priority.get(item["title"], 9)):
            if any(abs(line["price"] - kept["price"]) <= tolerance for kept in deduped):
                continue
            deduped.append(line)
        structure_lines = deduped[:5]

    fib = fibonacci_analysis(x, min(120, len(x)))
    fibonacci_lines = []
    if fib.get("status") == "OK":
        fib_line_colors = {"0.382":UI_COLORS['blue'], "0.500":UI_COLORS['amber'], "0.618":UI_COLORS['purple']}
        for ratio in ("0.382", "0.500", "0.618"):
            level = fib.get("levels", {}).get(ratio)
            if level is not None:
                fibonacci_lines.append({"price":float(level), "title":f"Fib {ratio}", "color":fib_line_colors[ratio], "style":1})
        visible_span = max(float(x["high"].max()) - float(x["low"].min()), .01)
        current_price = float(x.iloc[-1]["close"])
        for ratio, color in (("1.272","#ff8a65"), ("1.618","#ec4899")):
            level = fib.get("extensions", {}).get(ratio)
            if level is not None and abs(float(level) - current_price) <= visible_span * 1.35:
                fibonacci_lines.append({"price":float(level), "title":f"Ext {ratio}", "color":color, "style":3})
        tolerance = max(current_price * .0015, .01)
        fibonacci_lines = [line for line in fibonacci_lines if not any(
            abs(line["price"] - kept["price"]) <= tolerance for kept in structure_lines
        )]

    payload = json.dumps(
        {
            "candles": candles,
            "volumes": volumes,
            "mas": ma_payload,
            "markers": markers,
            "structureLines": structure_lines,
            "fibonacciLines": fibonacci_lines,
        },
        ensure_ascii=False,
    )
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
html,body,#chart{{margin:0;width:100%;height:100%;background:{CHART_BG};overflow:hidden}}
body{{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif}}
#legend{{position:absolute;z-index:5;left:12px;top:10px;display:flex;gap:6px;max-width:calc(100% - 132px);
overflow:hidden;white-space:nowrap;pointer-events:none}}
.legend-chip{{color:{CHART_TEXT};font-size:11px;font-weight:650;background:{CHART_CONTROL_BG}e8;
padding:4px 7px;border:1px solid {CHART_BORDER};border-radius:999px;backdrop-filter:blur(18px)}}
#hint{{position:absolute;z-index:5;left:12px;bottom:8px;color:{CHART_TEXT};font-size:11px;
background:{CHART_CONTROL_BG}e8;padding:5px 8px;border:1px solid {CHART_BORDER};border-radius:8px;pointer-events:none}}
#fit{{position:absolute;z-index:6;right:58px;top:8px;background:{CHART_CONTROL_BG}e8;color:{CHART_TEXT};
border:1px solid {CHART_BORDER};border-radius:9px;padding:6px 10px;cursor:pointer;font-weight:650;backdrop-filter:blur(18px)}}
@media(max-width:520px){{#hint{{font-size:10px;max-width:calc(100% - 30px)}}#fit{{right:50px}}
#legend{{max-width:118px}}.legend-chip:nth-child(n+2){{display:none}}}}
</style></head><body><div id="chart"></div><div id="legend"></div><button id="fit">{tr(LANG, 'fit_chart')}</button>
<div id="hint">{tr(LANG, 'chart_hint')}</div>
<script src="https://unpkg.com/lightweight-charts@5.0.8/dist/lightweight-charts.standalone.production.js"></script>
<script>
const data={payload}; const el=document.getElementById('chart');
const chart=LightweightCharts.createChart(el,{{width:el.clientWidth,height:el.clientHeight,
 layout:{{background:{{type:'solid',color:'{CHART_BG}'}},textColor:'{CHART_TEXT}'}},
 grid:{{vertLines:{{color:'{CHART_GRID}'}},horzLines:{{color:'{CHART_GRID}'}}}},
 crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},
 rightPriceScale:{{borderColor:'{CHART_BORDER}',minimumWidth:112,scaleMargins:{{top:.08,bottom:.08}},entireTextOnly:true}},timeScale:{{borderColor:'{CHART_BORDER}',timeVisible:false,
 rightOffset:4,barSpacing:8,minBarSpacing:2}},
 handleScroll:{{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:true}},
 handleScale:{{axisPressedMouseMove:true,mouseWheel:true,pinch:true}}
}});
const candle=chart.addSeries(LightweightCharts.CandlestickSeries,{{upColor:'{UI_COLORS['green']}',downColor:'{UI_COLORS['red']}',
 borderVisible:false,wickUpColor:'{UI_COLORS['green']}',wickDownColor:'{UI_COLORS['red']}'}}); candle.setData(data.candles);
const volume=chart.addSeries(LightweightCharts.HistogramSeries,{{priceFormat:{{type:'volume'}},priceScaleId:'volume'}});
volume.priceScale().applyOptions({{scaleMargins:{{top:.82,bottom:0}}}}); volume.setData(data.volumes);
const legend=document.getElementById('legend');
for(const ma of data.mas){{const s=chart.addSeries(LightweightCharts.LineSeries,{{color:ma.color,lineWidth:2,
 priceLineVisible:false,lastValueVisible:false,title:ma.name}});s.setData(ma.data);
 const last=ma.data.at(-1);if(last){{const chip=document.createElement('span');chip.className='legend-chip';
 chip.style.borderColor=ma.color+'88';chip.innerHTML=`<i style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${{ma.color}};margin-right:5px"></i>${{ma.name}} ${{last.value.toFixed(2)}}`;legend.appendChild(chip);}}}}
const visibleMarkers=el.clientWidth<520?data.markers.slice(-6):data.markers;
if(visibleMarkers.length) LightweightCharts.createSeriesMarkers(candle,visibleMarkers);
for(const line of data.structureLines){{candle.createPriceLine({{price:line.price,color:line.color,
 lineWidth:1,lineStyle:line.style,axisLabelVisible:true,title:line.title}});}}
for(const line of data.fibonacciLines){{candle.createPriceLine({{price:line.price,color:line.color,
 lineWidth:1,lineStyle:line.style,axisLabelVisible:true,title:line.title}});}}
const focusRecent=()=>{{const n=data.candles.length;const visible=Math.min(n,Math.max(45,Math.floor(el.clientWidth/7)));
 chart.timeScale().setVisibleLogicalRange({{from:n-visible-2,to:n+3}});}};
focusRecent();
document.getElementById('fit').onclick=()=>chart.timeScale().fitContent();
el.ondblclick=()=>chart.timeScale().fitContent();
let previousWidth=el.clientWidth;new ResizeObserver(e=>{{const width=e[0].contentRect.width;
 chart.applyOptions({{width,height:e[0].contentRect.height}});if(Math.abs(width-previousWidth)>80)focusRecent();previousWidth=width;}}).observe(el);
</script></body></html>"""
    src = "data:text/html;base64," + base64.b64encode(html.encode("utf-8")).decode("ascii")
    st.iframe(src, height=height)
    st.caption(tr(LANG, "chart_caption"))


def lightweight_futures_execution_chart(
    frame: pd.DataFrame, analysis: dict, account: dict, plan: dict, height: int = 650,
    symbol: str = "VN30F1M",
) -> None:
    """Native TradingView interaction for a futures contract with PAPER execution levels."""
    x = frame.copy().dropna(subset=["time","open","high","low","close"])
    if x.empty:
        st.error(f"Không có dữ liệu để dựng biểu đồ TradingView {symbol}.")
        return
    def unix_time(value):
        return int(pd.Timestamp(value).timestamp())
    candles = [{"time":unix_time(r.time), "open":float(r.open), "high":float(r.high),
                "low":float(r.low), "close":float(r.close)} for r in x.itertuples()]
    volumes = [{"time":unix_time(r.time), "value":float(r.volume),
                "color":"rgba(0,200,83,.48)" if r.close >= r.open else "rgba(239,83,80,.48)"}
               for r in x.itertuples()]
    mas = []
    for column, color in (("ma20",UI_COLORS['amber']),("ma50",UI_COLORS['blue'])):
        if column in x:
            values = [{"time":unix_time(r.time), "value":float(getattr(r,column))}
                      for r in x.itertuples() if pd.notna(getattr(r,column))]
            if values: mas.append({"name":column.upper(), "color":color, "data":values})
    active = account.get("side") in {"LONG","SHORT"} and int(account.get("quantity",0)) > 0
    side = account["side"] if active else plan.get("side", "PLAN")
    entry = account.get("entry_price") if active else plan.get("trigger")
    stop = account.get("stop_loss") if active else plan.get("stop_loss")
    tp1 = account.get("target") if active else plan.get("target_1")
    tp2 = account.get("target_2") if active else plan.get("target_2")
    mark = float(x.iloc[-1]["close"])
    pnl_vnd = float(account.get("unrealized_pnl_vnd",0)) if active else 0.0
    direction = 1 if side == "LONG" else -1 if side == "SHORT" else 0
    pnl_points = direction * (mark - float(entry)) if active and entry is not None else None
    lines = [
        {"price":mark,"title":f"MARK {mark:,.1f}","color":"#ffffff" if not UI_LIGHT else "#334155","style":0,"width":1},
        {"price":analysis.get("support"),"title":"SUPPORT","color":UI_COLORS['green'],"style":2,"width":1},
        {"price":analysis.get("resistance"),"title":"RESISTANCE","color":UI_COLORS['red'],"style":2,"width":1},
        {"price":entry,"title":f"{'ENTRY' if active else 'PLAN ENTRY'} {fmt(entry,1)}","color":"#26c6da","style":0,"width":2},
        {"price":stop,"title":f"STOP LOSS {fmt(stop,1)}","color":UI_COLORS['red'],"style":2,"width":2},
        {"price":tp1,"title":f"TAKE PROFIT 1 {fmt(tp1,1)}","color":UI_COLORS['green'],"style":2,"width":2},
        {"price":tp2,"title":f"TAKE PROFIT 2 {fmt(tp2,1)}","color":UI_COLORS['green'],"style":3,"width":2},
    ]
    zones = []
    if entry is not None:
        entry_value = float(entry)
        entry_low = plan.get("entry_low") if not active else None
        entry_high = plan.get("entry_high") if not active else None
        reference_span = max(
            [abs(float(level) - entry_value) for level in (stop, tp1, tp2) if level is not None] or [1.0]
        )
        entry_half_band = max(.1, reference_span * .035)
        zones.append({
            "low":float(entry_low) if entry_low is not None else entry_value - entry_half_band,
            "high":float(entry_high) if entry_high is not None else entry_value + entry_half_band,
            "fill":"rgba(38,198,218,.16)","border":"rgba(38,198,218,.72)","label":"ENTRY",
        })
        if stop is not None:
            zones.append({"low":min(entry_value,float(stop)),"high":max(entry_value,float(stop)),
                          "fill":"rgba(255,23,68,.11)","border":"rgba(255,23,68,.45)","label":"STOP LOSS"})
        if tp1 is not None:
            zones.append({"low":min(entry_value,float(tp1)),"high":max(entry_value,float(tp1)),
                          "fill":"rgba(0,230,118,.09)","border":"rgba(0,230,118,.38)","label":"TP1"})
        if tp1 is not None and tp2 is not None:
            zones.append({"low":min(float(tp1),float(tp2)),"high":max(float(tp1),float(tp2)),
                          "fill":"rgba(197,255,0,.075)","border":"rgba(197,255,0,.34)","label":"TP2"})
    fib = analysis.get("fibonacci", {})
    for ratio, color in (("0.382",UI_COLORS['blue']),("0.500",UI_COLORS['amber']),("0.618",UI_COLORS['purple'])):
        level = fib.get("levels",{}).get(ratio)
        if level is not None: lines.append({"price":level,"title":f"FIB {ratio}","color":color,"style":1,"width":1})
    lines = [{**line,"price":float(line["price"])} for line in lines if line.get("price") is not None]
    events = futures_wyckoff_events(x, max_bars=len(x))
    markers = []
    if not events.empty:
        for row in events.tail(12).itertuples():
            bullish = row.event in {"SPRING","SOS","LPS"}
            markers.append({"time":unix_time(row.time), "position":"belowBar" if bullish else "aboveBar",
                            "color":UI_COLORS['green'] if bullish else UI_COLORS['red'],
                            "shape":"arrowUp" if bullish else "arrowDown", "text":row.event})
    payload = json.dumps({"candles":candles,"volumes":volumes,"mas":mas,"lines":lines,"markers":markers,"zones":zones}, ensure_ascii=False)
    position_text = f"{side} · {int(account.get('quantity',0))} HĐ" if active else "KẾ HOẠCH CHỜ KÍCH HOẠT"
    money_text = (f"P&L {pnl_points:+.1f} điểm · {pnl_vnd:+,.0f} ₫" if pnl_points is not None
                  else f"Equity PAPER {float(account.get('equity_vnd',0)):,.0f} ₫")
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body,#fchart{{margin:0;width:100%;height:100%;background:{CHART_BG};overflow:hidden}}
body{{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",sans-serif}}
#desk{{position:absolute;z-index:8;left:12px;top:10px;display:flex;gap:7px;pointer-events:none;flex-wrap:wrap;max-width:75%}}
.trade-zones{{position:absolute;z-index:6;inset:0 128px 0 0;pointer-events:none;overflow:hidden}}
.trade-zone{{position:absolute;left:7%;right:0;border-top:1px solid;border-bottom:1px solid;box-sizing:border-box}}
.trade-zone-label{{position:absolute;left:7px;top:50%;transform:translateY(-50%);padding:2px 6px;border-radius:5px;font-size:9px;font-weight:800;letter-spacing:.06em;color:{CHART_TEXT};background:{CHART_CONTROL_BG}cc;white-space:nowrap}}
.chip{{background:{CHART_CONTROL_BG}ee;border:1px solid {CHART_BORDER};border-radius:9px;padding:6px 9px;color:{CHART_TEXT};font-size:11px;font-weight:750;backdrop-filter:blur(16px)}}
#hintf{{position:absolute;z-index:8;left:12px;bottom:8px;background:{CHART_CONTROL_BG}ee;border:1px solid {CHART_BORDER};border-radius:8px;padding:5px 8px;color:{CHART_TEXT};font-size:11px;pointer-events:none}}
#fitf{{position:absolute;z-index:9;right:128px;top:8px;border:1px solid {CHART_BORDER};border-radius:8px;background:{CHART_CONTROL_BG};color:{CHART_TEXT};padding:6px 9px;cursor:pointer}}
</style></head><body><div id="fchart"></div><div id="trade-zones" class="trade-zones"></div><div id="desk"><span class="chip">{symbol} · {position_text}</span><span class="chip" style="color:{UI_COLORS['green'] if pnl_vnd >= 0 else UI_COLORS['red']}">{money_text}</span><span class="chip">Cash {float(account.get('balance_vnd',0)):,.0f} ₫ · Equity {float(account.get('equity_vnd',0)):,.0f} ₫</span></div><button id="fitf">AUTO SCALE</button><div id="hintf">Lăn chuột: zoom · Kéo biểu đồ: di chuyển · Kéo trục giá phải: co giãn · Nhấp đúp: đặt lại</div>
<script src="https://unpkg.com/lightweight-charts@5.0.8/dist/lightweight-charts.standalone.production.js"></script><script>
const d={payload},el=document.getElementById('fchart');const chart=LightweightCharts.createChart(el,{{width:el.clientWidth,height:el.clientHeight,layout:{{background:{{type:'solid',color:'{CHART_BG}'}},textColor:'{CHART_TEXT}'}},grid:{{vertLines:{{color:'{CHART_GRID}'}},horzLines:{{color:'{CHART_GRID}'}}}},rightPriceScale:{{borderColor:'{CHART_BORDER}',minimumWidth:128,scaleMargins:{{top:.10,bottom:.14}}}},timeScale:{{borderColor:'{CHART_BORDER}',timeVisible:true,secondsVisible:false,rightOffset:6,barSpacing:8,minBarSpacing:2}},handleScroll:{{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:true}},handleScale:{{axisPressedMouseMove:true,mouseWheel:true,pinch:true}}}});
const c=chart.addSeries(LightweightCharts.CandlestickSeries,{{upColor:'{UI_COLORS['green']}',downColor:'{UI_COLORS['red']}',borderVisible:false,wickUpColor:'{UI_COLORS['green']}',wickDownColor:'{UI_COLORS['red']}'}});c.setData(d.candles);
const v=chart.addSeries(LightweightCharts.HistogramSeries,{{priceFormat:{{type:'volume'}},priceScaleId:'volume'}});v.priceScale().applyOptions({{scaleMargins:{{top:.84,bottom:0}}}});v.setData(d.volumes);
for(const ma of d.mas){{const s=chart.addSeries(LightweightCharts.LineSeries,{{color:ma.color,lineWidth:2,priceLineVisible:false,lastValueVisible:false,title:ma.name}});s.setData(ma.data);}}
if(d.markers.length)LightweightCharts.createSeriesMarkers(c,d.markers);
for(const line of d.lines)c.createPriceLine({{price:line.price,color:line.color,lineWidth:line.width,lineStyle:line.style,axisLabelVisible:true,title:line.title}});
const zoneLayer=document.getElementById('trade-zones');
const zoneNodes=d.zones.map(z=>{{const n=document.createElement('div');n.className='trade-zone';n.style.background=z.fill;n.style.borderColor=z.border;
 const label=document.createElement('span');label.className='trade-zone-label';label.textContent=z.label;label.style.border='1px solid '+z.border;
 n.appendChild(label);zoneLayer.appendChild(n);return {{z,n}};}});
const drawZones=()=>{{for(const item of zoneNodes){{const a=c.priceToCoordinate(item.z.high),b=c.priceToCoordinate(item.z.low);
 if(a===null||b===null){{item.n.style.display='none';continue;}}item.n.style.display='block';item.n.style.top=Math.min(a,b)+'px';item.n.style.height=Math.max(3,Math.abs(b-a))+'px';}}}};
let zoneSignature='';const syncZones=()=>{{const signature=zoneNodes.map(i=>[c.priceToCoordinate(i.z.high),c.priceToCoordinate(i.z.low)]).join('|');
 if(signature!==zoneSignature){{zoneSignature=signature;drawZones();}}requestAnimationFrame(syncZones);}};requestAnimationFrame(syncZones);
const fit=()=>{{chart.timeScale().fitContent();c.priceScale().applyOptions({{autoScale:true}});}};document.getElementById('fitf').onclick=fit;el.ondblclick=fit;new ResizeObserver(e=>chart.applyOptions({{width:e[0].contentRect.width,height:e[0].contentRect.height}})).observe(el);
</script></body></html>"""
    src = "data:text/html;base64," + base64.b64encode(html.encode("utf-8")).decode("ascii")
    st.iframe(src, height=height)


@st.fragment(run_every=5)
def live_futures_execution_chart(
    frame: pd.DataFrame, analysis: dict, account: dict, plan: dict, symbol: str,
) -> None:
    """Update only the TradingView chart fragment; never rerun the full page."""
    live_frame = frame.copy()
    live_account = account
    quote = load_futures_quote_cached(symbol)
    if quote.get("status") == "OK" and not live_frame.empty and "period_end" not in live_frame:
        age = quote.get("market_age_seconds")
        quote_time = pd.to_datetime(quote.get("market_time"), utc=True, errors="coerce")
        last_time = pd.Timestamp(live_frame.iloc[-1]["time"])
        last_time = last_time.tz_localize("Asia/Ho_Chi_Minh") if last_time.tzinfo is None else last_time
        bucket = {"15M":"15min", "1H":"h", "1D":"D"}.get(analysis.get("timeframe"), "15min")
        same_bar = pd.notna(quote_time) and quote_time.floor(bucket) == last_time.tz_convert("UTC").floor(bucket)
        if age is not None and float(age) <= 15 and same_bar:
            price = float(quote["price"])
            last_index = live_frame.index[-1]
            live_frame.loc[last_index,"close"] = price
            live_frame.loc[last_index,"high"] = max(float(live_frame.loc[last_index,"high"]), price)
            live_frame.loc[last_index,"low"] = min(float(live_frame.loc[last_index,"low"]), price)
            live_account = PaperFuturesBroker(
                STATE_DIR / f"paper_futures_{symbol.lower()}.json"
            ).snapshot(price)
    lightweight_futures_execution_chart(
        live_frame, analysis, live_account, plan, symbol=symbol,
    )


@st.cache_data(show_spinner=False, ttl=900)
def wyckoff_events(x):
    rows = []
    if len(x) < 10:
        return pd.DataFrame(columns=["time", "price", "event", "phase", "bias"])

    start = max(10, min(20, len(x) - 1))

    last_seen = {}
    for i in range(start, len(x)):
        r = analyze_wyckoff(x.iloc[: i + 1])
        ev = r.get("event", "NONE")

        if ev == "NONE":
            continue

        # Không lặp cùng một nhãn trên nhiều nến sát nhau gây che biểu đồ.
        if i - last_seen.get(ev, -100) < 5:
            continue
        last_seen[ev] = i

        bar = x.iloc[i]

        if ev in {"SPRING", "SOW"}:
            price = float(bar["low"])
        elif ev in {"UT", "SOS"}:
            price = float(bar["high"])
        else:
            price = float(bar["close"])

        rows.append(
            {
                "time": bar["time"],
                "price": price,
                "event": ev,
                "phase": r.get("phase", ""),
                "bias": r.get("bias", ""),
            }
        )

    return pd.DataFrame(rows)


def chart_window(x_all: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Cắt theo khoảng thời gian thay vì số bar để cache có gap không kéo méo trục X."""
    if x_all.empty:
        return x_all.copy()

    windows = {
        "1D": pd.DateOffset(months=9),
        "1W": pd.DateOffset(years=3),
        "1M": pd.DateOffset(years=5),
        "1Y": None,
    }
    end = pd.to_datetime(x_all["time"].max())
    offset = windows[tf]
    if offset is None:
        return x_all.copy()
    start = end - offset
    sliced = x_all[pd.to_datetime(x_all["time"]) >= start].copy()
    # Luôn giữ đủ dữ liệu tối thiểu để chart không rỗng với mã mới/ít thanh khoản.
    return sliced if len(sliced) >= 5 else x_all.tail(30).copy()


def make_chart(x_all, tf, show_ma20=True, show_ma50=True, show_ma100=True, show_ma200=True):
    x = chart_window(x_all, tf)
    wy = analyze_wyckoff(x_all)
    events = wyckoff_events(x_all)
    fib = fibonacci_analysis(x, min(120, len(x)))

    if not events.empty:
        tmin = pd.to_datetime(x["time"].min())
        events = events[pd.to_datetime(events["time"]) >= tmin]

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        row_heights=[0.68, 0.14, 0.18],
    )

    fig.add_trace(
        go.Candlestick(
            x=x["time"],
            open=x["open"],
            high=x["high"],
            low=x["low"],
            close=x["close"],
            name="Price",
            increasing_line_color="#26a69a",
            decreasing_line_color=UI_COLORS['red'],
            increasing_fillcolor="#26a69a",
            decreasing_fillcolor=UI_COLORS['red'],
        ),
        row=1,
        col=1,
    )

    ma_cfg = [
        (20, show_ma20, UI_COLORS["blue"]),
        (50, show_ma50, UI_COLORS["orange"]),
        (100, show_ma100, UI_COLORS["purple"]),
        (200, show_ma200, UI_COLORS["amber"]),
    ]

    for n, show, color in ma_cfg:
        col = f"ma{n}"
        if show and col in x.columns and x[col].notna().any():
            fig.add_trace(
                go.Scatter(
                    x=x["time"],
                    y=x[col],
                    mode="lines",
                    name=f"MA{n}",
                    line={"width": 1.4, "color": color},
                ),
                row=1,
                col=1,
            )

    # Wyckoff structure directly on price chart
    support = wy.get("support")
    resistance = wy.get("resistance")
    range_low = wy.get("range_low")
    range_high = wy.get("range_high")

    if support is not None:
        fig.add_hline(
            y=float(support),
            row=1, col=1,
            line_dash="dash",
            line_color="#26a69a",
            annotation_text=f"S {support:.2f}",
            annotation_position="bottom right",
        )
    if resistance is not None:
        fig.add_hline(
            y=float(resistance),
            row=1, col=1,
            line_dash="dash",
            line_color=UI_COLORS['red'],
            annotation_text=f"R {resistance:.2f}",
            annotation_position="top right",
        )
    if range_low is not None:
        fig.add_hline(
            y=float(range_low),
            row=1, col=1,
            line_dash="dot",
            line_color="#546e7a",
        )
    if range_high is not None:
        fig.add_hline(
            y=float(range_high),
            row=1, col=1,
            line_dash="dot",
            line_color="#546e7a",
        )

    # Trend-aware Fibonacci layer for the system analysis chart.
    if fib.get("status") == "OK":
        fib_colors = {
            "0.236":UI_COLORS['muted'], "0.382":UI_COLORS['blue'], "0.500":UI_COLORS['amber'],
            "0.618":UI_COLORS['purple'], "0.786":"#ec4899",
        }
        golden_low, golden_high = fib["golden_zone"]
        fig.add_hrect(
            y0=golden_low, y1=golden_high, fillcolor=UI_COLORS['purple'],
            opacity=.06, line_width=0, row=1, col=1,
        )
        for fib_ratio, fib_level in fib.get("levels", {}).items():
            if fib_ratio in fib_colors:
                fig.add_hline(
                    y=fib_level, line_dash="dot", line_color=fib_colors[fib_ratio],
                    line_width=1, annotation_text=f"Fib {fib_ratio} · {fib_level:,.2f}",
                    annotation_position="left", annotation_font={"size":9,"color":fib_colors[fib_ratio]},
                    row=1, col=1,
                )
        chart_min, chart_max = float(x["low"].min()), float(x["high"].max())
        visible_span = max(chart_max - chart_min, 0.01)
        current_price = float(x.iloc[-1]["close"])
        extension_colors = {"1.272":UI_COLORS['amber'], "1.414":"#ff8a65", "1.618":"#ec4899", "2.000":UI_COLORS['red']}
        visible_extensions = [
            (ratio, float(level)) for ratio, level in fib.get("extensions", {}).items()
            if abs(float(level) - current_price) <= visible_span * 1.35
        ]
        for extension_index, (fib_ratio, fib_level) in enumerate(visible_extensions):
            fig.add_hline(
                y=fib_level, line_dash="dashdot", line_color=extension_colors[fib_ratio],
                line_width=1.1 if fib_ratio in {"1.272","1.618"} else .85,
                annotation_text=f"Fib Ext {fib_ratio} · {fib_level:,.2f}",
                annotation_position="top left" if extension_index % 2 == 0 else "bottom left",
                annotation_font={"size":9,"color":extension_colors[fib_ratio]}, row=1, col=1,
            )
        if visible_extensions:
            fig.add_trace(
                go.Scatter(
                    x=[x["time"].iloc[-1]] * len(visible_extensions),
                    y=[level for _, level in visible_extensions], mode="markers",
                    marker={"size":1,"opacity":0}, showlegend=False, hoverinfo="skip",
                    name="Fib trend projection",
                ), row=1, col=1,
            )

    if not events.empty:
        bull = events[events["event"].isin(["SPRING", "SOS", "LPS"])]
        bear = events[events["event"].isin(["UT", "SOW"])]

        if not bull.empty:
            fig.add_trace(
                go.Scatter(
                    x=bull["time"],
                    y=bull["price"],
                    mode="markers+text",
                    text=bull["event"],
                    textposition="top center",
                    name="Wyckoff Bull",
                    marker={
                        "symbol": "triangle-up",
                        "size": 11,
                        "color": UI_COLORS['green'],
                        "line": {"width": 1, "color": "#0b0e11"},
                    },
                    textfont={"size": 10, "color": UI_COLORS['green']},
                ),
                row=1,
                col=1,
            )

        if not bear.empty:
            fig.add_trace(
                go.Scatter(
                    x=bear["time"],
                    y=bear["price"],
                    mode="markers+text",
                    text=bear["event"],
                    textposition="bottom center",
                    name="Wyckoff Bear",
                    marker={
                        "symbol": "triangle-down",
                        "size": 11,
                        "color": UI_COLORS['red'],
                        "line": {"width": 1, "color": "#0b0e11"},
                    },
                    textfont={"size": 10, "color": UI_COLORS['red']},
                ),
                row=1,
                col=1,
            )

    # Volume
    volume_colors = np.where(
        x["close"] >= x["open"],
        "#26a69a",
        UI_COLORS['red'],
    )

    fig.add_trace(
        go.Bar(
            x=x["time"],
            y=x["volume"],
            name="Volume",
            marker_color=volume_colors,
            opacity=0.65,
        ),
        row=2,
        col=1,
    )

    if "vol_ma20" in x.columns and x["vol_ma20"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=x["time"],
                y=x["vol_ma20"],
                mode="lines",
                name="Vol MA20",
                line={"color": UI_COLORS['muted'], "width": 1.2},
            ),
            row=2,
            col=1,
        )

    # RSI
    fig.add_trace(
        go.Scatter(
            x=x["time"],
            y=x["rsi14"],
            mode="lines",
            name="RSI14",
            line={"color": "#7e57c2", "width": 1.8},
        ),
        row=3,
        col=1,
    )

    fig.add_hrect(
        y0=70, y1=100,
        fillcolor=UI_COLORS['red'],
        opacity=0.06,
        line_width=0,
        row=3, col=1,
    )
    fig.add_hrect(
        y0=0, y1=30,
        fillcolor="#26a69a",
        opacity=0.06,
        line_width=0,
        row=3, col=1,
    )
    fig.add_hline(y=70, line_dash="dot", line_color=UI_COLORS['red'], row=3, col=1)
    fig.add_hline(y=50, line_dash="dot", line_color="#546e7a", row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="#26a69a", row=3, col=1)

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        height=760,
        margin={"l": 8, "r": 105, "t": 10, "b": 8},
        dragmode="pan",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        showlegend=True,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.01,
            "x": 0,
            "font": {"size": 10},
            "bgcolor": "rgba(0,0,0,0)",
        },
        font={"color": CHART_TEXT, "family": FONT_STACK, "size": 12},
        # Đổi timeframe sẽ reset zoom/range thay vì giữ trạng thái của chart trước.
        uirevision=f"internal-chart-{tf}",
    )

    fig.update_xaxes(
        showgrid=True,
        gridcolor="#1d242c",
        zeroline=False,
        autorange=False,
        range=[pd.to_datetime(x["time"].min()), pd.to_datetime(x["time"].max())],
    )
    if tf == "1D":
        fig.update_xaxes(rangebreaks=[{"bounds": ["sat", "mon"]}])
    fig.update_yaxes(
        side="right",
        fixedrange=False,
        automargin=True,
        showgrid=True,
        gridcolor="#1d242c",
        zeroline=False,
    )
    fig.update_yaxes(range=[0, 100], row=3, col=1)

    return fig, wy, events


def detail_table(df, x, tf, result_tf):
    latest = x.iloc[-1]
    fib = fibonacci_analysis(x, min(120, len(x)))
    rows = [
        ("Open", fmt(latest["open"])),
        ("High", fmt(latest["high"])),
        ("Low", fmt(latest["low"])),
        ("Close", fmt(latest["close"])),
        ("Volume", f"{int(latest['volume']):,}"),
        ("RVOL", fmt(latest.get("rvol"), 2)),
        ("ATR14", fmt(latest.get("atr14"), 2)),
        ("ATR %", fmt(latest.get("atr_pct"), 2)),
        ("ROC20 %", fmt(latest.get("roc20"), 2)),
        ("RSI14", fmt(latest.get("rsi14"), 2)),
        ("MACD", fmt(latest.get("macd"), 3)),
        ("MACD Signal", fmt(latest.get("macd_signal"), 3)),
        ("MACD Histogram", fmt(latest.get("macd_hist"), 3)),
        ("ADX14", fmt(latest.get("adx14"), 2)),
        ("+DI14", fmt(latest.get("plus_di14"), 2)),
        ("−DI14", fmt(latest.get("minus_di14"), 2)),
        ("OBV Bias", result_tf.get("obv_bias", "—")),
        ("MA20", fmt(latest.get("ma20"))),
        ("MA50", fmt(latest.get("ma50"))),
        ("MA100", fmt(latest.get("ma100"))),
        ("MA200", fmt(latest.get("ma200"))),
        ("MA Regime", result_tf.get("ma_regime", "—")),
        ("Fibonacci Trend", fib.get("direction", "—")),
        ("Fib Direction Source", fib.get("direction_source", "—")),
        ("Fib Nearest", f"{fib.get('nearest_ratio', '—')} · {fmt(fib.get('nearest_level'))}"),
        ("Fib Golden Zone", f"{fmt(fib.get('golden_zone', [None,None])[0])} – {fmt(fib.get('golden_zone', [None,None])[1])}"),
        ("Fib Extension 1.272", fmt(fib.get("extensions", {}).get("1.272"))),
        ("Fib Extension 1.618", fmt(fib.get("extensions", {}).get("1.618"))),
        ("Wyckoff Phase", result_tf.get("wyckoff_phase", "—")),
        ("Wyckoff Event", result_tf.get("wyckoff_event", "—")),
        ("Signal", result_tf.get("signal", "—")),
        ("Signal Score", result_tf.get("signal_score", "—")),
        ("Confidence", f"{result_tf.get('confidence', 0)}%"),
    ]
    return pd.DataFrame(rows, columns=["Metric", "Value"])


def scan_style(df):
    def color_signal(v):
        if "BUY" in str(v):
            return f"color:{UI_COLORS['green']};font-weight:700"
        if "SELL" in str(v):
            return f"color:{UI_COLORS['red']};font-weight:700"
        if "REDUCE" in str(v):
            return f"color:{UI_COLORS['amber']};font-weight:700"
        return f"color:{CHART_TEXT}"

    return themed_dataframe(df).map(color_signal, subset=["final_signal"])


# ============================================================
# APP
# ============================================================

# Top bar
APP_TITLES = {language: PROJECT_NAME for language in ("vi", "en", "zh", "ru", "de")}
APP_SUBTITLES = {
    "vi":"CỔ PHIẾU VIỆT NAM • WYCKOFF • FIBONACCI • ĐA KHUNG • BÀN GIAO DỊCH",
    "en":"VIETNAM STOCKS • WYCKOFF • FIBONACCI • MULTI-TIMEFRAME • TRADING DESK",
    "zh":"越南股票 • WYCKOFF • FIBONACCI • 多周期 • 交易台",
    "ru":"АКЦИИ ВЬЕТНАМА • WYCKOFF • FIBONACCI • МУЛЬТИТАЙМФРЕЙМ • ТОРГОВЫЙ ТЕРМИНАЛ",
    "de":"VIETNAM-AKTIEN • WYCKOFF • FIBONACCI • MULTI-TIMEFRAME • TRADING DESK",
}
ACTION_LABELS = {
    "vi": {},
    "en": {"MUA_CÓ_XÁC_NHẬN":"CONFIRMED BUY","THEO_DÕI_MUA":"WATCH TO BUY","NẮM_GIỮ":"HOLD","CHỜ_XÁC_NHẬN":"WAIT FOR CONFIRMATION","GIẢM_TỶ_TRỌNG":"REDUCE","BÁN_CÓ_XÁC_NHẬN":"CONFIRMED SELL"},
    "zh": {"MUA_CÓ_XÁC_NHẬN":"确认买入","THEO_DÕI_MUA":"关注买入","NẮM_GIỮ":"持有","CHỜ_XÁC_NHẬN":"等待确认","GIẢM_TỶ_TRỌNG":"降低仓位","BÁN_CÓ_XÁC_NHẬN":"确认卖出"},
    "ru": {"MUA_CÓ_XÁC_NHẬN":"ПОДТВЕРЖДЁННАЯ ПОКУПКА","THEO_DÕI_MUA":"НАБЛЮДАТЬ ДЛЯ ПОКУПКИ","NẮM_GIỮ":"ДЕРЖАТЬ","CHỜ_XÁC_NHẬN":"ЖДАТЬ ПОДТВЕРЖДЕНИЯ","GIẢM_TỶ_TRỌNG":"СОКРАТИТЬ","BÁN_CÓ_XÁC_NHẬN":"ПОДТВЕРЖДЁННАЯ ПРОДАЖА"},
    "de": {"MUA_CÓ_XÁC_NHẬN":"BESTÄTIGTER KAUF","THEO_DÕI_MUA":"KAUF BEOBACHTEN","NẮM_GIỮ":"HALTEN","CHỜ_XÁC_NHẬN":"BESTÄTIGUNG ABWARTEN","GIẢM_TỶ_TRỌNG":"REDUZIEREN","BÁN_CÓ_XÁC_NHẬN":"BESTÄTIGTER VERKAUF"},
}
ACTION_SUMMARIES = {
    "en":{"MUA_CÓ_XÁC_NHẬN":"Medium-term trend and daily trigger confirm an upward move.","THEO_DÕI_MUA":"The context leans bullish, but confirmation is not yet strong enough.","NẮM_GIỮ":"The trend remains mildly positive; manage existing exposure.","CHỜ_XÁC_NHẬN":"Signals are unclear or conflicting across timeframes.","GIẢM_TỶ_TRỌNG":"The combined structure is weakening; reduce risk.","BÁN_CÓ_XÁC_NHẬN":"Key timeframes confirm weakness; prioritize capital protection."},
    "zh":{"MUA_CÓ_XÁC_NHẬN":"中期趋势与日线触发共同确认上涨。","THEO_DÕI_MUA":"环境偏多，但确认强度仍不足。","NẮM_GIỮ":"趋势仍略偏积极，应管理现有仓位。","CHỜ_XÁC_NHẬN":"信号不清晰或多个周期存在冲突。","GIẢM_TỶ_TRỌNG":"综合结构转弱，应降低风险。","BÁN_CÓ_XÁC_NHẬN":"关键周期确认走弱，应优先保护资金。"},
    "ru":{"MUA_CÓ_XÁC_NHẬN":"Среднесрочный тренд и дневной триггер подтверждают рост.","THEO_DÕI_MUA":"Фон бычий, но подтверждение пока недостаточно.","NẮM_GIỮ":"Тренд умеренно позитивен; управляйте текущей позицией.","CHỜ_XÁC_NHẬN":"Сигналы неясны или конфликтуют между таймфреймами.","GIẢM_TỶ_TRỌNG":"Совокупная структура слабеет; снизьте риск.","BÁN_CÓ_XÁC_NHẬN":"Ключевые таймфреймы подтверждают слабость; защищайте капитал."},
    "de":{"MUA_CÓ_XÁC_NHẬN":"Mittelfristiger Trend und Tagessignal bestätigen den Anstieg.","THEO_DÕI_MUA":"Das Umfeld ist positiv, aber noch nicht ausreichend bestätigt.","NẮM_GIỮ":"Der Trend bleibt leicht positiv; bestehende Position verwalten.","CHỜ_XÁC_NHẬN":"Signale sind unklar oder zwischen Zeitrahmen widersprüchlich.","GIẢM_TỶ_TRỌNG":"Die Gesamtstruktur schwächt sich ab; Risiko reduzieren.","BÁN_CÓ_XÁC_NHẬN":"Wichtige Zeitrahmen bestätigen Schwäche; Kapital schützen."},
}
REGIME_LABELS = {
    "en":{"XU HƯỚNG TĂNG":"UPTREND","XU HƯỚNG GIẢM":"DOWNTREND","ĐI NGANG":"RANGE","ĐI NGANG / CHUYỂN PHA":"RANGE / TRANSITION","BIẾN ĐỘNG CAO":"HIGH VOLATILITY"},
    "zh":{"XU HƯỚNG TĂNG":"上升趋势","XU HƯỚNG GIẢM":"下降趋势","ĐI NGANG":"震荡","ĐI NGANG / CHUYỂN PHA":"震荡 / 转换阶段","BIẾN ĐỘNG CAO":"高波动"},
    "ru":{"XU HƯỚNG TĂNG":"ВОСХОДЯЩИЙ ТРЕНД","XU HƯỚNG GIẢM":"НИСХОДЯЩИЙ ТРЕНД","ĐI NGANG":"ДИАПАЗОН","ĐI NGANG / CHUYỂN PHA":"ДИАПАЗОН / ПЕРЕХОД","BIẾN ĐỘNG CAO":"ВЫСОКАЯ ВОЛАТИЛЬНОСТЬ"},
    "de":{"XU HƯỚNG TĂNG":"AUFWÄRTSTREND","XU HƯỚNG GIẢM":"ABWÄRTSTREND","ĐI NGANG":"SEITWÄRTS","ĐI NGANG / CHUYỂN PHA":"SEITWÄRTS / ÜBERGANG","BIẾN ĐỘNG CAO":"HOHE VOLATILITÄT"},
}
DRIVER_LABELS = {
    "en":{"Xu hướng MA":"MA trend","Cấu trúc Wyckoff":"Wyckoff structure","Động lượng":"Momentum","Khối lượng":"Volume","Điều chỉnh rủi ro":"Risk adjustment","Đa khung":"Multi-timeframe"},
    "zh":{"Xu hướng MA":"MA趋势","Cấu trúc Wyckoff":"Wyckoff结构","Động lượng":"动量","Khối lượng":"成交量","Điều chỉnh rủi ro":"风险调整","Đa khung":"多周期"},
    "ru":{"Xu hướng MA":"Тренд MA","Cấu trúc Wyckoff":"Структура Wyckoff","Động lượng":"Импульс","Khối lượng":"Объём","Điều chỉnh rủi ro":"Корректировка риска","Đa khung":"Мультитаймфрейм"},
    "de":{"Xu hướng MA":"MA-Trend","Cấu trúc Wyckoff":"Wyckoff-Struktur","Động lượng":"Momentum","Khối lượng":"Volumen","Điều chỉnh rủi ro":"Risikoanpassung","Đa khung":"Multi-Timeframe"},
}
CONFLICT_LABELS = {
    "en":{"THẤP":"LOW","TRUNG BÌNH":"MEDIUM","CAO":"HIGH"}, "zh":{"THẤP":"低","TRUNG BÌNH":"中","CAO":"高"},
    "ru":{"THẤP":"НИЗКИЙ","TRUNG BÌNH":"СРЕДНИЙ","CAO":"ВЫСОКИЙ"}, "de":{"THẤP":"NIEDRIG","TRUNG BÌNH":"MITTEL","CAO":"HOCH"},
}
LEVEL_LABELS = {
"vi":{"entry_low":"Vùng vào thấp","entry_high":"Vùng vào cao","trigger":"Mức kích hoạt","bullish_trigger":"Kích hoạt tăng","stop_loss":"Cắt lỗ tham khảo","protective_stop":"Mức bảo vệ","bearish_invalidation":"Mức vô hiệu","target_1":"Mục tiêu 1","target_2":"Mục tiêu 2","reference_target":"Mục tiêu tham khảo","support_reference":"Hỗ trợ tham khảo","recovery_level":"Mức hồi phục","reward_risk_1":"Reward/Risk mục tiêu 1"},
"en":{"entry_low":"Entry zone low","entry_high":"Entry zone high","trigger":"Trigger","bullish_trigger":"Bullish trigger","stop_loss":"Reference stop","protective_stop":"Protective stop","bearish_invalidation":"Bearish invalidation","target_1":"Target 1","target_2":"Target 2","reference_target":"Reference target","support_reference":"Reference support","recovery_level":"Recovery level","reward_risk_1":"Target 1 reward/risk"},
"zh":{"entry_low":"入场区下沿","entry_high":"入场区上沿","trigger":"触发位","bullish_trigger":"多头触发位","stop_loss":"参考止损","protective_stop":"保护止损","bearish_invalidation":"空头失效位","target_1":"目标1","target_2":"目标2","reference_target":"参考目标","support_reference":"参考支撑","recovery_level":"修复位","reward_risk_1":"目标1盈亏比"},
"ru":{"entry_low":"Нижняя граница входа","entry_high":"Верхняя граница входа","trigger":"Триггер","bullish_trigger":"Бычий триггер","stop_loss":"Ориентир стопа","protective_stop":"Защитный стоп","bearish_invalidation":"Отмена медвежьего сценария","target_1":"Цель 1","target_2":"Цель 2","reference_target":"Ориентир цели","support_reference":"Ориентир поддержки","recovery_level":"Уровень восстановления","reward_risk_1":"Риск/доходность цели 1"},
"de":{"entry_low":"Einstiegszone unten","entry_high":"Einstiegszone oben","trigger":"Auslöser","bullish_trigger":"Bullischer Auslöser","stop_loss":"Referenz-Stop","protective_stop":"Schutz-Stop","bearish_invalidation":"Bärische Invalidierung","target_1":"Ziel 1","target_2":"Ziel 2","reference_target":"Referenzziel","support_reference":"Referenz-Support","recovery_level":"Erholungsniveau","reward_risk_1":"Chance/Risiko Ziel 1"},
}
STRATEGY_LABELS = {
"en":{"KHÔNG_GIAO_DỊCH":"NO TRADE","MUA_KHI_BREAKOUT":"BUY ON BREAKOUT","CHỜ_BREAKOUT_HOẶC_PULLBACK":"WAIT FOR BREAKOUT OR PULLBACK","NẮM_GIỮ_VÀ_DỜI_CẮT_LỖ":"HOLD AND TRAIL STOP","THOÁT_VỊ_THẾ":"EXIT POSITION","GIẢM_TỶ_TRỌNG":"REDUCE EXPOSURE","CHỜ_TÍN_HIỆU_RÕ_RÀNG":"WAIT FOR CLEAR SIGNAL","CHỜ_DỮ_LIỆU_VÀ_THANH_KHOẢN":"WAIT FOR DATA AND LIQUIDITY"},
"zh":{"KHÔNG_GIAO_DỊCH":"不交易","MUA_KHI_BREAKOUT":"突破时买入","CHỜ_BREAKOUT_HOẶC_PULLBACK":"等待突破或回调","NẮM_GIỮ_VÀ_DỜI_CẮT_LỖ":"持有并移动止损","THOÁT_VỊ_THẾ":"退出仓位","GIẢM_TỶ_TRỌNG":"降低仓位","CHỜ_TÍN_HIỆU_RÕ_RÀNG":"等待明确信号","CHỜ_DỮ_LIỆU_VÀ_THANH_KHOẢN":"等待数据与流动性"},
"ru":{"KHÔNG_GIAO_DỊCH":"НЕ ТОРГОВАТЬ","MUA_KHI_BREAKOUT":"ПОКУПКА НА ПРОБОЕ","CHỜ_BREAKOUT_HOẶC_PULLBACK":"ЖДАТЬ ПРОБОЯ ИЛИ ОТКАТА","NẮM_GIỮ_VÀ_DỜI_CẮT_LỖ":"ДЕРЖАТЬ И ПЕРЕНОСИТЬ СТОП","THOÁT_VỊ_THẾ":"ВЫЙТИ ИЗ ПОЗИЦИИ","GIẢM_TỶ_TRỌNG":"СОКРАТИТЬ ПОЗИЦИЮ","CHỜ_TÍN_HIỆU_RÕ_RÀNG":"ЖДАТЬ ЯСНОГО СИГНАЛА","CHỜ_DỮ_LIỆU_VÀ_THANH_KHOẢN":"ЖДАТЬ ДАННЫХ И ЛИКВИДНОСТИ"},
"de":{"KHÔNG_GIAO_DỊCH":"KEIN HANDEL","MUA_KHI_BREAKOUT":"BEIM AUSBRUCH KAUFEN","CHỜ_BREAKOUT_HOẶC_PULLBACK":"AUF AUSBRUCH ODER RÜCKSETZER WARTEN","NẮM_GIỮ_VÀ_DỜI_CẮT_LỖ":"HALTEN UND STOP NACHZIEHEN","THOÁT_VỊ_THẾ":"POSITION SCHLIESSEN","GIẢM_TỶ_TRỌNG":"POSITION REDUZIEREN","CHỜ_TÍN_HIỆU_RÕ_RÀNG":"AUF KLARES SIGNAL WARTEN","CHỜ_DỮ_LIỆU_VÀ_THANH_KHOẢN":"AUF DATEN UND LIQUIDITÄT WARTEN"},
}

def display_code(value, mapping):
    return ui_sentence(mapping.get(LANG, {}).get(str(value), str(value)))
st.markdown(
    f"""
    <div class="tv-topbar">
      <div class="brand-wrap">
        <div class="stock-logo" aria-label="Stock market logo">
          <svg viewBox="0 0 32 32" role="img" aria-hidden="true">
            <path d="M5 25.5H27" stroke="#53677c" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M6.5 22L12 16.5L16.2 19L25.5 8.5" fill="none" stroke="#f5a623" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M20.5 8.5H25.5V13.5" fill="none" stroke="#64b5f6" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
            <circle cx="12" cy="16.5" r="2" fill="#a78bfa"/>
          </svg>
        </div>
        <div class="brand-copy">
          <div class="brand-line"><div class="tv-title">{tr(LANG, 'brand_title')}</div></div>
          <div class="tv-sub">{tr(LANG, 'brand_sub')}</div>
        </div>
      </div>
          <div class="top-meta"><span class="live-dot"></span>{tr(LANG, 'online')} • PRO DECISION V3<br>{tr(LANG, 'window')} • {BUILD_ID}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        f'<div class="sidebar-section-label">{tr(LANG, "market")} · {tr(LANG, "new_analysis")}</div>',
        unsafe_allow_html=True,
    )
    market_scope = st.selectbox(
        tr(LANG, "market"),
        list(MARKET_SCOPES),
        format_func=lambda key: MARKET_SCOPES[key],
        help=tr(LANG, "market"),
    )

try:
    market_listing = load_universe(market_scope)
except Exception as exc:
    st.error(f"Không lấy được danh sách {MARKET_SCOPES[market_scope]}.")
    st.code(str(exc))
    st.stop()

if market_listing.empty:
    if market_scope == "FAVORITES":
        st.info("Rổ Yêu thích đang trống. Chuyển sang VN30, VN100 hoặc một sàn rồi bấm ☆ để thêm mã.")
    else:
        st.error(f"Danh sách {MARKET_SCOPES[market_scope]} rỗng.")
    st.stop()

universe = market_listing["symbol"].tolist()
exchange_by_symbol = market_listing.set_index("symbol")["exchange"].to_dict()

scan_key = market_scope.lower()
scan_prefix = f"{scan_key}_scan" if scan_key in {"vn30", "vn100"} else f"market_scan_{scan_key}"
scan_path = PROCESSED_DIR / f"{scan_prefix}.csv"
scan_meta_path = PROCESSED_DIR / f"{scan_prefix}_meta.json"

with st.sidebar:
    symbol = st.selectbox(
        f"{tr(LANG, 'symbol')} {MARKET_SCOPES[market_scope]}",
        universe,
        help=f"Có {len(universe)} mã trong phạm vi đang chọn.",
    )

    tf = st.segmented_control(tr(LANG, "timeframe"), TF_ORDER, default="1D", key="stock_chart_timeframe", width="stretch") or "1D"
    st.caption(tr(LANG, "candle", period=period(LANG, tf)))
    st.caption("Khung nến biểu đồ độc lập với khung chọn trong danh mục và chu kỳ quét BOT.")

    refresh = st.button(f"↻ {tr(LANG, 'new_analysis')}", width="stretch")
    manual_data_check = st.button(
        f"◉ {tr(LANG, 'manual_data_check')}", width="stretch",
        help=tr(LANG, "manual_data_help"),
    )
    execute_paper = False
    if SYSTEM_MODE == "PAPER":
        execute_paper = st.button(f"▶ {tr(LANG, 'paper_cycle')}", type="primary", width="stretch")
    else:
        st.button("🔒 LIVE ORDER", width="stretch", disabled=True,
                  help=tr(LANG,"live_readonly"))

    if manual_data_check:
        with st.spinner("Đang kiểm tra cơ sở · toàn bộ hợp đồng phái sinh · phân tích đa khung · BOT..."):
            _auto_data_health.clear()
            st.session_state.manual_data_report = _refresh_data_health(symbol, check_all_futures=True)
            valuation_check = load_valuation(symbol, refresh=True)
            st.session_state.manual_data_report["valuation"] = valuation_check
            if valuation_check["status"] == "UNAVAILABLE":
                st.session_state.manual_data_report["errors"].append(vt(LANG, "UNAVAILABLE"))
        report = st.session_state.manual_data_report
        if report.get("errors"):
            st.warning("Kiểm tra hoàn tất nhưng có cảnh báo: " + " • ".join(report["errors"]))
        else:
            st.success(
                f"Dữ liệu mới hợp lệ · {symbol} {fmt(report['spot'].get('price'))} / "
                f"{report['spot'].get('action','—')} · Phái sinh "
                f"{report['futures'].get('checked_contracts',0)}/{report['futures'].get('available_contracts',0)} hợp đồng "
                f"· {report['futures'].get('list_source','—')}"
            )
        futures_health_rows = report.get("futures",{}).get("contracts",[])
        if futures_health_rows:
            futures_health_view = [{
                "Hợp đồng":item.get("symbol"), "Trạng thái":item.get("status"),
                "Giá":item.get("price"), "Action":item.get("action"), "Score":item.get("score"),
                "Nến 15M":item.get("rows",{}).get("15M"), "Nến 1H":item.get("rows",{}).get("1H"),
                "Nến 1D":item.get("rows",{}).get("1D"),
                "Cập nhật 15M":item.get("latest",{}).get("15M"),
                "Nguồn":item.get("sources",{}).get("15M"), "Lỗi":item.get("error"),
            } for item in futures_health_rows]
            desk_dataframe(themed_dataframe(pd.DataFrame(futures_health_view)), width="stretch", hide_index=True)
        st.session_state.auto_data_signature = None

    auto_data_health_panel(symbol)

    favorite_now = is_favorite(symbol)
    favorite_label = f"★ {tr(LANG, 'favorite_remove')}" if favorite_now else f"☆ {tr(LANG, 'favorite_add')}"
    if st.button(favorite_label, width="stretch"):
        if favorite_now:
            remove_favorite(symbol)
        else:
            add_favorite(symbol, exchange_by_symbol.get(symbol, "HOSE"))
        st.cache_data.clear()
        st.rerun()

    st.markdown(
        f'<div class="sidebar-section-label">{tr(LANG, "automation")}</div>',
        unsafe_allow_html=True,
    )
    broker = PaperBroker(STATE_DIR / "paper_portfolio.json")
    portfolio = broker.snapshot()
    status = bot_status(ROOT)
    if SYSTEM_MODE == "LIVE":
        status = {"running":False, "mode":"LIVE"}
    if status.get("running"):
        heartbeat = status.get("heartbeat", {})
        bot_target_label = MARKET_SCOPES.get(status.get("scope"), status.get("symbol") or "—")
        st.markdown(f"<div class='bot-status bot-running'>● Running · Paper<br>{bot_target_label} · {tr(LANG,'every_minutes',minutes=status.get('interval_minutes','—'))}</div>", unsafe_allow_html=True)
        if heartbeat:
            hb_time = pd.Timestamp.fromtimestamp(heartbeat.get("updated_at", 0)).strftime("%H:%M:%S")
            with st.container(key="sidebar_bot_last_scan"):
                if heartbeat.get("target_type") == "SCOPE":
                    st.caption(f"{tr(LANG,'bot_scan')}: {hb_time} · {heartbeat.get('action','—')} · {heartbeat.get('scanned',0)}/{heartbeat.get('total','—')} mã · {heartbeat.get('orders_count',0)} lệnh")
                else:
                    st.caption(f"{tr(LANG,'bot_scan')}: {hb_time} · {heartbeat.get('action','—')} · {fmt(heartbeat.get('price'))}")
    else:
        if SYSTEM_MODE == "LIVE":
            st.markdown("<div class='bot-status bot-stopped'>🔒 Live · Read-only<br>Order API locked</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='bot-status bot-stopped'>○ {tr(LANG,'bot_stopped')}</div>", unsafe_allow_html=True)

    equity_risk_reset = st.session_state.pop("equity_bot_risk_level_reset", None)
    if equity_risk_reset in {"LOW", "MEDIUM", "HIGH"}:
        st.session_state.equity_bot_risk_level = equity_risk_reset
    if "equity_bot_risk_applied" not in st.session_state:
        st.session_state.equity_bot_risk_applied = st.session_state.get("equity_bot_risk_level", "MEDIUM")
    if status.get("running") and status.get("risk_level") in {"LOW", "MEDIUM", "HIGH"}:
        st.session_state.equity_bot_risk_level = status["risk_level"]
        st.session_state.equity_bot_risk_applied = status["risk_level"]
    bot_mode = SYSTEM_MODE
    bot_target_mode = st.segmented_control(
        "Phạm vi BOT", ["Một mã", "Quét rổ"], default="Một mã", width="stretch",
        key="equity_bot_target_mode",
    ) or "Một mã"
    bot_scope = None
    if bot_target_mode == "Quét rổ":
        bot_scope = st.selectbox(
            "Rổ / thị trường cần quét", list(MARKET_SCOPES),
            format_func=lambda key: MARKET_SCOPES[key], key="equity_bot_scope",
            help="Mỗi chu kỳ phân tích toàn bộ phạm vi; mã có MUA CÓ XÁC NHẬN sẽ mua đúng 500 cổ phiếu nếu đủ điều kiện rủi ro.",
        )
        st.caption("Lệnh mua cố định: 500 cổ phiếu/mã · không giới hạn số vị thế · vẫn kiểm soát vốn và tỷ trọng · PAPER only")
    interval = st.segmented_control(tr(LANG, "scan_cycle"), [15, 30, 60], default=30, format_func=lambda value: f"{value}m", width="stretch") or 30
    st.caption("Chu kỳ BOT là thời gian giữa hai lượt quét; không phải độ dài một cây nến.")
    equity_risk_level = st.segmented_control(
        "Quản trị rủi ro", ["LOW", "MEDIUM", "HIGH"], default="MEDIUM",
        format_func=lambda value: {"LOW":"Thấp", "MEDIUM":"Trung bình", "HIGH":"Cao"}[value],
        key="equity_bot_risk_level", width="stretch",
        disabled=bool(status.get("running")) or SYSTEM_MODE == "LIVE",
        help="Thấp: thận trọng và quy mô nhỏ hơn. Trung bình: tiêu chuẩn hiện tại. Cao: ngưỡng vào linh hoạt và quy mô lớn hơn; khóa lỗ vẫn luôn hoạt động.",
    ) or "MEDIUM"
    st.caption({
        "LOW":"Thận trọng · Confidence ≥ 78% · Đồng thuận ≥ 75% · giảm quy mô rủi ro.",
        "MEDIUM":"Cân bằng · giữ nguyên tiêu chuẩn vào lệnh hiện tại.",
        "HIGH":"Linh hoạt · có thể xét WATCH BUY mạnh · Confidence ≥ 62% · Đồng thuận ≥ 55%.",
    }[equity_risk_level])
    if (
        equity_risk_level != st.session_state.equity_bot_risk_applied
        and not status.get("running") and SYSTEM_MODE == "PAPER"
    ):
        confirm_bot_risk_and_start(
            market="equity", level=equity_risk_level, interval=int(interval),
            symbol=None if bot_target_mode == "Quét rổ" else symbol,
            scope=bot_scope if bot_target_mode == "Quét rổ" else None,
        )
    start_col, stop_col = st.columns(2)
    with start_col:
        with st.container(key="bot_start_control"):
            start_requested = st.button("▶ Start", width="stretch", disabled=bool(status.get("running")) or SYSTEM_MODE == "LIVE")
    if start_requested:
        try:
            if bot_mode == "LIVE":
                raise RuntimeError("LIVE đang khóa: chưa có adapter API chính thức của công ty chứng khoán.")
            if bot_target_mode == "Quét rổ":
                start_bot(ROOT, int(interval), scope=bot_scope, risk_level=st.session_state.equity_bot_risk_applied)
                st.toast(f"Đã chạy BOT PAPER quét {MARKET_SCOPES[bot_scope]} · mua 500 CP khi xác nhận")
            else:
                start_bot(ROOT, int(interval), symbol=symbol, risk_level=st.session_state.equity_bot_risk_applied)
                st.toast(f"Đã chạy {symbol} PAPER mỗi {interval} phút")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    with stop_col:
        with st.container(key="bot_stop_control"):
            stop_requested = st.button("■ Stop", width="stretch", disabled=not bool(status.get("running")))
    if stop_requested:
        try:
            stop_bot(ROOT); st.toast("Đã dừng bot"); st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if SYSTEM_MODE == "PAPER":
        bot_risk_alert_panel()

    st.caption(f"{tr(LANG, 'analysis_frame')} 1D • 1W • 1M • 1Y")
    st.caption(tr(LANG, "risk_line"))
    if SYSTEM_MODE == "PAPER":
        st.caption(tr(LANG, "paper_assets", value=f"{portfolio['equity_vnd']:,.0f}", positions=len(portfolio['positions'])))
    else:
        st.caption(f"LIVE · READ-ONLY · {tr(LANG,'live_readonly')}")

    st.markdown(
        f'<div class="sidebar-section-label">{tr(LANG, "futures_desk")}</div>',
        unsafe_allow_html=True,
    )
    # Keep the sidebar futures card synchronized with the contract selected in
    # the Futures tab. Previously this block was hard-coded to VN30F1M, so its
    # quote, PAPER ledger and analysis could describe a different contract.
    sidebar_futures_symbol = st.session_state.get("selected_futures_contract", "VN30F1M")
    st.markdown(f'<div class="sidebar-futures-title">◆ {sidebar_futures_symbol} · Phái sinh</div>', unsafe_allow_html=True)
    realtime_futures_panel(sidebar_futures_symbol, compact=True)
    try:
        sidebar_futures_frames, _sidebar_futures_meta = load_vn30f1m_cached(
            0, sidebar_futures_symbol
        )
        sidebar_futures_price = None
        sidebar_futures_change = None
        for sidebar_tf in ("15M", "1H", "1D"):
            sidebar_frame = sidebar_futures_frames.get(sidebar_tf, pd.DataFrame())
            if not sidebar_frame.empty:
                sidebar_futures_price = float(sidebar_frame.iloc[-1]["close"])
                if len(sidebar_frame) >= 2:
                    sidebar_futures_change = sidebar_futures_price - float(sidebar_frame.iloc[-2]["close"])
                break
        # Use the same fresh-quote policy as the Futures tab. Technical signals
        # still use closed candles, while the displayed mark and P&L use live.
        sidebar_live_quote = st.session_state.get("realtime_futures_quotes", {}).get(
            sidebar_futures_symbol, {}
        )
        if (
            sidebar_live_quote.get("status") == "OK"
            and (
                sidebar_live_quote.get("market_age_seconds") is None
                or float(sidebar_live_quote["market_age_seconds"]) <= 15
            )
        ):
            live_mark = float(sidebar_live_quote["price"])
            previous_close = None
            for sidebar_tf in ("15M", "1H", "1D"):
                sidebar_frame = sidebar_futures_frames.get(sidebar_tf, pd.DataFrame())
                if not sidebar_frame.empty:
                    previous_close = float(sidebar_frame.iloc[-2 if len(sidebar_frame) >= 2 else -1]["close"])
                    break
            sidebar_futures_price = live_mark
            if previous_close is not None:
                sidebar_futures_change = live_mark - previous_close
        sidebar_futures_broker = PaperFuturesBroker(
            STATE_DIR / f"paper_futures_{sidebar_futures_symbol.lower()}.json"
        )
        sidebar_futures_account = sidebar_futures_broker.snapshot(sidebar_futures_price)
        sidebar_futures_result = analyze_vn30f1m(
            sidebar_futures_frames,
            account_equity_vnd=float(sidebar_futures_account["equity_vnd"]),
            symbol=sidebar_futures_symbol,
        )
        sidebar_futures_bot = futures_bot_status(ROOT)
        if sidebar_futures_result.get("status") == "OK":
            sidebar_action = sidebar_futures_result.get("action", "WAIT_CONFIRMATION")
            sidebar_action_color = {
                "LONG":UI_COLORS['green'], "SHORT":UI_COLORS['red'], "STAND_ASIDE":UI_COLORS['amber'],
                "WAIT_CONFIRMATION":UI_COLORS['blue'], "NO_TRADE":UI_COLORS['muted'],
            }.get(sidebar_action, UI_COLORS['muted'])
            sidebar_change_color = UI_COLORS['green'] if (sidebar_futures_change or 0) >= 0 else UI_COLORS['red']
            sidebar_position = sidebar_futures_account.get("side", "FLAT")
            sidebar_position_qty = int(sidebar_futures_account.get("quantity", 0))
            sidebar_pnl = float(sidebar_futures_account.get("unrealized_pnl_vnd", 0))
            if SYSTEM_MODE == "LIVE":
                sidebar_position, sidebar_position_qty, sidebar_pnl = "READ-ONLY", 0, 0.0
            st.markdown(
                f"""
                <div style="border:1px solid {CHART_BORDER};border-radius:10px;padding:10px 11px;
                            background:{CHART_CONTROL_BG};box-shadow:0 8px 24px rgba(0,0,0,.10)">
                  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
                    <div><div style="font-size:18px;font-weight:800;color:{CHART_TEXT}">{sidebar_futures_price:,.1f}</div>
                    <div style="font-size:11px;color:{sidebar_change_color};font-weight:700">{sidebar_futures_change or 0:+,.1f} điểm · 15M</div></div>
                    <div style="text-align:right;color:{sidebar_action_color};font-size:12px;font-weight:850">{sidebar_action.replace('_',' ')}<br>
                    <span style="font-size:10px">Score {sidebar_futures_result.get('score',0):+.1f}</span></div>
                  </div>
                  <div style="height:1px;background:{CHART_BORDER};margin:8px 0"></div>
                  <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px 8px;font-size:11px;color:{CHART_TEXT}">
                    <span>Xu hướng</span><b style="text-align:right">{sidebar_futures_result.get('regime','—')}</b>
                    <span>Hỗ trợ</span><b style="text-align:right;color:{CHART_TEXT}">{sidebar_futures_result.get('support',0):,.1f}</b>
                    <span>Kháng cự</span><b style="text-align:right;color:{CHART_TEXT}">{sidebar_futures_result.get('resistance',0):,.1f}</b>
                    <span>{SYSTEM_MODE}</span><b style="text-align:right">{sidebar_position}{f' · {sidebar_position_qty} HĐ' if SYSTEM_MODE == 'PAPER' else ''}</b>
                    <span>P&amp;L mở</span><b style="text-align:right;color:{UI_COLORS['green'] if sidebar_pnl >= 0 else UI_COLORS['red']}">{f'{sidebar_pnl:+,.0f} ₫' if SYSTEM_MODE == 'PAPER' else '—'}</b>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.container(key="sidebar_futures_bot_state"):
                if sidebar_futures_bot.get("running"):
                    sidebar_hb = sidebar_futures_bot.get("heartbeat", {})
                    st.success(f"● BOT Futures đang chạy · {sidebar_hb.get('action','WAIT')}")
                else:
                    st.caption(f"○ BOT Futures đang dừng · quản lý chi tiết tại tab Phái Sinh ({sidebar_futures_symbol})")
        else:
            st.caption(f"{sidebar_futures_symbol}: chưa đủ dữ liệu để phân tích nhanh.")
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as sidebar_futures_exc:
        st.caption(f"{sidebar_futures_symbol} tạm chưa khả dụng: {sidebar_futures_exc}")

    st.markdown(
        f'<div class="sidebar-section-label data-settings-label">{tr(LANG, "data_settings")}</div>',
        unsafe_allow_html=True,
    )
    if SYSTEM_MODE == "LIVE":
        st.error(f"🔒 {tr(LANG,'live_locked')}")
        st.caption(tr(LANG, "live_note"))

    with st.expander(f"⚙ {tr(LANG, 'data_settings')}"):
        favorites = load_watchlist()
        st.caption(tr(LANG, "favorite_count", count=len(favorites)))
        if not favorites.empty:
            st.write(", ".join(favorites["symbol"].tolist()))
        api_key = st.text_input("VNSTOCK_API_KEY", type="password")
        if st.button(tr(LANG, "save_api"), width="stretch"):
            try:
                save_api_key(api_key); st.cache_data.clear(); st.success(tr(LANG, "api_saved"))
            except (OSError, ValueError) as exc:
                st.error(str(exc))

    with st.expander(f"⇩ {tr(LANG, 'download_data')}", expanded=False):
        render_data_download_panel(LANG, "sidebar_download")
    with st.expander(f"✦ {tr(LANG, 'ai_key')}", expanded=False):
        openai_key = st.text_input(tr(LANG, "ai_key"), type="password", placeholder="sk-…")
        if st.button(f"✦ {tr(LANG, 'ai_key')}", width="stretch"):
            try:
                save_openai_api_key(openai_key); st.success(tr(LANG, "ai_key_saved"))
            except (OSError, ValueError) as exc:
                st.error(str(exc))

    if execute_paper:
        from src.trading_engine import paper_cycle
        try:
            cycle = paper_cycle(
                ROOT, symbol,
                risk_level=st.session_state.get("equity_bot_risk_level", "MEDIUM"),
            )
            if cycle["order"]: st.toast(f"PAPER {cycle['order']['side']} {cycle['order']['quantity']} {symbol}")
            else: st.toast(f"{tr(LANG,'no_order')} · {ACTION_LABELS.get(LANG,{}).get(cycle['analysis']['system_action'], cycle['analysis']['system_action'].replace('_', ' '))}")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

if refresh:
    st.cache_data.clear()

try:
    df = get_history(symbol, refresh=refresh)
    result = analyze_cached(symbol, df)
except Exception as exc:
    st.error(f"{symbol}: lỗi dữ liệu/phân tích")
    st.code(str(exc))
    st.markdown(f"### ⇩ {tr(LANG, 'download_data')}")
    st.info(tr(LANG, "download_recovery"))
    render_data_download_panel(LANG, "recovery_download")
    st.stop()

x = resampled(df, tf)
rtf = result["timeframes"].get(tf, {})
if tf != "1D":
    st.caption(f"{tf}: {len(x)} nến gộp từ OHLCV ngày thực có. Ngày trên nến là phiên cuối có dữ liệu, không phải dữ liệu tương lai. Kỳ đầu/cuối có thể chưa trọn kỳ.")
    if len(x) < 20:
        st.info(f"Khung {tf} chỉ có {len(x)} nến; chưa đủ MA20. MA/RSI/Wyckoff thiếu lịch sử không được nội suy.")

latest = x.iloc[-1]
prev_close = x.iloc[-2]["close"] if len(x) >= 2 else np.nan
change_pct = pct_change(float(latest["close"]), float(prev_close)) if pd.notna(prev_close) else None
price_color = "tv-green" if (change_pct or 0) >= 0 else "tv-red"
data_quality = result.get("data_quality", {})

# Header instrument strip
st.markdown(
    f'<div class="section-heading quick-overview-heading"><h2>{tr(LANG, "quick_overview")}</h2><span>{tr(LANG, "data_to")} {pd.to_datetime(latest["time"]).strftime("%d/%m/%Y")} • {MARKET_SCOPES[market_scope]}</span></div>',
    unsafe_allow_html=True,
)
action = result.get("system_action", "CHỜ_XÁC_NHẬN")
action_display = ui_sentence(ACTION_LABELS.get(LANG, {}).get(action, action.replace("_", " ")))
action_summary = ACTION_SUMMARIES.get(LANG, {}).get(action, result.get("decision_summary", ""))
score = float(rtf.get("signal_score", 0) or 0)
k1, k2, k3, k4 = st.columns(4)
k1.metric(symbol, fmt(latest["close"]), delta=f"{(change_pct or 0):+.2f}%")
k2.metric(tr(LANG, "decision"), action_display)
k3.metric(tr(LANG, "total_score"), f"{float(result.get('consensus_score', 0)):+.1f}")
conflict_display = display_code(result.get("conflict_level", "—"), CONFLICT_LABELS)
regime_display = display_code(result.get("market_regime", "—"), REGIME_LABELS)
k4.metric(tr(LANG, "confidence"), f"{result.get('confidence', 0)}%", delta=f"{tr(LANG,'grade')} {result.get('decision_grade', '—')} · {tr(LANG,'conflict')} {conflict_display}")

# Automated confluence decision
action_color = (
    UI_COLORS["green"] if "MUA" in action
    else UI_COLORS["red"] if "BÁN" in action
    else UI_COLORS["amber"] if "GIẢM" in action
    else UI_COLORS["blue"] if "GIỮ" in action
    else UI_COLORS["muted"]
)
overview_left, overview_right = st.columns([1.18, 1], gap="medium")
score_width = max(0, min(100, (float(result.get("consensus_score", 0)) + 100) / 2))
with overview_left:
    st.markdown(f"""<div class="cockpit"><div class="cockpit-head"><div class="cockpit-title">{tr(LANG,'system_decision')} · PRO V3</div><div class="mode-chip">{regime_display} · {symbol}</div></div><div class="action-row"><div class="action-badge" style="color:{action_color};background:{action_color}18;border:1px solid {action_color}55">{action_display}</div><div class="action-summary">{action_summary}</div></div><div class="stat-grid"><div class="stat-box"><div class="stat-label">{tr(LANG,'aggregate')}</div><div class="stat-value">{result.get('consensus_score',0):+.1f}</div></div><div class="stat-box"><div class="stat-label">{tr(LANG,'confidence')}</div><div class="stat-value">{result.get('confidence',0)}%</div></div><div class="stat-box"><div class="stat-label">{tr(LANG,'alignment')}</div><div class="stat-value">{result.get('timeframe_alignment',0)}%</div></div><div class="stat-box"><div class="stat-label">{tr(LANG,'evidence_grade')}</div><div class="stat-value">{result.get('decision_grade','—')}</div></div></div><div class="score-axis"><div class="score-marker" style="left:{score_width}%"></div></div></div>""", unsafe_allow_html=True)
with overview_right:
    if SYSTEM_MODE == "PAPER":
        paper_positions = portfolio.get("positions", {})
        position_count = len(paper_positions)
        total_quantity = sum(int(pos.get("quantity", 0)) for pos in paper_positions.values())
        position_value = sum(
            broker.market_value_vnd(
                int(pos.get("quantity", 0)),
                float(pos.get("last_price", pos.get("avg_price", 0)) or 0),
            )
            for pos in paper_positions.values()
        )
        dot_class = "long-dot" if position_count else "flat-dot"
        position_name = tr(LANG, "paper_positions_summary", count=position_count)
        st.markdown(f"""<div class="cockpit"><div class="cockpit-head"><div class="cockpit-title">{tr(LANG,'paper_account')}</div><div class="mode-chip">PAPER · {tr(LANG,'long_only')} · 1×</div></div><div class="account-status"><div class="{dot_class}"></div><div><div class="position-badge">{position_name}</div><div class="action-summary">{tr(LANG,'paper_position_value')}: {position_value:,.0f} ₫</div></div></div><div class="account-grid"><div class="account-cell"><div class="stat-label">{tr(LANG,'cash')}</div><div class="stat-value">{portfolio['cash_vnd']:,.0f} ₫</div></div><div class="account-cell"><div class="stat-label">{tr(LANG,'equity')}</div><div class="stat-value">{portfolio['equity_vnd']:,.0f} ₫</div></div><div class="account-cell"><div class="stat-label">{tr(LANG,'paper_total_quantity')}</div><div class="stat-value">{total_quantity:,} {tr(LANG,'shares')}</div></div><div class="account-cell"><div class="stat-label">{tr(LANG,'paper_open_positions')}</div><div class="stat-value">{position_count}</div></div></div><div class="account-hint">{tr(LANG,'paper_account_hint')}</div></div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""<div class="cockpit"><div class="cockpit-head"><div class="cockpit-title">LIVE · Read-only</div><div class="mode-chip">{tr(LANG,'market_data')}</div></div><div class="account-status"><div class="long-dot"></div><div><div class="position-badge">{symbol}</div><div class="action-summary">{tr(LANG,'live_readonly')}</div></div></div><div class="account-grid"><div class="account-cell"><div class="stat-label">{tr(LANG,'price_label')}</div><div class="stat-value">{fmt(latest['close'])}</div></div><div class="account-cell"><div class="stat-label">{tr(LANG,'signal_label')}</div><div class="stat-value">{action_display}</div></div><div class="account-cell"><div class="stat-label">{tr(LANG,'score_label')}</div><div class="stat-value">{result.get('consensus_score',0):+.1f}</div></div><div class="account-cell"><div class="stat-label">{tr(LANG,'order_api')}</div><div class="stat-value">{tr(LANG,'locked')}</div></div></div></div>""", unsafe_allow_html=True)

drivers = result.get("decision_drivers", [])
driver_html = "".join(
    f'<div class="driver-row"><span>{display_code(item["name"], DRIVER_LABELS)}</span><b class="{"driver-pos" if item["score"] > 0 else "driver-neg" if item["score"] < 0 else "driver-flat"}">{item["score"]:+.1f}</b></div>'
    for item in drivers
) or f'<div class="quality-copy">{tr(LANG,"no_risk")}</div>'
grade = result.get("decision_grade", "—")
confirmation = (
    f'{tr(LANG,"data")} {data_quality.get("data_quality", "—")} • {tr(LANG,"coverage")} {result.get("evidence_coverage", 0)}%<br>'
    f'{tr(LANG,"quality")} {result.get("evidence_quality", 0)}% • {tr(LANG,"conflict")} {conflict_display}'
)
risk_flags = result.get("risk_flags", [])
risk_preview = risk_flags[:2] if risk_flags and LANG == "vi" else ([f"{tr(LANG,'risk_attention')}: {len(risk_flags)}"] if risk_flags else [tr(LANG,"no_risk")])
risk_html = "".join(f'<div class="driver-row"><span>{text}</span></div>' for text in risk_preview)
st.markdown(f"""<div class="pro-insights"><div class="insight-panel"><div class="insight-title">{tr(LANG,'decision_drivers')}</div>{driver_html}</div><div class="insight-panel"><div class="insight-title">{tr(LANG,'decision_quality')}</div><div class="quality-line"><div class="grade-badge">{grade}</div><div class="quality-copy">{confirmation}</div></div></div><div class="insight-panel"><div class="insight-title">{tr(LANG,'risk_attention')}</div>{risk_html}</div></div>""", unsafe_allow_html=True)

if data_quality and data_quality.get("data_quality") != "GOOD":
    st.warning(tr(LANG, "data_quality_warning", quality=data_quality.get('data_quality', '—'), days=data_quality.get('age_days', '—'), turnover=f"{float(data_quality.get('median_turnover_20d_vnd', 0))/1_000_000:,.0f}"))

if risk_flags:
    with st.container(key="multiframe_conflict_alert"):
        st.warning(f"{tr(LANG,'warning')}: " + (" • ".join(risk_flags) if LANG == "vi" else f"{len(risk_flags)}"))

# News/event context for the selected symbol. The impact is deliberately capped
# at +/-10 so an isolated headline cannot reverse the technical model by itself.
with st.expander(f"📰 {tr(LANG, 'news_events')}", expanded=False):
    with st.spinner(tr(LANG, "loading_news", symbol=symbol)):
        company_news, news_error = load_company_news(symbol, refresh_news=refresh)
    news_context = score_news(company_news, lookback_days=30)
    news_score = float(news_context["score"])
    combined_score = max(-100.0, min(100.0, float(result.get("consensus_score", 0)) + news_score))

    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Sắc thái tin 30 ngày", news_context["label"])
    n2.metric("Tác động tin", f"{news_score:+.1f}", help="Điểm tiêu đề có trọng số thời gian, giới hạn từ -10 đến +10.")
    n3.metric("Số tin đã đánh giá", news_context["count"])
    n4.metric("Điểm kỹ thuật + tin", f"{combined_score:.1f}", delta=f"{news_score:+.1f} từ tin")

    if news_error:
        st.info(f"Nguồn tin tạm thời chưa đầy đủ: {news_error}")
    if news_context["count"] == 0:
        st.caption("Chưa có tin trong 30 ngày để điều chỉnh bối cảnh. Điểm kỹ thuật được giữ nguyên.")
    else:
        news_table = pd.DataFrame(news_context["items"])
        news_table["published"] = pd.to_datetime(news_table["published"]).dt.strftime("%d/%m/%Y %H:%M")
        news_table["impact_label"] = news_table["impact"].map(
            lambda value: "Tích cực" if value > 0 else "Tiêu cực" if value < 0 else "Trung tính"
        )
        desk_dataframe(
            themed_dataframe(news_table.rename(columns={
                "published": "Thời gian", "title": "Tiêu đề", "source": "Nguồn",
                "event_type": "Loại sự kiện", "impact_label": "Ảnh hưởng",
                "impact": "Điểm", "url": "Liên kết",
            })[["Thời gian", "Tiêu đề", "Loại sự kiện", "Ảnh hưởng", "Điểm", "Nguồn", "Liên kết"]]),
            width="stretch",
            hide_index=True,
            column_config={"Liên kết": st.column_config.LinkColumn("Bài viết")},
        )
        st.caption(
            "Điểm tin là phân loại định lượng từ tiêu đề/tóm tắt và độ mới; cần mở bài gốc để kiểm chứng. "
            "Tin tức chỉ là lớp bối cảnh rủi ro, không tự tạo lệnh mua/bán."
        )

with st.expander(f"◈ {vt(LANG, 'title')}", expanded=False):
    refresh_valuation = st.button(f"↻ {vt(LANG, 'refresh')}", key="refresh_equity_valuation")
    with st.spinner(vt(LANG, "loading")):
        valuation_context = load_valuation(symbol, refresh=bool(refresh_valuation or refresh))
    result = attach_valuation(result, valuation_context)
    render_valuation(result, LANG, UI_LIGHT)

strategy_plan = result.get("strategy_plan", {})
with st.expander(f"🎯 {tr(LANG, 'strategy_plan')}", expanded=False):
    with st.container(key="strategy_plan_summary"):
        s1, s2 = st.columns([1.2, 2.8])
        with s1:
            st.markdown(f"**{tr(LANG,'strategy')}:** `{display_code(strategy_plan.get('strategy', 'NO_TRADE'), STRATEGY_LABELS)}`")
            st.markdown(f"**{tr(LANG,'status')}:** `{strategy_plan.get('status', 'NO_PLAN')}`")
        with s2:
            st.write(strategy_plan.get("note", "") if LANG == "vi" else tr(LANG, "strategy_note"))

    level_labels = LEVEL_LABELS[LANG]
    levels = [
        {tr(LANG,"parameters"): label, tr(LANG,"value"): strategy_plan[key]}
        for key, label in level_labels.items()
        if strategy_plan.get(key) is not None
    ]
    if levels:
        with st.container(key="strategy_plan_levels"):
            if UI_LIGHT:
                st.table(themed_dataframe(pd.DataFrame(levels)))
            else:
                desk_dataframe(themed_dataframe(pd.DataFrame(levels)), width="stretch", hide_index=True)
    if strategy_plan.get("position_formula"):
        st.code(strategy_plan["position_formula"] if LANG == "vi" else tr(LANG, "position_formula"), language=None, wrap_lines=True)
    st.caption(tr(LANG, "plan_warning"))

# Main chart + right panel
st.markdown(
    f'<div class="section-heading"><h2>{tr(LANG, "chart_structure")}</h2><span>Scroll: zoom • Drag: pan • Double-click: reset</span></div>',
    unsafe_allow_html=True,
)
chart_col, info_col = st.columns([4.8, 1.25], gap="small")

with chart_col:
    chart_source = st.segmented_control(
        tr(LANG, "chart_source"),
        ["TradingView", tr(LANG, "system_analysis")],
        default=tr(LANG, "system_analysis"),
    )

    if chart_source == "TradingView":
        tradingview_chart(symbol, tf, exchange_by_symbol.get(symbol, "HOSE"))
        st.caption(
            "Biểu đồ do TradingView cung cấp. Marker Wyckoff và score riêng được hiển thị ở panel bên phải."
        )
        wy = analyze_wyckoff(x)
        events = wyckoff_events(x)
    else:
        internal_engine = st.segmented_control(
            tr(LANG, "internal_engine"),
            ["TradingView Lightweight", tr(LANG, "fallback")],
            default="TradingView Lightweight",
        )
        ma_bar = st.columns(6)
        with ma_bar[0]:
            show20 = st.checkbox("MA20", True)
        with ma_bar[1]:
            show50 = st.checkbox("MA50", True)
        with ma_bar[2]:
            show100 = st.checkbox("MA100", True)
        with ma_bar[3]:
            show200 = st.checkbox("MA200", True)
        with ma_bar[4]:
            show_wyckoff_structure = st.checkbox("Wyckoff 2.0", True)
        with ma_bar[5]:
            st.caption(tr(LANG, "candles", count=len(x), period=period(LANG, tf)))

        wy = analyze_wyckoff(x)
        events = wyckoff_events(x)
        if internal_engine == "TradingView Lightweight":
            lightweight_system_chart(
                x,
                tf,
                show_ma20=show20,
                show_ma50=show50,
                show_ma100=show100,
                show_ma200=show200,
                show_wyckoff_structure=show_wyckoff_structure,
            )
        else:
            fig, wy, events = make_chart(
                x,
                tf,
                show_ma20=show20,
                show_ma50=show50,
                show_ma100=show100,
                show_ma200=show200,
            )
            st.plotly_chart(
                fig,
                width="stretch",
                config={
                    "displaylogo": False,
                    "scrollZoom": True,
                    "doubleClick": "reset",
                },
            )

with info_col:
    st.markdown('<div class="tv-card-title">Multi-timeframe</div>', unsafe_allow_html=True)

    for t in TF_ORDER:
        rr = result["timeframes"].get(t, {})
        sig = rr.get("signal", "—")
        st.markdown(
            f"""
            <div class="tv-card" style="margin-bottom:6px">
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <b>{t}</b>
                    {signal_badge(sig)}
                </div>
                <div class="tv-small" style="margin-top:7px">
                    {tr(LANG,'score_conf',score=fmt(rr.get('signal_score'),1),confidence=rr.get('confidence',0))}<br>
                    {rr.get('ma_regime','—')} • RSI {fmt(rr.get('rsi14'),1)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.popover(f"ⓘ {t} · {sig}", width="stretch"):
            st.markdown(f"**{sig}**")
            st.write(signal_explanation(sig))
            st.caption(
                tr(LANG, "score_conf", score=fmt(rr.get('signal_score'), 1), confidence=rr.get('confidence', 0)) + " • " + period(LANG, t)
            )

    st.markdown('<div class="tv-card-title" style="margin-top:10px">Wyckoff</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="tv-card wyckoff-summary-card">
          <span class="tv-pill">{wy.get('phase','—')}</span>
          <span class="tv-pill">{wy.get('event','NONE')}</span><br>
          <div class="tv-small" style="margin-top:8px">
            Support: <b>{fmt(wy.get('support'))}</b><br>
            Resistance: <b>{fmt(wy.get('resistance'))}</b><br>
            Range Low: <b>{fmt(wy.get('range_low'))}</b><br>
            Range High: <b>{fmt(wy.get('range_high'))}</b>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption(tr(LANG, "click_help"))
    current_status = [
        (wy.get("event", "NONE"), WYCKOFF_EVENT_HELP),
        (wy.get("phase", "TRADING_RANGE"), WYCKOFF_PHASE_HELP),
        (wy.get("bias", "NEUTRAL"), WYCKOFF_BIAS_HELP),
    ]
    # The chart-side rail is narrow: full-width controls avoid vertical letters.
    for code, descriptions in current_status:
        with st.popover(code, width="stretch"):
            st.markdown(descriptions.get(code, "Chưa có mô tả."))

    reasons = rtf.get("reasons", [])
    if reasons:
        st.caption(" • ".join(reasons))

# Bottom tabs
st.markdown(
    f'<div class="section-heading deep-data-heading"><h2>{tr(LANG, "deep_data")}</h2><span>Multi-timeframe • OHLC • Market scanner</span></div>',
    unsafe_allow_html=True,
)
account_mode_tab_label = tr(LANG,"paper_account_tab") if SYSTEM_MODE == "PAPER" else tr(LANG,"live_account_tab")
# The watcher is independent from tab selection and survives normal Streamlit
# reruns until the user explicitly acknowledges the filled order.
if not st.session_state.get("push_notification_test_pending"):
    # Do not let the one-second alert fragment replace its element tree while
    # Streamlit is mounting the notification-test dialog.
    watch_trade_fill_alert()

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
    f"◉ {tr(LANG,'multi_overview')}", f"≋ {tr(LANG,'ohlc_indicators')}",
    "⌁ Chỉ số VN", f"⌕ {tr(LANG,'market_filter')}", f"◆ {tr(LANG,'futures_desk')}",
    f"◫ {account_mode_tab_label}", f"✓ {tr(LANG,'validation')}",
    f"✦ {tr(LANG,'ai_analyst')}", f"▣ {tr(LANG,'algorithm_tab')}",
    f"⇩ {tr(LANG,'download_data')}",
])

with tab10:
    render_data_download_panel(LANG, "main_download")

with tab1:
    st.caption(tr(LANG, "table_help"))
    interactive_timeframe_table(result)

with tab2:
    desk_dataframe(
        themed_dataframe(x[
            [
                c for c in [
                    "time", "open", "high", "low", "close", "volume",
                    "ma20", "ma50", "ma100", "ma200", "rsi14", "rvol",
                    "atr14", "atr_pct", "roc20", "volatility20"
                ]
                if c in x.columns
            ]
        ]
        .tail(120)
        .sort_values("time", ascending=False)),
        width="stretch",
        hide_index=True,
    )

    if not events.empty:
        st.markdown("**Wyckoff events**")
        desk_dataframe(
            themed_dataframe(events.sort_values("time", ascending=False)),
            width="stretch",
            hide_index=True,
        )


with tab3:
    st.markdown("### Chỉ số thị trường · Phân tích đa khung và kịch bản điểm số")
    index_controls = st.columns([1, 1, 1, 1.5])
    with index_controls[0]:
        index_symbol = st.selectbox("Chỉ số", ["VNINDEX", "VN30", "VN100"],
                                    key="market_index_symbol")
    with index_controls[1]:
        index_tf = st.segmented_control("Khung biểu đồ", TF_ORDER, default="1D",
                                        key="vnindex_chart_tf", width="stretch") or "1D"
    with index_controls[2]:
        index_horizon = st.selectbox("Thời hạn kịch bản", [5, 10, 20, 40, 60], index=2,
                                     format_func=lambda value: f"{value} phiên")
    with index_controls[3]:
        # st.button has no field label, so reserve the same label row used by
        # selectbox/segmented_control to keep all controls on one baseline.
        st.markdown("<div class='index-refresh-label'>Cập nhật dữ liệu</div>", unsafe_allow_html=True)
        refresh_index = st.button("↻ Cập nhật chỉ số và phân tích", width="stretch",
                                  key="index_refresh_button")
        if "vnindex_refresh_token" not in st.session_state:
            st.session_state.vnindex_refresh_token = 0
        if refresh_index:
            st.session_state.vnindex_refresh_token += 1
    try:
        with st.spinner(f"Đang tổng hợp {index_symbol} và độ rộng thị trường..."):
            index_history, index_source = load_vnindex_cached(index_symbol, st.session_state.vnindex_refresh_token)
            index_result = analyze_vnindex(index_history, load_hose_breadth(PROCESSED_DIR, index_symbol),
                                           index_horizon, symbol=index_symbol)
        if index_result.get("status") != "OK":
            st.warning(f"{index_symbol} chưa đủ lịch sử: {index_result.get('rows', 0)} nến.")
        else:
            levels, weights = index_result["levels"], index_result["scenario_weights"]
            realtime_index_panel(index_symbol, index_result["close"])
            c1, c2, c3 = st.columns(3)
            c1.metric("Điểm kỹ thuật", f"{index_result['index_score']:+.1f}")
            c2.metric("Kỹ thuật + độ rộng", f"{index_result['combined_score']:+.1f}")
            c3.metric("Mẫu độ rộng", f"{index_result['breadth']['sample']} mã")
            chart_choice = st.radio("Nguồn biểu đồ", ["TradingView", "Phân tích hệ thống"],
                                    horizontal=True, key="vnindex_chart_source")
            if chart_choice == "TradingView":
                tradingview_chart(index_symbol, index_tf, exchange="HOSE", height=720)
                st.caption(f"TradingView cung cấp HOSE:{index_symbol}; vùng điểm do VnStockDesk tính từ VNStock và kết quả quét.")
            else:
                ma_cols = st.columns(5)
                show_ma20 = ma_cols[0].checkbox("MA20", True, key="idx_ma20")
                show_ma50 = ma_cols[1].checkbox("MA50", True, key="idx_ma50")
                show_ma100 = ma_cols[2].checkbox("MA100", True, key="idx_ma100")
                show_ma200 = ma_cols[3].checkbox("MA200", True, key="idx_ma200")
                show_wy = ma_cols[4].checkbox("Wyckoff/Fibonacci", True, key="idx_wy")
                index_chart_frame = add_indicators(resample_ohlcv(index_history, index_tf))
                lightweight_system_chart(index_chart_frame, index_tf, show_ma20, show_ma50,
                                         show_ma100, show_ma200, show_wy, height=720)

            tf_result = index_result["timeframes"].get(index_tf, {})
            index_indicator_frame = add_indicators(resample_ohlcv(index_history, index_tf))
            fib = fibonacci_analysis(index_indicator_frame, min(120, len(index_indicator_frame)))
            st.markdown(f"#### Chỉ báo kỹ thuật · {index_symbol} · {index_tf}")
            i1, i2, i3, i4, i5 = st.columns(5)
            i1.metric("Signal · Score", f"{tf_result.get('signal', '—')} · {tf_result.get('signal_score', 0):+}")
            i2.metric("RSI14 · RVOL", f"{fmt(tf_result.get('rsi14'), 1)} · {fmt(tf_result.get('rvol'), 2)}x")
            i3.metric("MACD · Histogram", f"{fmt(tf_result.get('macd'), 3)} · {fmt(tf_result.get('macd_hist'), 3)}")
            i4.metric("ADX14 · +DI / −DI", f"{fmt(tf_result.get('adx14'), 1)} · {fmt(tf_result.get('plus_di14'), 1)} / {fmt(tf_result.get('minus_di14'), 1)}")
            i5.metric("Confidence", f"{tf_result.get('confidence', 0)}%", delta=tf_result.get("obv_bias", "—"))
            j1, j2, j3, j4 = st.columns(4)
            j1.metric("MA regime", tf_result.get("ma_regime", "—"))
            j2.metric("Wyckoff", f"{tf_result.get('wyckoff_phase', '—')} · {tf_result.get('wyckoff_event', '—')}")
            j3.metric("Hỗ trợ / Kháng cự", f"{fmt(tf_result.get('support'))} / {fmt(tf_result.get('resistance'))}")
            j4.metric("Fibonacci", f"{fib.get('direction', '—')} · {fib.get('nearest_ratio', '—')}",
                      delta=f"Mức gần nhất {fmt(fib.get('nearest_level'))}")
            with st.expander("Chi tiết OHLC, chỉ báo, Wyckoff và Fibonacci"):
                desk_dataframe(themed_dataframe(detail_table(index_history, index_indicator_frame,
                                                              index_tf, tf_result)),
                               width="stretch", hide_index=True)
            st.markdown(f"#### Kịch bản {index_horizon} phiên")
            bull, sideways, bear = st.columns(3)
            with bull:
                st.success(f"**Tăng · trọng số {weights['bull']:.1f}%**\n\nKích hoạt: **{fmt(levels['bull_trigger'])}** điểm  \nMục tiêu: **{fmt(levels['bull_target'])}** điểm  \nMở rộng: **{fmt(levels['bull_extended'])}** điểm")
            with sideways:
                st.info(f"**Đi ngang/chuyển pha · trọng số {weights['range']:.1f}%**\n\nTâm phân phối: **{fmt(levels['range_mid'])}** điểm  \nChờ phá hỗ trợ hoặc kháng cự.")
            with bear:
                st.error(f"**Giảm · trọng số {weights['bear']:.1f}%**\n\nKích hoạt: **{fmt(levels['bear_trigger'])}** điểm  \nMục tiêu: **{fmt(levels['bear_target'])}** điểm  \nCực đoan lịch sử: **{fmt(levels['extreme_downside'])}** điểm")
            breadth = index_result["breadth"]
            b1, b2, b3 = st.columns(3)
            b1.metric("Mã tích cực", "—" if breadth["bullish_pct"] is None else f"{breadth['bullish_pct']:.1f}%")
            b2.metric("Mã trung tính", "—" if breadth["neutral_pct"] is None else f"{breadth['neutral_pct']:.1f}%")
            b3.metric("Mã tiêu cực", "—" if breadth["bearish_pct"] is None else f"{breadth['bearish_pct']:.1f}%")
            dist = index_result["historical_distribution_pct"]
            st.caption(f"Phân phối {index_horizon} phiên · P05 {dist['p05']:+.2f}% • P25 {dist['p25']:+.2f}% • Trung vị {dist['median']:+.2f}% • P75 {dist['p75']:+.2f}% • P95 {dist['p95']:+.2f}% • {dist['observations']} quan sát hoàn tất.")
            if index_result["warnings"]:
                st.warning("Độ rộng chưa đầy đủ: " + ", ".join(index_result["warnings"]) + ". Không nâng độ tin cậy bằng dữ liệu thiếu.")
            with st.expander("Phương pháp và giới hạn"):
                st.write(index_result["method"])
                st.write(f"Nguồn OHLCV: {index_source}. Mức cực đoan là phân vị lịch sử, không phải dự báo chắc chắn sẽ rơi thẳng đến đó.")
    except Exception as index_exc:
        st.error("Không tải hoặc phân tích được VNINDEX.")
        st.code(str(index_exc))


with tab4:
    scan_controls, scan_note = st.columns([1, 3])
    with scan_controls:
        with st.popover(f"▶ Quét {MARKET_SCOPES[market_scope]}", width="stretch"):
            scan_mode = st.selectbox("Số lượng", ["Toàn bộ phạm vi", "100 mã đầu", "10 mã kiểm thử"])
            force_scan = st.checkbox("Tải lại toàn bộ lịch sử", value=False)
            st.caption("Có checkpoint tự động mỗi 10 mã. Toàn thị trường có thể mất nhiều giờ với gói Community.")
            if st.button("Bắt đầu quét", type="primary", width="stretch"):
                from scan import main as run_scan
                scan_limit = 10 if scan_mode.startswith("10 mã") else 100 if scan_mode.startswith("100 mã") else None
                with st.spinner("Đang tải dữ liệu và phân tích..."):
                    run_scan(limit=scan_limit, refresh=force_scan, scope=market_scope, resume=True)
                st.cache_data.clear()
                st.success("Quét hoàn tất.")
                st.rerun()
    with scan_note:
        st.caption(f"Đang xem kết quả riêng của {MARKET_SCOPES[market_scope]}; các phạm vi không ghi đè lẫn nhau.")

    if scan_path.exists():
        scan = pd.read_csv(scan_path)

        bullish = int((scan["consensus_score"] >= 25).sum())
        bearish = int((scan["consensus_score"] <= -25).sum())
        neutral = len(scan) - bullish - bearish
        breadth_score = 0 if scan.empty else float(scan["consensus_score"].mean())
        b1, b2, b3, b4 = st.columns(4)
        b1.metric(f"Độ rộng {MARKET_SCOPES[market_scope]}", f"{breadth_score:+.1f}")
        b2.metric("Tích cực", bullish)
        b3.metric("Trung tính", neutral)
        b4.metric("Tiêu cực", bearish)

        if "decision_grade" in scan.columns:
            grade_counts = scan["decision_grade"].value_counts()
            st.caption(
                "Chất lượng bằng chứng · "
                + " • ".join(f"Hạng {grade}: {int(grade_counts.get(grade, 0))}" for grade in ["A", "B", "C", "D"])
            )

        if scan_meta_path.exists():
            try:
                meta = json.loads(scan_meta_path.read_text(encoding="utf-8"))
                st.caption(
                    f"Cập nhật {meta.get('rescored_at') or meta.get('generated_at', '—')} • "
                    f"{meta.get('analyzed', len(scan))}/{meta.get('universe', len(scan))} mã • "
                    f"{meta.get('errors', 0)} lỗi • {meta.get('engine_version', 'ENGINE V1')}"
                )
            except (OSError, ValueError):
                pass

        left, middle, right = st.columns([1, 1, 1])

        with left:
            sig_filter = st.multiselect(
                "Signal filter",
                sorted(scan["final_signal"].dropna().unique().tolist()),
                default=[],
            )
            if "data_quality" in scan.columns:
                quality_filter = st.multiselect(
                    "Chất lượng dữ liệu",
                    ["GOOD", "WATCH", "REJECT"],
                    default=["GOOD"],
                )
            else:
                quality_filter = []
            if "decision_grade" in scan.columns:
                grade_filter = st.multiselect("Hạng bằng chứng", ["A", "B", "C", "D"], default=[])
            else:
                grade_filter = []

        with middle:
            min_score = st.slider(
                "Min consensus",
                min_value=-100,
                max_value=100,
                value=-100,
                step=5,
            )

        with right:
            min_confidence = st.slider(
                "Min confidence",
                min_value=0,
                max_value=100,
                value=0,
                step=10,
            )

        view = scan.copy()

        if sig_filter:
            view = view[
                view["final_signal"].isin(sig_filter)
            ]
        if quality_filter and "data_quality" in view.columns:
            view = view[view["data_quality"].isin(quality_filter)]
        if grade_filter and "decision_grade" in view.columns:
            view = view[view["decision_grade"].isin(grade_filter)]

        view = view[
            view["consensus_score"] >= min_score
        ]
        if "confidence" in view.columns:
            view = view[view["confidence"] >= min_confidence]

        cols = [
            c for c in [
                "symbol", "system_action", "decision_grade", "market_regime", "final_signal", "consensus_score", "confidence",
                "timeframe_alignment", "conflict_level", "decision_drivers",
                "news_adjusted_score", "news_score", "news_sentiment", "news_count_30d",
                "valuation_pe", "valuation_pb", "valuation_roe", "valuation_profit_growth", "valuation_debt_equity",
                "valuation_status", "valuation_conclusion", "valuation_period", "valuation_source", "valuation_fetched_at", "valuation_warnings",
                "strategic_score", "tactical_score", "risk_flags",
                "strategy", "strategy_status", "entry_low", "entry_high",
                "trigger", "stop_loss", "target_1", "target_2", "reward_risk_1",
                "data_age_days",
                "data_quality", "recent_nonzero_volume_ratio", "median_turnover_20d_vnd",
                "1d_signal", "1w_signal", "1m_signal", "1y_signal",
                "1d_signal_score", "1d_rsi14", "1d_atr_pct",
                "1d_ma_regime", "1d_wyckoff_phase",
            ]
            if c in view.columns
        ]

        desk_dataframe(
            themed_dataframe(view[cols].sort_values("consensus_score", ascending=False)),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("Chưa có file scan. Chạy run_scan.command trước.")

with tab5:
    if SYSTEM_MODE == "LIVE":
        st.markdown(f"### ◆ {tr(LANG, 'futures_title')} · LIVE")
        live_contracts, live_contract_meta = load_futures_contracts_cached(0)
        live_contract_map = {item["symbol"]: item for item in live_contracts}
        live_selected_symbol = st.selectbox(
            tr(LANG, "fut_contract"), list(live_contract_map),
            format_func=lambda code: live_contract_map[code]["label"],
            key="selected_futures_contract", help=tr(LANG, "fut_contract_help"),
        )
        realtime_futures_panel(live_selected_symbol)
        st.warning(tr(LANG, "live_readonly"))
        with st.spinner(f"{live_selected_symbol} · 15M · 1H · 1D..."):
            live_frames, live_meta = load_vn30f1m_cached(0, live_selected_symbol)
        live_result = analyze_vn30f1m(live_frames, symbol=live_selected_symbol)
        if live_result.get("status") != "OK":
            st.error(tr(LANG, "fut_insufficient", symbol=live_selected_symbol))
        else:
            lm1,lm2,lm3,lm4 = st.columns(4)
            lm1.metric(live_selected_symbol, f"{float(live_result['price']):,.1f}")
            lm2.metric(tr(LANG,"futures_trend"), live_result.get("regime","—"), delta=f"{live_result.get('score',0):+.1f}")
            lm3.metric(tr(LANG,"futures_support"), f"{live_result.get('support',0):,.1f}")
            lm4.metric(tr(LANG,"futures_resistance"), f"{live_result.get('resistance',0):,.1f}")
            st.markdown(f"**{tr(LANG,'futures_plan')} · {live_result.get('action','WAIT_CONFIRMATION')}**")
            st.caption(f"Confidence {live_result.get('confidence',0)}% · Alignment {live_result.get('alignment',0)}% · LIVE READ-ONLY")
            live_chart_tf = st.selectbox(tr(LANG,"fut_chart_tf"), FUTURES_CHART_TIMEFRAMES, key="live_futures_chart_timeframe")
            live_analysis = analyze_futures_chart_frame(live_frames, live_chart_tf)
            live_chart_frame = live_analysis.get("data", pd.DataFrame()).tail(240)
            st.caption(f"{live_chart_tf} · {len(live_chart_frame)} nến thực · {live_analysis['status']} · Kế hoạch giao dịch đa khung 15M/1H/1D được giữ riêng.")
            if not live_chart_frame.empty:
                lightweight_futures_execution_chart(
                    live_chart_frame, live_analysis,
                    {"side":"FLAT","quantity":0,"equity_vnd":0,"unrealized_pnl_vnd":0},
                    {**live_result.get("plan",{}),"side":live_result.get("action")},
                    symbol=live_selected_symbol,
                )
            st.info("LIVE chỉ hiển thị quote, biểu đồ và phân tích. Tài khoản, vị thế, P&L và BOT PAPER được ẩn hoàn toàn.")
    else:
        st.markdown(f"### ◈ {tr(LANG, 'futures_title')}")
        futures_contracts, futures_contract_meta = load_futures_contracts_cached(0)
        futures_contract_map = {item["symbol"]: item for item in futures_contracts}
        selected_futures_symbol = st.selectbox(
            tr(LANG, "fut_contract"),
            list(futures_contract_map),
            format_func=lambda code: futures_contract_map[code]["label"],
            key="selected_futures_contract",
            help=tr(LANG, "fut_contract_help"),
        )
        selected_contract_info = futures_contract_map[selected_futures_symbol]
        st.caption(
            f"{tr(LANG,'fut_source')}: {futures_contract_meta['source_label']} · "
            f"{futures_contract_meta['count']} {tr(LANG,'fut_count')} · {tr(LANG,'fut_underlying')} {selected_contract_info['underlying']} · "
            f"{tr(LANG,'fut_expiry')} {selected_contract_info['expiry']}"
        )
        realtime_futures_panel(selected_futures_symbol)
        futures_full_live = st.toggle(
            tr(LANG, "fut_heavy"), value=False,
            key="futures_full_live_enabled",
            help=tr(LANG, "fut_heavy_help"),
        )
        if futures_full_live:
            st.caption(tr(LANG, "fut_heavy_on"))
        selected_scope_label = tr(LANG, "fut_selected")
        all_scope_label = tr(LANG, "fut_all")
        futures_status = futures_bot_status(ROOT)
        futures_risk_reset = st.session_state.pop("futures_bot_risk_level_reset", None)
        if futures_risk_reset in {"LOW", "MEDIUM", "HIGH"}:
            st.session_state.futures_bot_risk_level = futures_risk_reset
        if "futures_bot_risk_applied" not in st.session_state:
            st.session_state.futures_bot_risk_applied = st.session_state.get("futures_bot_risk_level", "MEDIUM")
        if futures_status.get("running") and futures_status.get("risk_level") in {"LOW", "MEDIUM", "HIGH"}:
            st.session_state.futures_bot_risk_level = futures_status["risk_level"]
            st.session_state.futures_bot_risk_applied = futures_status["risk_level"]
        bot_scope_col, bot_cycle_col, bot_risk_col = st.columns([1.45, 1, 1.35], gap="medium", vertical_alignment="bottom")
        with bot_scope_col:
            futures_bot_scope = st.segmented_control(
                tr(LANG, "fut_scope"), [selected_scope_label, all_scope_label],
                default=selected_scope_label, key="futures_bot_scan_scope", width="stretch",
            ) or selected_scope_label
        with bot_cycle_col:
            futures_interval = st.segmented_control(
                tr(LANG,"fut_cycle"), [5,15,30], default=15,
                format_func=lambda value:f"{value}m", key="futures_bot_interval", width="stretch",
            ) or 15
        with bot_risk_col:
            futures_risk_level = st.segmented_control(
                "Quản trị rủi ro", ["LOW", "MEDIUM", "HIGH"], default="MEDIUM",
                format_func=lambda value: {"LOW":"Thấp", "MEDIUM":"Trung bình", "HIGH":"Cao"}[value],
                key="futures_bot_risk_level", width="stretch",
                disabled=bool(futures_status.get("running")),
                help="Điều chỉnh ngưỡng Confidence, đồng thuận và số hợp đồng; Stop Loss và khóa lỗ ngày luôn được giữ.",
            ) or "MEDIUM"
        futures_bot_target = selected_futures_symbol if futures_bot_scope == selected_scope_label else "ALL"
        if futures_risk_level != st.session_state.futures_bot_risk_applied and not futures_status.get("running"):
            confirm_bot_risk_and_start(
                market="futures", level=futures_risk_level, interval=int(futures_interval),
                symbol=futures_bot_target,
            )
        st.caption(tr(LANG, "fut_recommended"))
        if futures_status.get("running"):
            fhb = futures_status.get("heartbeat", {})
            st.markdown(f"<div class='bot-status bot-running'>● BOT {tr(LANG,'running').lower()} · {futures_status.get('symbol', selected_futures_symbol)}<br>{fhb.get('action','WAIT')} · {fmt(fhb.get('price'),1)}</div>", unsafe_allow_html=True)
            st.caption(fhb.get("reason", tr(LANG, "fut_monitoring")))
        else:
            st.markdown(f"<div class='bot-status bot-stopped'>○ BOT {tr(LANG,'stopped').lower()} · {selected_futures_symbol}</div>", unsafe_allow_html=True)
        fc1,fc2,fc3 = st.columns(3, gap="medium", vertical_alignment="bottom")
        with fc1:
            with st.container(key="futures_bot_start_control"):
                futures_start_requested = st.button("▶ Start", width="stretch", disabled=bool(futures_status.get("running")), key="start_futures_bot")
        if futures_start_requested:
            try:
                active_futures_risk = st.session_state.futures_bot_risk_applied
                start_futures_bot(ROOT, int(futures_interval), futures_bot_target, active_futures_risk)
                risk_name = {"LOW":"Thấp", "MEDIUM":"Trung bình", "HIGH":"Cao"}[active_futures_risk]
                st.toast(f"Đã chạy BOT PAPER · {futures_bot_scope} · Rủi ro {risk_name}")
                st.rerun()
            except (RuntimeError,ValueError,OSError) as exc: st.error(str(exc))
        with fc2:
            with st.container(key="futures_bot_stop_control"):
                futures_stop_requested = st.button("■ Stop", width="stretch", disabled=not bool(futures_status.get("running")), key="stop_futures_bot")
        if futures_stop_requested:
            try: stop_futures_bot(ROOT); st.toast(f"Đã dừng BOT {futures_status.get('symbol', selected_futures_symbol)}"); st.rerun()
            except (RuntimeError,ValueError,OSError) as exc: st.error(str(exc))
        run_futures_once = fc3.button("↻ Một chu kỳ", width="stretch", disabled=bool(futures_status.get("running")), key="run_futures_once")
        futures_refresh = st.button(f"↻ {tr(LANG, 'futures_refresh')}", key="refresh_vn30f1m")
        if run_futures_once:
            try:
                if futures_bot_target == "ALL":
                    one_cycle = futures_paper_scan_cycle(
                        ROOT, list(futures_contract_map), risk_level=st.session_state.futures_bot_risk_applied
                    )
                else:
                    one_cycle = futures_paper_cycle(
                        ROOT, symbol=selected_futures_symbol, risk_level=st.session_state.futures_bot_risk_applied
                    )
                st.session_state.futures_last_scan_report = one_cycle
                st.success(f"{one_cycle['bot_action']} · {one_cycle['reason']}")
                st.rerun()
            except (RuntimeError,ValueError,OSError) as exc: st.error(str(exc))
        last_futures_scan = st.session_state.get("futures_last_scan_report", {})
        if last_futures_scan.get("results"):
            scan_rows = [{
                "Hợp đồng":item.get("symbol"), "Giá":item.get("price"),
                "BOT action":item.get("bot_action"), "Phân tích":item.get("analysis",{}).get("action"),
                "Score":item.get("analysis",{}).get("score"), "Confidence":item.get("analysis",{}).get("confidence"),
                "Lệnh":len(item.get("orders",[])), "Lý do":item.get("reason"),
            } for item in last_futures_scan["results"]]
            with st.expander(
                f"Kết quả vòng quét gần nhất · {last_futures_scan.get('scanned',0)}/{last_futures_scan.get('total',0)} hợp đồng",
                expanded=True,
            ):
                desk_dataframe(themed_dataframe(pd.DataFrame(scan_rows)), width="stretch", hide_index=True)
        with st.spinner(f"{selected_futures_symbol} · 15M · 1H · 1D..."):
            futures_frames, futures_meta = load_vn30f1m_cached(1 if futures_refresh else 0, selected_futures_symbol)
        futures_broker = PaperFuturesBroker(STATE_DIR / f"paper_futures_{selected_futures_symbol.lower()}.json")
        latest_futures_price = None
        for future_tf in ("15M", "1H", "1D"):
            if not futures_frames.get(future_tf, pd.DataFrame()).empty:
                latest_futures_price = float(futures_frames[future_tf].iloc[-1]["close"])
                break
        selected_live_quote = st.session_state.get("realtime_futures_quotes", {}).get(selected_futures_symbol, {})
        if (
            selected_live_quote.get("status") == "OK"
            and (selected_live_quote.get("market_age_seconds") is None or float(selected_live_quote["market_age_seconds"]) <= 15)
        ):
            latest_futures_price = float(selected_live_quote["price"])
        futures_account = futures_broker.snapshot(latest_futures_price)
        futures_result = analyze_vn30f1m(
            futures_frames, account_equity_vnd=float(futures_account["equity_vnd"]),
            symbol=selected_futures_symbol,
        )
        if futures_result.get("status") != "OK":
            st.error(tr(LANG, "fut_insufficient", symbol=selected_futures_symbol))
        else:
            action_colors = {"LONG":UI_COLORS['green'], "SHORT":UI_COLORS['red'], "STAND_ASIDE":UI_COLORS['amber'], "WAIT_CONFIRMATION":UI_COLORS['blue'], "NO_TRADE":UI_COLORS['muted']}
            future_color = action_colors.get(futures_result["action"], UI_COLORS['muted'])
            f1, f2, f3, f4 = st.columns(4)
            f1.metric(selected_futures_symbol, f"{float(latest_futures_price or futures_result['price']):,.1f}")
            f2.metric(tr(LANG, "futures_trend"), futures_result["regime"], delta=f"{futures_result['score']:+.1f}")
            f3.metric(tr(LANG, "futures_support"), f"{futures_result['support']:,.1f}")
            f4.metric(tr(LANG, "futures_resistance"), f"{futures_result['resistance']:,.1f}")
            st.markdown(
                f"<div class='decision-hero'><div class='tv-card-title'>{tr(LANG,'futures_plan')}</div>"
                f"<div class='tv-big' style='color:{future_color}'>{futures_result['action'].replace('_',' ')}</div>"
                f"<div class='tv-small'>Score {futures_result['score']:+.1f} • Confidence {futures_result['confidence']}% • Alignment {futures_result['alignment']}%</div></div>",
                unsafe_allow_html=True,
            )
    
            # The contract selector above is analysis-only. Position management is
            # driven exclusively by ledgers that actually contain an open position.
            reference_futures_broker = futures_broker
            reference_futures_account = futures_account
            reference_futures_price = float(latest_futures_price or futures_result["price"])
            open_futures_positions = active_futures_paper_positions()
            managed_futures_symbol = selected_futures_symbol
            managed_futures_price = reference_futures_price
            if open_futures_positions:
                active_position_symbols = list(open_futures_positions)
                previous_managed = st.session_state.get("managed_futures_position")
                if previous_managed not in open_futures_positions:
                    st.session_state.managed_futures_position = active_position_symbols[0]
    
                def active_position_label(code: str) -> str:
                    position = open_futures_positions[code]
                    side = str(position["side"])
                    quantity = int(position["quantity"])
                    entry = float(position.get("entry_price") or 0)
                    last = float(position.get("last_price") or entry)
                    direction = 1 if side == "LONG" else -1
                    pnl_vnd = direction * quantity * (last - entry) * float(
                        reference_futures_broker.config.contract_multiplier_vnd
                    )
                    pnl_arrow = "▲" if pnl_vnd > 0 else "▼" if pnl_vnd < 0 else "◆"
                    return f"{code} · {side} · {quantity} HĐ · {pnl_arrow} {pnl_vnd:+,.0f} ₫"
    
                managed_futures_symbol = st.selectbox(
                    tr(LANG, "fut_active"), active_position_symbols,
                    key="managed_futures_position",
                    format_func=active_position_label,
                    help="Chỉ hiển thị các hợp đồng đang có vị thế PAPER LONG hoặc SHORT.",
                )
                futures_broker = PaperFuturesBroker(open_futures_positions[managed_futures_symbol]["path"])
                managed_quote = load_futures_quote_cached(managed_futures_symbol)
                if (
                    managed_quote.get("status") == "OK"
                    and (
                        managed_quote.get("market_age_seconds") is None
                        or float(managed_quote["market_age_seconds"]) <= 15
                    )
                ):
                    managed_futures_price = float(managed_quote["price"])
                else:
                    managed_futures_price = float(
                        open_futures_positions[managed_futures_symbol].get("last_price")
                        or open_futures_positions[managed_futures_symbol].get("entry_price")
                    )
                futures_account = futures_broker.snapshot(managed_futures_price)
            else:
                st.info(tr(LANG, "fut_no_position"))
    
            future_plan = futures_result["plan"]
            active_futures_position = futures_account.get("side") in {"LONG", "SHORT"} and int(futures_account.get("quantity", 0)) > 0
            model_max_contracts = int(futures_result.get("position_size",{}).get("contracts",0))
            if active_futures_position:
                selected_futures_contracts = int(futures_account.get("quantity",0))
                st.number_input(
                    tr(LANG,"fut_active_qty"), min_value=selected_futures_contracts,
                    max_value=selected_futures_contracts, value=selected_futures_contracts,
                    step=1, key="active_futures_contracts_display", disabled=True,
                    help="Đây là khối lượng vị thế hiện tại. Hãy đóng vị thế trước khi chọn số lượng cho lệnh mới.",
                )
            else:
                contracts_allowed = model_max_contracts > 0 and futures_result["action"] in {"LONG","SHORT"}
                if contracts_allowed:
                    current_contract_choice = int(st.session_state.get("manual_futures_contracts", 1))
                    if not 1 <= current_contract_choice <= model_max_contracts:
                        st.session_state.manual_futures_contracts = 1
                    selected_futures_contracts = int(st.number_input(
                        tr(LANG,"fut_new_qty"), min_value=1, max_value=model_max_contracts,
                        value=1, step=1, key="manual_futures_contracts",
                        help="Người dùng chủ động chọn số hợp đồng. Giới hạn trên do vốn, ký quỹ và rủi ro mỗi lệnh quyết định.",
                    ))
                else:
                    st.number_input(
                        tr(LANG,"fut_new_qty"), min_value=0, max_value=0, value=0,
                        step=1, key="manual_futures_contracts_locked", disabled=True,
                        help="Chưa đủ điều kiện LONG/SHORT hoặc giới hạn rủi ro hiện cho phép 0 hợp đồng.",
                    )
                    selected_futures_contracts = 0
            execution_side = futures_account["side"] if active_futures_position else futures_result["action"]
            execution_entry = float(futures_account["entry_price"]) if active_futures_position else future_plan.get("trigger")
            execution_stop = futures_account.get("stop_loss") if active_futures_position else future_plan.get("stop_loss")
            execution_tp1 = futures_account.get("target") if active_futures_position else future_plan.get("target_1")
            execution_tp2 = futures_account.get("target_2") if active_futures_position else future_plan.get("target_2")
            direction_factor = 1 if execution_side == "LONG" else -1 if execution_side == "SHORT" else 0
            mark_price = float(managed_futures_price)
            open_points = direction_factor * (mark_price - float(execution_entry)) if execution_entry is not None else None
            risk_points = abs(float(execution_entry) - float(execution_stop)) if execution_entry is not None and execution_stop is not None else None
            reward_points = direction_factor * (float(execution_tp1) - float(execution_entry)) if execution_entry is not None and execution_tp1 is not None else None
            reward_risk = reward_points / risk_points if reward_points is not None and risk_points and risk_points > 0 else None
            execution_label = tr(LANG,"fut_active") if active_futures_position else tr(LANG,"fut_pending")
            position_heading_symbol = f"{managed_futures_symbol} · " if active_futures_position else ""
            st.markdown(f"**◆ {position_heading_symbol}{execution_label} · {execution_side.replace('_',' ')}**")
            ex1, ex2, ex3, ex4, ex5, ex6 = st.columns(6)
            ex1.metric(tr(LANG,"fut_price"), f"{mark_price:,.1f}")
            ex2.metric("Entry", fmt(execution_entry,1))
            ex3.metric("P&L", f"{open_points:+.1f} pts" if open_points is not None else "—",
                       delta=f"{float(futures_account.get('unrealized_pnl_vnd',0)):+,.0f} ₫" if active_futures_position else None)
            ex4.metric("Stop Loss", fmt(execution_stop,1), delta=f"-{risk_points:.1f} pts" if risk_points is not None else None)
            ex5.metric("Take Profit TP1", fmt(execution_tp1,1), delta=f"+{reward_points:.1f} pts" if reward_points is not None else None)
            ex6.metric("TP2 · R:R", f"{fmt(execution_tp2,1)} · {reward_risk:.2f}R" if reward_risk is not None else fmt(execution_tp2,1))
            execution_quantity = selected_futures_contracts
            contract_multiplier = float(futures_result.get("config",{}).get("contract_multiplier_vnd",100_000))
            margin_ratio = float(futures_result.get("config",{}).get("initial_margin_ratio",.17))
            estimated_margin = execution_quantity * mark_price * contract_multiplier * margin_ratio
            stop_value = risk_points * execution_quantity * contract_multiplier if risk_points is not None else None
            tp1_value = reward_points * execution_quantity * contract_multiplier if reward_points is not None else None
            tp2_points = direction_factor * (float(execution_tp2) - float(execution_entry)) if execution_entry is not None and execution_tp2 is not None else None
            tp2_value = tp2_points * execution_quantity * contract_multiplier if tp2_points is not None else None
            money1, money2, money3, money4, money5, money6 = st.columns(6)
            money1.metric(tr(LANG,"fut_quantity"), f"{execution_quantity} HĐ")
            money2.metric(tr(LANG,"fut_cash"), f"{float(futures_account.get('balance_vnd',0)):,.0f} ₫")
            money3.metric("Equity", f"{float(futures_account.get('equity_vnd',0)):,.0f} ₫")
            money4.metric(tr(LANG,"fut_margin"), f"{estimated_margin:,.0f} ₫")
            money5.metric(tr(LANG,"fut_risk"), f"-{stop_value:,.0f} ₫" if stop_value is not None else "—")
            money6.metric(tr(LANG,"fut_profit"), f"+{tp1_value:,.0f} / +{tp2_value:,.0f} ₫" if tp1_value is not None and tp2_value is not None else "—")
            # Contract value must follow the latest market mark, not a planned/old entry.
            live_contract_price = mark_price
            notional_per_contract = live_contract_price * contract_multiplier
            total_notional = notional_per_contract * execution_quantity
            margin_per_contract = notional_per_contract * margin_ratio
            live_meta = futures_meta.get("15M", {}) if managed_futures_symbol == selected_futures_symbol else {}
            live_provider = managed_quote.get("provider") if open_futures_positions else live_meta.get("provider")
            live_source_label = (
                managed_quote.get("source_label") if open_futures_positions else None
            ) or live_meta.get("source_label") or live_meta.get("source", "N/A")
            live_updated_at = (
                managed_quote.get("market_time") or managed_quote.get("received_at")
                if open_futures_positions else live_meta.get("latest")
            )
            try:
                live_updated_label = pd.Timestamp(live_updated_at).strftime("%d/%m/%Y %H:%M")
            except (TypeError, ValueError):
                live_updated_label = tr(LANG,"fut_unknown")
            st.markdown(f"**{tr(LANG,'fut_value_detail')}**")
            value1, value2, value3, value4, value5, value6 = st.columns(6)
            value1.metric(tr(LANG,"fut_live_price",symbol=managed_futures_symbol), f"{live_contract_price:,.1f} pts")
            value2.metric(tr(LANG,"fut_multiplier"), f"{contract_multiplier:,.0f} ₫/pt")
            value3.metric(tr(LANG,"fut_one_value"), f"{notional_per_contract:,.0f} ₫")
            value4.metric(tr(LANG,"fut_notional",quantity=execution_quantity), f"{total_notional:,.0f} ₫")
            value5.metric(tr(LANG,"fut_margin_contract"), f"{margin_per_contract:,.0f} ₫", delta=f"{margin_ratio:.0%}")
            value6.metric(tr(LANG,"fut_source_update"), live_source_label, delta=live_updated_label)
            st.caption(
                f"Cách tính: {live_contract_price:,.1f} điểm × {contract_multiplier:,.0f} ₫ = "
                f"{notional_per_contract:,.0f} ₫/hợp đồng. Tổng danh nghĩa {execution_quantity} HĐ = "
                f"{total_notional:,.0f} ₫; ký quỹ ước tính = {estimated_margin:,.0f} ₫. "
                "P&L thay đổi 100.000 ₫ cho mỗi 1 điểm trên mỗi hợp đồng, chưa trừ phí."
            )
            if live_provider != "VCI":
                st.warning(
                    f"Nguồn VCI hiện không khả dụng; hệ thống đang hiển thị {live_source_label}. "
                    "Nguồn dự phòng luôn được công khai, không gắn nhãn VCI sai nguồn."
                )
            st.markdown(
                "<div class='tv-small'>Quy cách hợp đồng đối chiếu theo "
                "<a href='https://www.ssi.com.vn/khach-hang-ca-nhan/quy-dinh-giao-dich/"
                "quy-dinh-giao-dich-chung-khoan-phai-sinh' target='_blank'>SSI</a>. "
                f"Giá thị trường ưu tiên VCI qua VNStock; nút <b>Cập nhật {selected_futures_symbol}</b> buộc lấy dữ liệu mới.</div>",
                unsafe_allow_html=True,
            )
            if active_futures_position:
                position_state_color = "success" if (open_points or 0) >= 0 else "warning"
                getattr(st, position_state_color)(
                    f"{execution_side} {int(futures_account['quantity'])} HĐ · Entry {execution_entry:,.1f} · "
                    f"Mark {mark_price:,.1f} · P&L {open_points:+.1f} điểm / {float(futures_account.get('unrealized_pnl_vnd',0)):+,.0f} ₫"
                )
            close_position_col, position_note_col = st.columns([1, 3], gap="medium")
            with close_position_col:
                with st.popover(
                    f"■ {tr(LANG,'fut_close')}",
                    disabled=not active_futures_position,
                    use_container_width=True,
                ):
                    if active_futures_position:
                        st.markdown(
                            f"**{execution_side} · {int(futures_account['quantity'])} HĐ**  \n"
                            f"Entry `{execution_entry:,.1f}` · Giá đóng dự kiến `{mark_price:,.1f}`  \n"
                            f"P&L tạm tính `{open_points:+.1f} điểm` / `{float(futures_account.get('unrealized_pnl_vnd',0)):+,.0f} ₫`"
                        )
                        if futures_status.get("running"):
                            st.warning("BOT Futures đang chạy. Xác nhận dưới đây sẽ dừng BOT trước khi đóng vị thế.")
                        confirm_futures_close = st.checkbox(
                            tr(LANG,"fut_confirm"),
                            key="confirm_close_futures_position",
                        )
                        if st.button(
                            tr(LANG,"fut_confirm_all"),
                            type="primary", width="stretch",
                            disabled=not confirm_futures_close,
                            key="confirm_close_all_futures",
                        ):
                            try:
                                if futures_status.get("running"):
                                    stop_futures_bot(ROOT)
                                closing_broker = PaperFuturesBroker(
                                    STATE_DIR / f"paper_futures_{managed_futures_symbol.lower()}.json"
                                )
                                closing_snapshot = closing_broker.snapshot(mark_price)
                                if closing_snapshot.get("side") == "FLAT":
                                    st.info("Vị thế đã được đóng trước đó.")
                                else:
                                    close_order = closing_broker.close(mark_price, "MANUAL_DASHBOARD_CLOSE_ALL")
                                    st.toast(
                                        f"Đã đóng {close_order['quantity']} HĐ {execution_side} · "
                                        f"P&L {close_order.get('pnl_vnd',0):+,.0f} ₫",
                                        icon="✅",
                                    )
                                st.rerun()
                            except (RuntimeError, ValueError, OSError, PermissionError) as exc:
                                st.error(f"Không thể đóng vị thế: {exc}")
            with position_note_col:
                if active_futures_position:
                    st.caption(f"Đóng vị thế sử dụng giá {managed_futures_symbol} mới nhất đang hiển thị. Đây là PAPER; giá khớp thật có thể khác do trượt giá và thanh khoản.")
                else:
                    st.caption(tr(LANG,"fut_no_position"))
    
            performance = futures_broker.performance_report(mark_price)
            st.markdown(f"### {tr(LANG, 'performance_futures')}")
            report1, report2, report3, report4, report5, report6 = st.columns(6)
            report1.metric(tr(LANG,"money_before_pnl"), f"{performance['capital_before_pnl_vnd']:,.0f} ₫")
            report2.metric(
                tr(LANG,"realized_pnl"), f"{performance['realized_pnl_vnd']:+,.0f} ₫",
                delta=f"{performance['realized_pnl_vnd'] / performance['capital_before_pnl_vnd'] * 100:+.2f}%"
                if performance["capital_before_pnl_vnd"] else None,
            )
            report3.metric(tr(LANG,"unrealized_pnl"), f"{performance['unrealized_pnl_vnd']:+,.0f} ₫")
            report4.metric(tr(LANG,"total_pnl"), f"{performance['total_pnl_vnd']:+,.0f} ₫")
            report5.metric(tr(LANG,"cash_after_realized"), f"{performance['cash_after_realized_vnd']:,.0f} ₫")
            report6.metric(
                tr(LANG,"equity_after_total"), f"{performance['equity_after_total_vnd']:,.0f} ₫",
                delta=f"{performance['return_pct']:+.2f}% {tr(LANG,'performance_suffix')}",
            )
            stat1, stat2, stat3, stat4, stat5, stat6 = st.columns(6)
            stat1.metric(tr(LANG,"investment_return"), f"{performance['return_pct']:+.2f}%")
            stat2.metric(tr(LANG,"day_pnl"), f"{performance['day_pnl_vnd']:+,.0f} ₫")
            stat3.metric(tr(LANG,"closed_trades"), f"{performance['closed_trades']}")
            stat4.metric(tr(LANG,"win_rate"), f"{performance['win_rate_pct']:.1f}%")
            stat5.metric(
                "Profit factor",
                f"{performance['profit_factor']:.2f}" if performance["profit_factor"] is not None else "—",
            )
            stat6.metric(tr(LANG,"max_drawdown"), f"{performance['max_drawdown_pct']:.2f}%")
    
            performance_analytics_chart(
                performance, key="futures_performance_analytics",
                title=f"{managed_futures_symbol} · {tr(LANG, 'performance_futures')}",
            )
            st.caption(
                "Tiền trước lãi/lỗ = vốn PAPER sau điều chỉnh nạp/rút nhưng chưa cộng kết quả giao dịch. "
                f"Tiền sau P&L đã ghi nhận chỉ bao gồm vị thế đã đóng; Equity bao gồm cả P&L chưa ghi nhận theo giá {managed_futures_symbol} hiện tại."
            )
    
            chart_control, bars_control, price_zoom_control, engine_control = st.columns([2,1,1.15,1.35], gap="medium")
            with chart_control:
                futures_chart_tf = st.segmented_control(
                    tr(LANG,"fut_chart_tf"), FUTURES_CHART_TIMEFRAMES, default="15M",
                    key="futures_chart_timeframe", width="stretch",
                ) or "15M"
            with bars_control:
                futures_chart_bars = st.select_slider(
                    tr(LANG,"fut_candles"), options=[80,120,180,240,400,600], value=180,
                    key="futures_chart_bars",
                )
            with engine_control:
                futures_chart_engine = st.selectbox(
                    tr(LANG,"fut_chart_engine"), ["TradingView", "3-panel technical"],
                    key="futures_chart_engine",
                    help="TradingView tương tác hỗ trợ zoom/kéo tự nhiên; 3 panel hiển thị thêm Volume và RSI.",
                )
            with price_zoom_control:
                futures_price_zoom = st.select_slider(
                    tr(LANG,"fut_zoom"), options=[50,75,100,125,150,200,250,300], value=100,
                    format_func=lambda value: f"{value}%", key="futures_price_zoom",
                    help="Chỉ dùng cho Kỹ thuật 3 panel; TradingView zoom trực tiếp bằng chuột.",
                    disabled=futures_chart_engine == "TradingView",
                )
            # The reference chart never borrows an order overlay from a different
            # contract selected in the independent position-management control.
            chart_active_position = active_futures_position and managed_futures_symbol == selected_futures_symbol
            if not chart_active_position:
                active_futures_position = False
                futures_account = {**reference_futures_account, "side":"FLAT", "quantity":0}
                execution_side = futures_result["action"]
                execution_entry = future_plan.get("trigger")
                execution_stop = future_plan.get("stop_loss")
                execution_tp1 = future_plan.get("target_1")
                execution_tp2 = future_plan.get("target_2")
            chart_base_tf = "1D" if futures_chart_tf in TF_ORDER else futures_chart_tf
            selected_future_analysis = analyze_futures_chart_frame(futures_frames, futures_chart_tf)
            futures_chart_frame = selected_future_analysis.get("data", pd.DataFrame()).tail(futures_chart_bars)
            st.caption(f"{futures_chart_tf} · mỗi nến là một kỳ, không phải cửa sổ nến ngày. Kế hoạch Entry/Stop/TP đa khung 15M/1H/1D được giữ riêng.")
            if selected_future_analysis.get("status") != "OK":
                st.info(f"Có {len(futures_chart_frame)} nến {futures_chart_tf} thực; chưa đủ 30 nến cho phân tích kỹ thuật phái sinh. Không tạo thêm lịch sử hoặc ghép hợp đồng khác.")
            if not futures_chart_frame.empty:
                if futures_chart_engine == "TradingView":
                    tv_plan = {**future_plan, "side":futures_result["action"]}
                    live_futures_execution_chart(
                        futures_chart_frame, selected_future_analysis, futures_account, tv_plan,
                        selected_futures_symbol,
                    )
                future_fig = make_subplots(
                    rows=3, cols=1, shared_xaxes=True, vertical_spacing=.035,
                    row_heights=[.64,.19,.17], specs=[[{}],[{}],[{}]],
                )
                future_fig.add_trace(go.Candlestick(
                    x=futures_chart_frame["time"], open=futures_chart_frame["open"], high=futures_chart_frame["high"],
                    low=futures_chart_frame["low"], close=futures_chart_frame["close"], name=selected_futures_symbol,
                    increasing={"line":{"color":UI_COLORS['green'],"width":1.2},"fillcolor":UI_COLORS['green']},
                    decreasing={"line":{"color":UI_COLORS['red'],"width":1.2},"fillcolor":UI_COLORS['red']},
                    hovertext=[f"O {o:,.1f} · H {h:,.1f} · L {l:,.1f} · C {c:,.1f}" for o,h,l,c in zip(futures_chart_frame.open,futures_chart_frame.high,futures_chart_frame.low,futures_chart_frame.close)],
                    hoverinfo="x+text",
                ), row=1, col=1)
                for ma_name, ma_color in (("ma20", UI_COLORS['amber']), ("ma50", UI_COLORS['blue'])):
                    if ma_name in futures_chart_frame:
                        future_fig.add_trace(go.Scatter(x=futures_chart_frame["time"], y=futures_chart_frame[ma_name], name=ma_name.upper(), line={"color":ma_color,"width":1.7}, hovertemplate=f"{ma_name.upper()} %{{y:,.1f}}<extra></extra>"), row=1, col=1)
                volume_colors = [UI_COLORS['green'] if c >= o else UI_COLORS['red'] for o,c in zip(futures_chart_frame.open,futures_chart_frame.close)]
                future_fig.add_trace(go.Bar(x=futures_chart_frame["time"], y=futures_chart_frame["volume"], name="Volume", marker={"color":volume_colors,"opacity":.62}, hovertemplate="Volume %{y:,.0f}<extra></extra>"), row=2, col=1)
                if "vol_ma20" in futures_chart_frame:
                    future_fig.add_trace(go.Scatter(x=futures_chart_frame["time"], y=futures_chart_frame["vol_ma20"], name="Vol MA20", line={"color":UI_COLORS['amber'],"width":1.4}, hovertemplate="Vol MA20 %{y:,.0f}<extra></extra>"), row=2, col=1)
                if "rsi14" in futures_chart_frame:
                    future_fig.add_trace(go.Scatter(x=futures_chart_frame["time"], y=futures_chart_frame["rsi14"], name="RSI14", line={"color":UI_COLORS['purple'],"width":1.8}, hovertemplate="RSI14 %{y:.1f}<extra></extra>"), row=3, col=1)
                    future_fig.add_hrect(y0=70,y1=100,fillcolor=UI_COLORS['red'],opacity=.055,line_width=0,row=3,col=1)
                    future_fig.add_hrect(y0=0,y1=30,fillcolor=UI_COLORS['green'],opacity=.055,line_width=0,row=3,col=1)
                    for rsi_level,rsi_color in ((70,UI_COLORS['red']),(50,CHART_BORDER),(30,UI_COLORS['green'])):
                        future_fig.add_hline(y=rsi_level,line_dash="dot",line_color=rsi_color,line_width=1,row=3,col=1)
                selected_support = selected_future_analysis.get("support")
                selected_resistance = selected_future_analysis.get("resistance")
                if selected_support is not None:
                    future_fig.add_hline(y=selected_support, line_dash="dash", line_color=UI_COLORS['green'], annotation_text=f"S {selected_support:,.1f}", annotation_position="bottom left", row=1,col=1)
                if selected_resistance is not None:
                    future_fig.add_hline(y=selected_resistance, line_dash="dash", line_color=UI_COLORS['red'], annotation_text=f"R {selected_resistance:,.1f}", annotation_position="top left", row=1,col=1)
                wy_range_low = selected_future_analysis.get("range_low")
                wy_range_high = selected_future_analysis.get("range_high")
                if wy_range_low is not None:
                    future_fig.add_hline(
                        y=wy_range_low, line_dash="dot", line_color="#546e7a", line_width=1,
                        annotation_text=f"Wyckoff Low · {wy_range_low:,.1f}",
                        annotation_position="bottom left",
                        annotation_font={"size":9, "color":UI_COLORS['muted']},
                        annotation_bgcolor=CHART_CONTROL_BG,
                        annotation_bordercolor="rgba(144,164,174,.35)",
                        annotation_borderpad=3,
                        row=1, col=1,
                    )
                if wy_range_high is not None:
                    future_fig.add_hline(
                        y=wy_range_high, line_dash="dot", line_color="#546e7a", line_width=1,
                        annotation_text=f"Wyckoff High · {wy_range_high:,.1f}",
                        annotation_position="top left",
                        annotation_font={"size":9, "color":UI_COLORS['muted']},
                        annotation_bgcolor=CHART_CONTROL_BG,
                        annotation_bordercolor="rgba(144,164,174,.35)",
                        annotation_borderpad=3,
                        row=1, col=1,
                    )
                fibonacci = selected_future_analysis.get("fibonacci", {})
                if fibonacci.get("status") == "OK":
                    fib_colors = {
                        "0.236":UI_COLORS['muted'], "0.382":UI_COLORS['blue'], "0.500":UI_COLORS['amber'],
                        "0.618":UI_COLORS['purple'], "0.786":"#ec4899",
                    }
                    golden_low, golden_high = fibonacci["golden_zone"]
                    future_fig.add_hrect(
                        y0=golden_low, y1=golden_high, fillcolor=UI_COLORS['purple'], opacity=.065,
                        line_width=0, row=1, col=1,
                    )
                    for fib_ratio, fib_level in fibonacci.get("levels", {}).items():
                        if fib_ratio in fib_colors:
                            future_fig.add_hline(
                                y=fib_level, line_dash="dot", line_color=fib_colors[fib_ratio],
                                line_width=1, annotation_text=f"Fib {fib_ratio} · {fib_level:,.1f}",
                                annotation_position="left", row=1, col=1,
                            )
                    chart_min, chart_max = float(futures_chart_frame.low.min()), float(futures_chart_frame.high.max())
                    visible_span = max(chart_max - chart_min, 1.0)
                    current_price = float(futures_chart_frame.iloc[-1]["close"])
                    projected_extensions = []
                    extension_colors = {"1.272":UI_COLORS['amber'], "1.414":"#ff8a65", "1.618":"#ec4899", "2.000":UI_COLORS['red']}
                    for fib_ratio, fib_level in fibonacci.get("extensions", {}).items():
                        # Prevent extreme old swings from flattening the useful candle area.
                        if abs(float(fib_level) - current_price) <= visible_span * 1.35:
                            projected_extensions.append((fib_ratio, float(fib_level)))
                    for extension_index, (fib_ratio, fib_level) in enumerate(projected_extensions):
                        future_fig.add_hline(
                            y=fib_level, line_dash="dashdot", line_color=extension_colors.get(fib_ratio,"#ff8a65"),
                            line_width=1.15 if fib_ratio in {"1.272","1.618"} else .85,
                            annotation_text=f"Fib Ext {fib_ratio} · {fib_level:,.1f}",
                            annotation_position="top left" if extension_index % 2 == 0 else "bottom left",
                            annotation_font={"size":9, "color":extension_colors.get(fib_ratio,"#ff8a65")},
                            row=1, col=1,
                        )
                    if projected_extensions:
                        # Plotly shapes do not affect autorange; invisible anchors keep projections visible.
                        future_fig.add_trace(go.Scatter(
                            x=[futures_chart_frame["time"].iloc[-1]] * len(projected_extensions),
                            y=[level for _, level in projected_extensions], mode="markers",
                            marker={"size":1, "opacity":0}, showlegend=False, hoverinfo="skip",
                            name="Fib projection anchors",
                        ), row=1, col=1)
                future_fig.add_hline(
                    y=mark_price, line_color="#ffffff" if not UI_LIGHT else "#334155", line_width=1.2,
                    annotation_text=f"GIÁ HIỆN TẠI · {mark_price:,.1f}", annotation_position="bottom left",
                    annotation_font={"size":9,"color":CHART_TEXT}, row=1,col=1,
                )
                # TradingView-style translucent execution zones for both plan and live position.
                if execution_entry is not None:
                    zone_entry = float(execution_entry)
                    zone_span = max(
                        [abs(float(level) - zone_entry) for level in (execution_stop, execution_tp1, execution_tp2) if level is not None] or [1.0]
                    )
                    entry_zone_low = float(future_plan.get("entry_low")) if not active_futures_position and future_plan.get("entry_low") is not None else zone_entry - max(.1, zone_span * .035)
                    entry_zone_high = float(future_plan.get("entry_high")) if not active_futures_position and future_plan.get("entry_high") is not None else zone_entry + max(.1, zone_span * .035)
                    future_fig.add_hrect(y0=min(entry_zone_low,entry_zone_high),y1=max(entry_zone_low,entry_zone_high),
                                         fillcolor="#26c6da",opacity=.14,line_width=1,line_color="#26c6da",row=1,col=1)
                    if execution_stop is not None:
                        future_fig.add_hrect(y0=min(zone_entry,float(execution_stop)),y1=max(zone_entry,float(execution_stop)),
                                             fillcolor=UI_COLORS['red'],opacity=.09,line_width=0,row=1,col=1)
                    if execution_tp1 is not None:
                        future_fig.add_hrect(y0=min(zone_entry,float(execution_tp1)),y1=max(zone_entry,float(execution_tp1)),
                                             fillcolor=UI_COLORS['green'],opacity=.075,line_width=0,row=1,col=1)
                    if execution_tp1 is not None and execution_tp2 is not None:
                        future_fig.add_hrect(y0=min(float(execution_tp1),float(execution_tp2)),y1=max(float(execution_tp1),float(execution_tp2)),
                                             fillcolor="#c5ff00",opacity=.06,line_width=0,row=1,col=1)
                if not active_futures_position and execution_entry is not None:
                    plan_levels = [
                        (execution_entry, "ĐIỂM VÀO", "#26c6da", "solid", "top left"),
                        (execution_stop, "CẮT LỖ", UI_COLORS['red'], "dash", "bottom left"),
                        (execution_tp1, "CHỐT LỜI TP1", UI_COLORS['green'], "dash", "top left"),
                        (execution_tp2, "CHỐT LỜI TP2", UI_COLORS['green'], "dashdot", "bottom left"),
                    ]
                    for plan_level, plan_title, plan_color, plan_dash, plan_position in plan_levels:
                        if plan_level is not None:
                            future_fig.add_hline(
                                y=float(plan_level), line_color=plan_color, line_width=1.8, line_dash=plan_dash,
                                annotation_text=f"KẾ HOẠCH · {plan_title} {float(plan_level):,.1f}",
                                annotation_position=plan_position,
                                annotation_font={"size":9,"color":plan_color}, row=1,col=1,
                            )
                # Active PAPER position overlay: actual entry, protective stop and profit targets.
                if futures_account.get("side") in {"LONG", "SHORT"} and int(futures_account.get("quantity", 0)) > 0:
                    position_side = futures_account["side"]
                    position_qty = int(futures_account["quantity"])
                    entry_price = float(futures_account["entry_price"])
                    stop_loss = futures_account.get("stop_loss")
                    target_1 = futures_account.get("target")
                    target_2 = futures_account.get("target_2")
                    open_pnl = float(futures_account.get("unrealized_pnl_vnd", 0))
                    pnl_color = UI_COLORS['green'] if open_pnl >= 0 else UI_COLORS['red']
                    if stop_loss is not None:
                        stop_loss = float(stop_loss)
                    if target_1 is not None:
                        target_1 = float(target_1)
                    future_fig.add_hline(
                        y=entry_price, line_color="#26c6da", line_width=2.2,
                        annotation_text=f"{position_side} {position_qty} HĐ · ENTRY {entry_price:,.1f} · P&L {open_pnl:+,.0f} ₫",
                        annotation_position="top left", annotation_font={"size":10, "color":pnl_color},
                        annotation_bgcolor=CHART_CONTROL_BG, annotation_bordercolor="#26c6da",
                        annotation_borderpad=4, row=1, col=1,
                    )
                    if stop_loss is not None:
                        future_fig.add_hline(
                            y=stop_loss, line_color=UI_COLORS['red'], line_width=2, line_dash="dash",
                            annotation_text=f"CẮT LỖ · {stop_loss:,.1f}", annotation_position="bottom left",
                            annotation_font={"size":10, "color":UI_COLORS['red']},
                            annotation_bgcolor=CHART_CONTROL_BG, annotation_bordercolor=UI_COLORS['red'],
                            annotation_borderpad=4, row=1, col=1,
                        )
                    if target_1 is not None:
                        target_1_label = "TP1 ĐÃ CHỐT" if futures_account.get("target_1_done") else "CHỐT LỜI TP1"
                        future_fig.add_hline(
                            y=target_1, line_color=UI_COLORS['green'], line_width=2, line_dash="dash",
                            annotation_text=f"{target_1_label} · {target_1:,.1f}", annotation_position="top left",
                            annotation_font={"size":10, "color":UI_COLORS['green']},
                            annotation_bgcolor=CHART_CONTROL_BG, annotation_bordercolor=UI_COLORS['green'],
                            annotation_borderpad=4, row=1, col=1,
                        )
                    if target_2 is not None:
                        target_2 = float(target_2)
                        future_fig.add_hline(
                            y=target_2, line_color=UI_COLORS['green'], line_width=1.7, line_dash="dashdot",
                            annotation_text=f"CHỐT LỜI TP2 · {target_2:,.1f}", annotation_position="bottom left",
                            annotation_font={"size":10, "color":UI_COLORS['green']},
                            annotation_bgcolor=CHART_CONTROL_BG, annotation_bordercolor="#64dd17",
                            annotation_borderpad=4, row=1, col=1,
                        )
                future_events = futures_wyckoff_events(futures_chart_frame, max_bars=len(futures_chart_frame))
                if not future_events.empty:
                    # Keep every marker/tooltip, but only label events separated by enough bars.
                    event_times = list(futures_chart_frame["time"])
                    min_label_gap = max(5, len(event_times) // 24)
                    last_label_index = -min_label_gap
                    sparse_labels = []
                    for event_time, event_name in zip(future_events["time"], future_events["event"]):
                        event_index = min(range(len(event_times)), key=lambda i: abs(pd.Timestamp(event_times[i]) - pd.Timestamp(event_time)))
                        show_label = event_index - last_label_index >= min_label_gap
                        sparse_labels.append(event_name if show_label else "")
                        if show_label:
                            last_label_index = event_index
                    future_events = future_events.assign(chart_label=sparse_labels)
                    bull_events = future_events[future_events["event"].isin(["SPRING","SOS","LPS"])]
                    bear_events = future_events[future_events["event"].isin(["UT","SOW"])]
                    if not bull_events.empty:
                        future_fig.add_trace(go.Scatter(x=bull_events.time,y=bull_events.price,mode="markers+text",name="Wyckoff Bull",text=bull_events.chart_label,textposition="bottom center",textfont={"size":9,"color":UI_COLORS['green']},marker={"size":10,"color":UI_COLORS['green'],"symbol":"triangle-up"},customdata=bull_events[["event","phase","bias"]],hovertemplate="<b>%{customdata[0]}</b> · %{customdata[1]}<br>%{x}<br>%{y:,.1f} · %{customdata[2]}<extra></extra>"),row=1,col=1)
                    if not bear_events.empty:
                        future_fig.add_trace(go.Scatter(x=bear_events.time,y=bear_events.price,mode="markers+text",name="Wyckoff Bear",text=bear_events.chart_label,textposition="top center",textfont={"size":9,"color":UI_COLORS['red']},marker={"size":10,"color":UI_COLORS['red'],"symbol":"triangle-down"},customdata=bear_events[["event","phase","bias"]],hovertemplate="<b>%{customdata[0]}</b> · %{customdata[1]}<br>%{x}<br>%{y:,.1f} · %{customdata[2]}<extra></extra>"),row=1,col=1)
                future_fig.update_layout(
                    height=760, template="plotly_white" if UI_LIGHT else "plotly_dark", dragmode="zoom", hovermode="x unified",
                    margin=dict(l=10,r=105,t=45,b=10), xaxis_rangeslider_visible=False,
                    paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
                    font={"family":FONT_STACK,"color":CHART_TEXT,"size":12},
                    legend={"orientation":"h","y":1.02,"x":0}, uirevision=f"{selected_futures_symbol}-{futures_chart_tf}-Y{futures_price_zoom}",
                )
                future_fig.update_xaxes(showgrid=True,gridcolor=CHART_GRID,rangeslider_visible=False,showspikes=True,spikemode="across",spikesnap="cursor")
                future_fig.update_yaxes(side="right",showgrid=True,gridcolor=CHART_GRID,automargin=True)
                if futures_price_zoom == 100:
                    future_fig.update_yaxes(fixedrange=False, autorange=True, tickformat=",.1f", row=1,col=1)
                else:
                    price_center = float(futures_chart_frame.iloc[-1]["close"])
                    natural_span = max(float(futures_chart_frame["high"].max()) - float(futures_chart_frame["low"].min()), 1.0)
                    minimum_half_span = max(float(selected_future_analysis.get("atr14") or 1.0) * 2, .5)
                    price_half_span = max(natural_span * .55 * 100 / float(futures_price_zoom), minimum_half_span)
                    future_fig.update_yaxes(
                        fixedrange=False, autorange=False,
                        range=[price_center - price_half_span, price_center + price_half_span],
                        tickformat=",.1f", row=1,col=1,
                    )
                future_fig.update_yaxes(fixedrange=True, tickformat="~s", row=2,col=1)
                future_fig.update_yaxes(fixedrange=True, range=[0,100],tickvals=[30,50,70],row=3,col=1)
                if futures_chart_engine == "3-panel technical":
                    st.plotly_chart(
                        future_fig, width="stretch", key=f"vn30f1m_chart_{futures_chart_tf}",
                        config={
                            "scrollZoom":True, "displaylogo":False, "doubleClick":"reset+autosize",
                            "responsive":True, "showAxisDragHandles":True, "showAxisRangeEntryBoxes":True,
                            "modeBarButtonsToAdd":["zoom2d","pan2d","zoomIn2d","zoomOut2d","autoScale2d","resetScale2d"],
                            "modeBarButtonsToRemove":["lasso2d","select2d"],
                        },
                    )
                    st.caption("Zoom: giữ chuột và khoanh vùng cần phóng lớn, lăn chuột, hoặc dùng thanh Zoom trục giá 50–300%. Chọn 100% hay nhấp đúp để tự căn lại; nút Pan trên thanh công cụ dùng để di chuyển.")
                else:
                    st.caption("TradingView: lăn chuột để zoom, giữ chuột kéo để di chuyển, kéo trực tiếp trục giá phải để co giãn; nhấp đúp hoặc AUTO SCALE để đặt lại.")
                tech1,tech2,tech3,tech4,tech5 = st.columns(5)
                tech1.metric(f"{futures_chart_tf} Direction", selected_future_analysis.get("direction","N/A"), delta=f"{selected_future_analysis.get('score',0):+.1f}" if selected_future_analysis.get("status") == "OK" else None)
                tech2.metric("MA Regime", selected_future_analysis.get("ma_regime","N/A"))
                tech3.metric("RSI14", fmt(selected_future_analysis.get("rsi14"),1))
                tech4.metric("RVOL", f"{fmt(selected_future_analysis.get('rvol'),2)}x")
                tech5.metric("ATR14", fmt(selected_future_analysis.get("atr14"),1))
                wy1,wy2,wy3 = st.columns(3)
                wy1.metric("Wyckoff Event", selected_future_analysis.get("wyckoff_event","NONE"))
                wy2.metric("Wyckoff Phase", selected_future_analysis.get("wyckoff_phase","TRADING_RANGE"))
                wy3.metric("Wyckoff Bias", selected_future_analysis.get("wyckoff_bias","NEUTRAL"))
                if fibonacci.get("status") == "OK":
                    fib1, fib2, fib3, fib4 = st.columns(4)
                    fib1.metric("Fibonacci Trend", fibonacci.get("direction", "N/A"))
                    fib2.metric("Swing Low / High", f"{fibonacci['swing_low']:,.1f} / {fibonacci['swing_high']:,.1f}")
                    fib3.metric("Fib gần nhất", f"{fibonacci['nearest_ratio']} · {fibonacci['nearest_level']:,.1f}")
                    fib4.metric("Golden Zone 0.5–0.618", f"{fibonacci['golden_zone'][0]:,.1f}–{fibonacci['golden_zone'][1]:,.1f}")
                    fib_extensions = " • ".join(f"{ratio}: {level:,.1f}" for ratio, level in fibonacci.get("extensions", {}).items())
                    st.caption(f"Nguồn hướng: {fibonacci.get('direction_source','SWING_STRUCTURE')} · Fib mở rộng: {fib_extensions}. Chỉ sử dụng cùng MA, Wyckoff, RSI/RVOL và xác nhận đóng nến 15M; không nới stop-loss chỉ vì giá chạm Fib.")
                reasons_selected = selected_future_analysis.get("reasons",[])
                source_note = futures_meta.get(chart_base_tf,{}).get('source','N/A')
                horizon_note = " · gộp từ OHLCV ngày thực có; kỳ đầu/cuối có thể chưa trọn kỳ" if futures_chart_tf in {"1W","1M","1Y"} else ""
                st.caption(f"{tr(LANG,'futures_data')}: {source_note} · {len(futures_chart_frame)} bars{horizon_note} · " + (" • ".join(reasons_selected) if reasons_selected else "Chưa có yếu tố kỹ thuật nổi bật."))
            else:
                st.error(f"Không có dữ liệu biểu đồ {futures_chart_tf} cho {selected_futures_symbol}.")
    
            future_plan = futures_result["plan"]
            plan_tab, frames_tab, risk_tab, futures_paper_tab, futures_ai_tab = st.tabs([
                tr(LANG,"futures_plan"), tr(LANG,"futures_frames"), tr(LANG,"futures_risk"),
                tr(LANG,"futures_paper"), tr(LANG,"futures_ai"),
            ])
            with plan_tab:
                q1, q2, q3, q4 = st.columns(4)
                q1.metric(tr(LANG,"futures_entry"), f"{future_plan['entry_low']:,.1f} – {future_plan['entry_high']:,.1f}")
                q2.metric(tr(LANG,"futures_trigger"), fmt(future_plan.get("trigger"),1))
                q3.metric(tr(LANG,"futures_stop"), fmt(future_plan.get("stop_loss"),1), delta=f"{futures_result['stop_points']:.1f} pts")
                q4.metric(tr(LANG,"futures_targets"), f"{fmt(future_plan.get('target_1'),1)} / {fmt(future_plan.get('target_2'),1)}")
                st.info(future_plan["rule"])
                if futures_result["action"] not in {"LONG", "SHORT"}:
                    st.warning(tr(LANG,"futures_no_trade"))
            with frames_tab:
                future_rows = []
                for future_tf in ("15M","1H","1D"):
                    fr = futures_result["frames"].get(future_tf,{})
                    future_rows.append({"Timeframe":future_tf,"Direction":fr.get("direction","N/A"),"Score":fr.get("score",0),"Wyckoff Event":fr.get("wyckoff_event","NONE"),"Wyckoff Phase":fr.get("wyckoff_phase","N/A"),"Wyckoff Bias":fr.get("wyckoff_bias","N/A"),"MA":fr.get("ma_regime","N/A"),"RSI14":fr.get("rsi14"),"RVOL":fr.get("rvol"),"ATR14":fr.get("atr14"),"Support":fr.get("support"),"Resistance":fr.get("resistance")})
                desk_dataframe(themed_dataframe(pd.DataFrame(future_rows)), width="stretch", hide_index=True)
                st.caption(" • ".join(f"{tf}: {meta.get('source')} · {meta.get('rows')} bars" for tf,meta in futures_meta.items()))
            with risk_tab:
                sized = futures_result["position_size"]
                r1,r2,r3 = st.columns(3)
                r1.metric(tr(LANG,"futures_contracts"), sized["contracts"])
                r2.metric(tr(LANG,"futures_margin"), f"{sized['estimated_margin_vnd']:,.0f} ₫")
                r3.metric(tr(LANG,"futures_max_loss"), f"{sized['estimated_max_loss_vnd']:,.0f} ₫")
                cfg = futures_result["config"]
                st.write(f"Risk/trade **{cfg['risk_per_trade']:.2%}** • Daily loss lock **{cfg['max_daily_loss_pct']:.2%}** • Max **{cfg['max_trades_per_day']} trades/day** • Margin model **{cfg['initial_margin_ratio']:.0%}** • Target utilization **{cfg['target_margin_utilization']:.0%}**")
                for flag in futures_result.get("risk_flags",[]): st.warning(flag)
                with st.expander(tr(LANG,"futures_bot_rules"), expanded=True):
                    st.markdown(tr(LANG,"futures_bot_guide"))
            with futures_paper_tab:
                pa1,pa2,pa3,pa4 = st.columns(4)
                pa1.metric("Equity", f"{futures_account['equity_vnd']:,.0f} ₫")
                pa2.metric("Position", f"{futures_account['side']} · {futures_account['quantity']} HĐ")
                pa3.metric("Unrealized P&L", f"{futures_account['unrealized_pnl_vnd']:+,.0f} ₫")
                pa4.metric("Trades today", f"{futures_account['trades_today']}/{futures_result['config']['max_trades_per_day']}")
                open_allowed = (not futures_status.get("running") and futures_account["side"] == "FLAT"
                                and futures_result["action"] in {"LONG","SHORT"}
                                and selected_futures_contracts > 0
                                and selected_futures_contracts <= futures_result["position_size"]["contracts"])
                st.info(
                    f"Lệnh dự kiến: {futures_result['action']} **{selected_futures_contracts} HĐ** · "
                    f"Entry **{fmt(future_plan.get('trigger'),1)}** · Danh nghĩa **{total_notional:,.0f} ₫** · "
                    f"Ký quỹ **{estimated_margin:,.0f} ₫** · SL **{fmt(future_plan.get('stop_loss'),1)}** · "
                    f"TP **{fmt(future_plan.get('target_1'),1)} / {fmt(future_plan.get('target_2'),1)}**"
                )
                open_col, close_col = st.columns(2)
                if open_col.button(tr(LANG,"futures_open"), type="primary", width="stretch", disabled=not open_allowed):
                    try:
                        futures_broker.open(
                            futures_result["action"], selected_futures_contracts, mark_price,
                            future_plan["stop_loss"], future_plan["target_1"], "SYSTEM_PLAN_PAPER",
                            target_2=future_plan.get("target_2"),
                        )
                        st.success("PAPER Futures order filled."); st.rerun()
                    except (ValueError,RuntimeError,OSError) as exc: st.error(str(exc))
                if close_col.button(tr(LANG,"futures_close"), width="stretch", disabled=futures_account["side"] == "FLAT" or bool(futures_status.get("running"))):
                    try:
                        futures_broker.close(mark_price, "MANUAL_CLOSE_PAPER")
                        st.success("PAPER Futures position closed."); st.rerun()
                    except (ValueError,RuntimeError,OSError) as exc: st.error(str(exc))
                with st.expander(tr(LANG,"paper_capital")):
                    if futures_status.get("running"): st.warning(tr(LANG,"paper_bot_stop"))
                    futures_balance = st.number_input("PAPER Futures balance (VND)", min_value=10_000_000.0, max_value=100_000_000_000_000.0, value=float(futures_account["balance_vnd"]), step=100_000_000.0, format="%.0f", disabled=bool(futures_status.get("running")))
                    if st.button(tr(LANG,"paper_set_cash"), key="set_futures_balance", disabled=bool(futures_status.get("running"))):
                        futures_broker.set_balance(futures_balance); st.rerun()
                    futures_reset_confirm = st.text_input(tr(LANG,"paper_reset_confirm"), key="futures_reset_confirm", disabled=bool(futures_status.get("running")))
                    if st.button(tr(LANG,"paper_reset"), key="reset_futures_account", disabled=bool(futures_status.get("running"))):
                        if futures_reset_confirm != "RESET PAPER": st.error(tr(LANG,"paper_reset_wrong"))
                        else: futures_broker.reset(futures_balance); st.rerun()
                if futures_account.get("orders"):
                    st.markdown(f"**{tr(LANG, 'paper_orders')}**")
                    desk_dataframe(themed_dataframe(pd.DataFrame(futures_account["orders"][-100:][::-1])), width="stretch", hide_index=True)
                st.error(f"🔒 {tr(LANG,'futures_live_lock')}")
            with futures_ai_tab:
                st.markdown(futures_ai_brief(futures_result))
    
with tab6:
    if SYSTEM_MODE == "LIVE":
        st.markdown("### ◫ TÀI KHOẢN LIVE · READ-ONLY")
        st.info(tr(LANG, "live_readonly"))
        live1, live2, live3, live4 = st.columns(4)
        live1.metric("MODE", "LIVE")
        live2.metric("MARKET DATA", "CONNECTED")
        live3.metric("ORDER API", "LOCKED")
        live4.metric("PAPER DATA", "HIDDEN")
        st.warning("Không hiển thị hoặc sử dụng số dư, vị thế, lệnh và P&L PAPER trong chế độ LIVE.")
    else:
        paper_broker = PaperBroker(STATE_DIR / "paper_portfolio.json")
        paper_prices = {symbol: float(latest["close"])}
        paper = paper_broker.snapshot(paper_prices)
        bot = bot_status(ROOT)
        position_value = sum(
            paper_broker.market_value_vnd(pos["quantity"], paper_prices.get(code, pos.get("last_price", pos["avg_price"])))
            for code, pos in paper["positions"].items()
        )
        unrealized_pnl = sum(
            paper_broker.market_value_vnd(pos["quantity"], paper_prices.get(code, pos.get("last_price", pos["avg_price"])) - pos["avg_price"])
            for code, pos in paper["positions"].items()
        )
        p1, p2, p3, p4 = st.columns(4)
        p1.metric(tr(LANG, "paper_equity"), f"{paper['equity_vnd']:,.0f} ₫")
        p2.metric(tr(LANG, "cash"), f"{paper['cash_vnd']:,.0f} ₫")
        p3.metric(tr(LANG, "paper_position_value"), f"{position_value:,.0f} ₫", delta=f"{unrealized_pnl:+,.0f} ₫")
        p4.metric("BOT · PAPER", "RUNNING" if bot.get("running") else "STOPPED")
        st.caption(tr(LANG, "paper_strategy_note"))
        st.info(tr(LANG, "paper_settlement_note"))
    
        account_overview, account_positions, account_orders, account_capital, account_risk = st.tabs([
            tr(LANG, "paper_overview"), tr(LANG, "paper_positions"), tr(LANG, "paper_orders"),
            tr(LANG, "paper_capital"), tr(LANG, "paper_risk"),
        ])
    
        with account_overview:
            day_start = float(paper_broker.state.get("day_start_equity_vnd", paper["equity_vnd"]))
            day_pnl = float(paper["equity_vnd"]) - day_start
            cash_ratio = (float(paper["cash_vnd"]) / float(paper["equity_vnd"]) * 100) if paper["equity_vnd"] else 0
            with st.container(key="paper_simulation_notice"):
                st.info(tr(LANG, "paper_simulation_notice"))
            with st.container(key="paper_overview_metrics"):
                o1, o2, o3, o4, o5 = st.columns(5)
                o1.metric(tr(LANG, "paper_day_pnl"), f"{day_pnl:+,.0f} ₫")
                o2.metric(tr(LANG, "paper_cash_ratio"), f"{cash_ratio:.1f}%")
                o3.metric(tr(LANG, "paper_open_positions"), len(paper["positions"]))
                o4.metric(tr(LANG, "paper_filled_orders"), len(paper["orders"]))
                o5.metric(tr(LANG, "paper_pending_cash"), f"{paper.get('pending_cash_vnd', 0):,.0f} ₫")
            stock_performance = paper_broker.performance_report(paper_prices)
            st.markdown(f"### {tr(LANG, 'performance_stock')}")
            sp1, sp2, sp3, sp4, sp5, sp6 = st.columns(6)
            sp1.metric(tr(LANG,"money_before_pnl"), f"{stock_performance['capital_before_pnl_vnd']:,.0f} ₫")
            sp2.metric(tr(LANG,"realized_pnl"), f"{stock_performance['realized_pnl_vnd']:+,.0f} ₫")
            sp3.metric(tr(LANG,"unrealized_pnl"), f"{stock_performance['unrealized_pnl_vnd']:+,.0f} ₫")
            sp4.metric(tr(LANG,"total_pnl"), f"{stock_performance['total_pnl_vnd']:+,.0f} ₫")
            sp5.metric(tr(LANG,"cash_after_realized"), f"{stock_performance['cash_after_realized_vnd']:,.0f} ₫")
            sp6.metric(
                tr(LANG,"equity_after_total"), f"{stock_performance['equity_after_total_vnd']:,.0f} ₫",
                delta=f"{stock_performance['return_pct']:+.2f}% {tr(LANG,'performance_suffix')}",
            )
            ss1, ss2, ss3, ss4, ss5, ss6 = st.columns(6)
            ss1.metric(tr(LANG,"investment_return"), f"{stock_performance['return_pct']:+.2f}%")
            ss2.metric(tr(LANG,"day_pnl"), f"{stock_performance['day_pnl_vnd']:+,.0f} ₫")
            ss3.metric(tr(LANG,"closed_trades"), f"{stock_performance['closed_trades']}")
            ss4.metric(tr(LANG,"win_rate"), f"{stock_performance['win_rate_pct']:.1f}%")
            ss5.metric(
                "Profit factor",
                f"{stock_performance['profit_factor']:.2f}" if stock_performance["profit_factor"] is not None else "—",
            )
            ss6.metric(tr(LANG,"max_drawdown"), f"{stock_performance['max_drawdown_pct']:.2f}%")
            performance_analytics_chart(
                stock_performance, key="stock_performance_analytics",
                title=tr(LANG, "performance_stock"),
            )
            st.caption(
                "P&L cơ sở đã trừ phí mua, phí bán và thuế bán theo cấu hình PAPER. Dòng tiền điều chỉnh vốn "
                "được tách khỏi lợi nhuận; P&L chưa ghi nhận sử dụng giá mới nhất đang có của từng mã."
            )
    
        with account_positions:
            positions = []
            for code, pos in paper["positions"].items():
                last_price = float(paper_prices.get(code, pos.get("last_price", pos["avg_price"])))
                pnl = paper_broker.market_value_vnd(pos["quantity"], last_price - pos["avg_price"])
                available_quantity = paper_broker.available_quantity(code)
                positions.append({
                    tr(LANG, "symbol"): code, tr(LANG, "quantity"): pos["quantity"],
                    tr(LANG, "paper_available_quantity"): available_quantity,
                    tr(LANG, "paper_pending_quantity"): max(0, int(pos["quantity"]) - available_quantity),
                    tr(LANG, "avg_price"): pos["avg_price"], tr(LANG, "paper_last_price"): last_price,
                    tr(LANG, "paper_market_value"): paper_broker.market_value_vnd(pos["quantity"], last_price),
                    tr(LANG, "paper_unrealized_pnl"): pnl, "Stop loss": pos.get("stop_loss"),
                    tr(LANG, "paper_target"): pos.get("target"),
                })
            if positions:
                position_columns = {
                    tr(LANG, "quantity"): {"type_config": {"type": "number", "format": "vn_integer"}},
                    tr(LANG, "paper_available_quantity"): {"type_config": {"type": "number", "format": "vn_integer"}},
                    tr(LANG, "paper_pending_quantity"): {"type_config": {"type": "number", "format": "vn_integer"}},
                    tr(LANG, "avg_price"): {"type_config": {"type": "number", "format": "%.3f"}},
                    tr(LANG, "paper_last_price"): {"type_config": {"type": "number", "format": "%.3f"}},
                    tr(LANG, "paper_market_value"): {"type_config": {"type": "number", "format": "vn_vnd"}},
                    tr(LANG, "paper_unrealized_pnl"): {"type_config": {"type": "number", "format": "vn_signed_vnd"}},
                    "Stop loss": {"type_config": {"type": "number", "format": "%.3f"}},
                    tr(LANG, "paper_target"): {"type_config": {"type": "number", "format": "%.3f"}},
                }
                desk_dataframe(
                    themed_dataframe(pd.DataFrame(positions)), width="stretch", hide_index=True,
                    column_config=position_columns, key="paper_positions_table",
                )
            else:
                st.info(tr(LANG, "paper_no_positions"))
    
        with account_orders:
            if paper["orders"]:
                desk_dataframe(themed_dataframe(pd.DataFrame(paper["orders"][-100:][::-1])), width="stretch", hide_index=True)
            else:
                st.info(tr(LANG, "paper_no_orders"))
    
        with account_capital:
            st.caption(tr(LANG, "paper_capital_note"))
            if bot.get("running"):
                st.warning(tr(LANG, "paper_bot_stop"))
            cash_col, reset_col = st.columns(2, gap="medium")
            with cash_col:
                new_cash = st.number_input(
                    tr(LANG, "paper_cash_new"), min_value=1_000_000.0,
                    max_value=1_000_000_000_000_000.0, value=float(paper["cash_vnd"]),
                    step=100_000_000.0, format="%.0f", disabled=bool(bot.get("running")),
                )
                if st.button(tr(LANG, "paper_set_cash"), width="stretch", disabled=bool(bot.get("running"))):
                    try:
                        paper_broker.set_cash_balance(new_cash)
                        st.success(tr(LANG, "paper_cash_updated", value=f"{new_cash:,.0f}")); st.rerun()
                    except (OSError, ValueError) as exc:
                        st.error(str(exc))
            with reset_col:
                reset_cash = st.number_input(
                    tr(LANG, "paper_reset_amount"), min_value=1_000_000.0,
                    max_value=1_000_000_000_000_000.0, value=float(paper_broker.config.initial_cash_vnd),
                    step=100_000_000.0, format="%.0f", disabled=bool(bot.get("running")),
                )
                reset_confirmation = st.text_input(tr(LANG, "paper_reset_confirm"), key="paper_reset_confirmation", disabled=bool(bot.get("running")))
                if st.button(tr(LANG, "paper_reset"), width="stretch", disabled=bool(bot.get("running"))):
                    if reset_confirmation != "RESET PAPER":
                        st.error(tr(LANG, "paper_reset_wrong"))
                    else:
                        try:
                            paper_broker.reset(reset_cash)
                            st.session_state.paper_reset_confirmation = ""
                            st.success(tr(LANG, "paper_reset_done", value=f"{reset_cash:,.0f}")); st.rerun()
                        except (OSError, ValueError) as exc:
                            st.error(str(exc))
            adjustments = paper.get("capital_adjustments", [])
            if adjustments:
                st.markdown(f"**{tr(LANG, 'paper_adjustments')}**")
                desk_dataframe(themed_dataframe(pd.DataFrame(adjustments[-20:][::-1])), width="stretch", hide_index=True)
        with account_risk:
            cfg = PaperBroker(STATE_DIR / "paper_portfolio.json").config
            risk_rows = pd.DataFrame([
                {tr(LANG, "parameters"): tr(LANG, "paper_risk_trade"), tr(LANG, "value"): f"{cfg.risk_per_trade:.1%}"},
                {tr(LANG, "parameters"): tr(LANG, "paper_max_symbol"), tr(LANG, "value"): f"{cfg.max_position_pct:.0%}"},
                {tr(LANG, "parameters"): tr(LANG, "paper_max_positions"), tr(LANG, "value"): str(cfg.max_positions) if cfg.max_positions else "∞"},
                {tr(LANG, "parameters"): tr(LANG, "paper_daily_lock"), tr(LANG, "value"): f"{cfg.max_daily_loss_pct:.1%}"},
                {tr(LANG, "parameters"): tr(LANG, "paper_lot_size"), tr(LANG, "value"): str(cfg.lot_size)},
            ])
            desk_dataframe(themed_dataframe(risk_rows), width="stretch", hide_index=True)
            with st.container(key="paper_live_locked_notice"):
                st.warning(tr(LANG, "paper_live_locked_notice"))
    
with tab7:
    st.caption("Walk-forward không nhìn trước · đo hướng giá tương lai · chưa gồm phí, trượt giá và giới hạn thanh khoản.")
    v1, v2 = st.columns(2)
    horizon = v1.selectbox("Khoảng đánh giá", [10, 20, 40, 60], index=1, format_func=lambda value: f"{value} phiên")
    step = v2.selectbox("Khoảng lấy mẫu", [10, 20, 40], index=1, format_func=lambda value: f"Mỗi {value} phiên")
    with st.spinner("Đang kiểm định tín hiệu lịch sử..."):
        validation = validate_cached(df, horizon, step, "PRO_DECISION_4TF")
    if validation["status"] != "OK":
        st.info("Chưa đủ lịch sử để kiểm định.")
    else:
        v1, v2, v3, v4 = st.columns(4)
        v1.metric("Hit rate định hướng", "—" if validation["hit_rate"] is None else f"{validation['hit_rate']:.1f}%")
        v2.metric("Số tín hiệu", validation["signals"], delta=f"{validation['observations']} mẫu")
        v3.metric("Mức phủ tín hiệu", f"{validation['coverage']:.1f}%")
        v4.metric("Biên định hướng TB", "—" if validation["avg_forward_return"] is None else f"{validation['avg_forward_return']:+.2f}%")
        st.markdown(
            f"Tín hiệu tăng ({validation.get('bullish_signals', 0)} mẫu): lợi suất tương lai TB **{fmt(validation.get('bullish_avg_return'), 2)}%** · "
            f"Tín hiệu giảm ({validation.get('bearish_signals', 0)} mẫu): lợi suất tương lai TB **{fmt(validation.get('bearish_avg_return'), 2)}%**"
        )
        records = validation["records"].copy()
        records["Dự báo"] = records["prediction"].map({1: "TĂNG", -1: "GIẢM", 0: "TRUNG TÍNH"})
        records["Đúng hướng"] = records["correct"].map({True: "ĐÚNG", False: "SAI/Không tín hiệu"})
        desk_dataframe(themed_dataframe(records.rename(columns={"time": "Thời điểm", "score": "Điểm", "confidence": "Tin cậy", "alignment": "Đồng thuận", "grade": "Hạng", "forward_return_pct": "Lợi suất tương lai %"})[["Thời điểm", "Điểm", "Tin cậy", "Đồng thuận", "Hạng", "Dự báo", "Lợi suất tương lai %", "Đúng hướng"]].sort_values("Thời điểm", ascending=False)), width="stretch", hide_index=True)
        st.warning("Hit rate lịch sử không phải xác suất thắng tương lai. Cần kiểm định thêm theo giai đoạn thị trường và danh mục trước khi dùng vốn thật.")

with tab8:
    st.markdown(
        f"""<div class="ai-shell"><div class="ai-head"><div class="ai-brand"><div class="ai-orb">✦</div>
        <div><div class="ai-title">{tr(LANG,'ai_title')} · {symbol}</div><div class="ai-subtitle">{tr(LANG,'ai_subtitle')}</div></div>
        </div><div class="ai-live">CONTEXT · PRO V3</div></div></div>""",
        unsafe_allow_html=True,
    )
    ai_context = compact_ai_context(
        symbol,
        result,
        latest.to_dict(),
        wy,
        news_context if "news_context" in locals() else None,
    )
    ai_mode_options = [tr(LANG, "ai_internal"), tr(LANG, "ai_online")]
    ai_mode = st.segmented_control(tr(LANG, "ai_mode"), ai_mode_options, default=ai_mode_options[0], width="stretch") or ai_mode_options[0]
    if ai_mode == ai_mode_options[1]:
        st.caption(tr(LANG, "ai_online_notice"))
    else:
        st.caption(tr(LANG, "ai_local_notice"))

    st.markdown(
        f"`{tr(LANG,'ai_context')}` · **{symbol}** · {action_display} · "
        f"Score **{result.get('consensus_score', 0):+.1f}** · {tr(LANG,'confidence')} **{result.get('confidence', 0)}%**"
    )

    suggestions_by_lang = {
        "vi": ["Vì sao hệ thống đưa ra quyết định này?", "Phân tích xung đột đa khung", "Rủi ro và mức cắt lỗ là gì?"],
        "en": ["Why did the system make this decision?", "Analyze timeframe conflicts", "What are the risks and stop level?"],
        "zh": ["为什么系统做出这个决策？", "分析多周期冲突", "风险和止损位是什么？"],
        "ru": ["Почему система приняла это решение?", "Разберите конфликт таймфреймов", "Каковы риски и стоп-уровень?"],
        "de": ["Warum trifft das System diese Entscheidung?", "Timeframe-Konflikte analysieren", "Welche Risiken und Stop-Niveaus gibt es?"],
    }
    pending_question = None
    suggestion_cols = st.columns(3)
    for index, (column, suggestion) in enumerate(zip(suggestion_cols, suggestions_by_lang[LANG])):
        if column.button(suggestion, key=f"ai_suggestion_{LANG}_{index}", width="stretch"):
            pending_question = suggestion

    if "ai_conversations" not in st.session_state:
        st.session_state.ai_conversations = {}
    history = st.session_state.ai_conversations.setdefault(symbol, [])
    with st.form("ai_question_form", clear_on_submit=True):
        typed_question = st.text_area(
            tr(LANG, "ai_question"),
            placeholder=tr(LANG, "ai_placeholder"),
            height=92,
            max_chars=2000,
        )
        send_col, clear_col = st.columns([3, 1])
        submitted = send_col.form_submit_button(f"✦ {tr(LANG,'ai_send')}", type="primary", width="stretch")
        clear_requested = clear_col.form_submit_button(tr(LANG, "ai_clear"), width="stretch")

    if clear_requested:
        history.clear()
    question = pending_question or (typed_question.strip() if submitted else "")
    ai_warning = None
    if question:
        with st.spinner(tr(LANG, "ai_thinking")):
            if ai_mode == ai_mode_options[1]:
                try:
                    answer = online_ai_answer(question, ai_context, language=LANG)
                    engine = os.getenv("OPENAI_MODEL", "gpt-5.4")
                except (ValueError, RuntimeError) as exc:
                    answer = local_ai_answer(question, ai_context, language=LANG)
                    engine = "INTERNAL"
                    ai_warning = f"{tr(LANG,'ai_fallback')} ({exc})"
            else:
                answer = local_ai_answer(question, ai_context, language=LANG)
                engine = "INTERNAL"
        history.extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer, "engine": engine},
        ])
        del history[:-16]
    if ai_warning:
        st.warning(ai_warning)
    for message in history:
        avatar = "🤖" if message["role"] == "assistant" else "👤"
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                st.caption(f"AI ENGINE · {message.get('engine', 'INTERNAL')}")
    if not history:
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(local_ai_answer("", ai_context))
            st.caption("AI ENGINE · INTERNAL")

with tab9:
    st.markdown(f"### ◉ {tr(LANG,'algo_title')}")
    st.caption(tr(LANG, "algo_intro"))
    st.info("Phân tích danh mục thống nhất · dữ liệu thị trường mới · chỉ hỗ trợ ra quyết định, không tự gửi lệnh.")

    portfolio_store = PortfolioStore(STATE_DIR / "saved_portfolios.json")
    saved_portfolios = portfolio_store.list()
    with st.expander(f"▣ Danh mục đã lưu · {len(saved_portfolios)}", expanded=bool(saved_portfolios)):
        if not saved_portfolios:
            st.caption("Chưa có danh mục nào được lưu trong hệ thống.")
        else:
            saved_names = [item["name"] for item in saved_portfolios]
            selected_saved_name = st.selectbox(
                "Chọn danh mục đã lưu", saved_names, key="selected_saved_portfolio",
                format_func=lambda name: next(
                    f"{name} · {len(item.get('positions',[]))} mã"
                    for item in saved_portfolios if item["name"] == name
                ),
            )
            saved_open_col, saved_delete_col = st.columns([2, 1], gap="medium")
            if saved_open_col.button("↗ MỞ DANH MỤC", width="stretch", key="open_saved_portfolio"):
                try:
                    loaded_portfolio = portfolio_store.get(selected_saved_name)
                    loaded_basket = loaded_portfolio.get("basket", "ALL")
                    if loaded_basket not in MARKET_SCOPES:
                        loaded_basket = "ALL"
                    loaded_positions = loaded_portfolio.get("positions", [])
                    available_loaded_symbols = set(
                        load_universe(loaded_basket)["symbol"].dropna().astype(str).str.upper()
                    )
                    loaded_positions = [
                        item for item in loaded_positions
                        if str(item.get("symbol", "")).upper() in available_loaded_symbols
                    ]
                    loaded_symbols = [str(item["symbol"]).upper() for item in loaded_positions]
                    if not loaded_symbols:
                        raise ValueError("Các mã đã lưu không còn nằm trong rổ hiện tại.")
                    st.session_state.portfolio_analysis_basket = loaded_basket
                    st.session_state[f"portfolio_symbols_{loaded_basket}"] = loaded_symbols
                    st.session_state.portfolio_algorithm_editor_symbols = tuple(loaded_symbols)
                    st.session_state.pop("portfolio_algorithm_editor", None)
                    st.session_state.portfolio_algorithm_input = pd.DataFrame(
                        loaded_positions, columns=["symbol","quantity","buy_price"]
                    )
                    st.session_state.portfolio_name_input = selected_saved_name
                    st.toast(f"Đã mở danh mục {selected_saved_name}", icon="✅")
                    st.rerun()
                except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                    st.error(f"Không thể mở danh mục: {exc}")
            with saved_delete_col:
                with st.popover("⌫ XÓA DANH MỤC", use_container_width=True):
                    st.warning(f"Danh mục “{selected_saved_name}” sẽ bị xóa khỏi hệ thống.")
                    confirm_saved_delete = st.checkbox(
                        "Xác nhận xóa", key=f"confirm_delete_portfolio_{selected_saved_name}"
                    )
                    if st.button(
                        "⌫ XÁC NHẬN XÓA", type="primary", width="stretch",
                        disabled=not confirm_saved_delete, key=f"delete_portfolio_{selected_saved_name}",
                    ):
                        try:
                            portfolio_store.delete(selected_saved_name)
                            st.toast(f"Đã xóa danh mục {selected_saved_name}", icon="🗑️")
                            st.rerun()
                        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                            st.error(f"Không thể xóa danh mục: {exc}")

    basket_col, symbols_col = st.columns([1, 2.4], gap="medium")
    with basket_col:
        portfolio_basket = st.selectbox(
            "Rổ cổ phiếu", list(MARKET_SCOPES), format_func=lambda key: MARKET_SCOPES[key],
            key="portfolio_analysis_basket",
        )
    try:
        portfolio_listing = load_universe(portfolio_basket)
        portfolio_symbol_options = portfolio_listing["symbol"].dropna().astype(str).str.upper().drop_duplicates().tolist()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as portfolio_listing_exc:
        portfolio_symbol_options = []
        st.warning(f"Không tải được rổ {MARKET_SCOPES[portfolio_basket]}: {portfolio_listing_exc}")
    with symbols_col:
        default_portfolio_symbols = [symbol] if symbol in portfolio_symbol_options else portfolio_symbol_options[:1]
        selected_portfolio_symbols = st.multiselect(
            f"Mã thuộc rổ {MARKET_SCOPES[portfolio_basket]}", portfolio_symbol_options,
            default=default_portfolio_symbols, key=f"portfolio_symbols_{portfolio_basket}",
            help="Chọn một hoặc nhiều mã đã đầu tư; bảng bên dưới chỉ nhận mã từ rổ này.",
        )

    existing_portfolio_input = st.session_state.get("portfolio_algorithm_input", pd.DataFrame())
    existing_positions = {}
    if isinstance(existing_portfolio_input, pd.DataFrame) and not existing_portfolio_input.empty:
        existing_positions = {
            str(row.get("symbol", "")).upper(): row
            for _, row in existing_portfolio_input.iterrows()
        }
    editor_symbols_key = "portfolio_algorithm_editor_symbols"
    symbols_signature = tuple(selected_portfolio_symbols)
    if st.session_state.get(editor_symbols_key) != symbols_signature:
        st.session_state[editor_symbols_key] = symbols_signature
        st.session_state.pop("portfolio_algorithm_editor", None)
        st.session_state.portfolio_algorithm_input = pd.DataFrame([
            {
                "symbol":code,
                "quantity":int(float(existing_positions.get(code, {}).get("quantity", 0) or 0)),
                "buy_price":float(existing_positions.get(code, {}).get("buy_price", 0) or 0),
            }
            for code in selected_portfolio_symbols
        ], columns=["symbol","quantity","buy_price"])
    elif "portfolio_algorithm_input" not in st.session_state:
        st.session_state.portfolio_algorithm_input = pd.DataFrame(
            columns=["symbol","quantity","buy_price"]
        )
    # A form prevents Streamlit from rerunning after every edited cell. All
    # rows are committed and analyzed with a single submit.
    with st.form("portfolio_algorithm_form", clear_on_submit=False):
        portfolio_tf = st.selectbox("Khung phân tích danh mục cơ sở", ["MULTI", *TF_ORDER], key="portfolio_analysis_timeframe")
        st.caption("Khung chọn có Signal/Score riêng; System Action, kế hoạch và kết luận tổng hợp vẫn là đa khung. Không thay đổi BOT.")
        portfolio_name = st.text_input(
            "Tên danh mục", key="portfolio_name_input",
            placeholder="Ví dụ: Danh mục đầu tư dài hạn",
            max_chars=80,
        )
        portfolio_input = desk_data_editor(
            st.session_state.portfolio_algorithm_input,
            key="portfolio_algorithm_editor", num_rows="fixed", hide_index=True,
            width="stretch",
            column_config={
                "symbol":st.column_config.TextColumn(tr(LANG,"algo_symbol"), disabled=True),
                "quantity":st.column_config.NumberColumn(tr(LANG,"algo_quantity"), min_value=0, step=100, format="%d"),
                "buy_price":st.column_config.NumberColumn(
                    tr(LANG,"algo_buy_price"), min_value=0.0, step=.001, format="%.3f",
                    help="Nhập giá với 3 chữ số thập phân, ví dụ 20.876.",
                ),
            },
        )
        save_portfolio_col, run_portfolio_col = st.columns([1, 2], gap="medium")
        save_portfolio_requested = save_portfolio_col.form_submit_button(
            "↓ LƯU DANH MỤC VÀO HỆ THỐNG", width="stretch",
        )
        run_portfolio_algorithm = run_portfolio_col.form_submit_button(
            f"◉ {tr(LANG,'algo_run')}", type="primary", width="stretch",
        )
    if portfolio_input is None:
        save_portfolio_requested = run_portfolio_algorithm = False
    if save_portfolio_requested:
        try:
            positions_to_save = [
                {
                    "symbol":str(row.get("symbol") or "").upper().strip(),
                    "quantity":int(float(row.get("quantity") or 0)),
                    "buy_price":float(row.get("buy_price") or 0),
                }
                for _, row in portfolio_input.iterrows()
            ]
            saved_item = portfolio_store.save(
                portfolio_name, portfolio_basket, positions_to_save
            )
            st.session_state.portfolio_algorithm_input = portfolio_input.copy()
            st.toast(
                f"Đã lưu danh mục {saved_item['name']} · {len(saved_item['positions'])} mã",
                icon="✅",
            )
            st.rerun()
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            st.error(f"Không thể lưu danh mục: {exc}")
    if run_portfolio_algorithm:
        st.session_state.portfolio_algorithm_input = portfolio_input.copy()
        normalized_rows = []
        for _, input_row in portfolio_input.iterrows():
            code = str(input_row.get("symbol") or "").upper().strip()
            try:
                quantity = int(float(input_row.get("quantity") or 0))
                buy_price = float(input_row.get("buy_price") or 0)
            except (TypeError, ValueError):
                continue
            if code and code.isalnum() and quantity > 0 and buy_price > 0:
                normalized_rows.append({"symbol":code, "quantity":quantity, "buy_price":buy_price})
        if not normalized_rows:
            st.error(tr(LANG,"algo_invalid"))
        else:
            # Merge repeated symbols into one auditable position using the
            # quantity-weighted average purchase price.
            normalized = pd.DataFrame(normalized_rows)
            normalized["cost_weight"] = normalized["quantity"] * normalized["buy_price"]
            grouped = normalized.groupby("symbol", as_index=False).agg(
                quantity=("quantity","sum"), cost_weight=("cost_weight","sum")
            )
            grouped["buy_price"] = grouped["cost_weight"] / grouped["quantity"]
            progress = st.progress(0, text=f"0/{len(grouped)}")
            output_rows, full_results, failures = [], {}, []
            for algo_index, holding in grouped.iterrows():
                holding_symbol = str(holding["symbol"])
                try:
                    holding_history = get_history(holding_symbol, refresh=True)
                    if holding_history is None or holding_history.empty:
                        raise ValueError("No OHLCV data")
                    holding_analysis = analyze_symbol(holding_symbol, holding_history)
                    holding_analysis = attach_valuation(holding_analysis, load_valuation(holding_symbol))
                    latest_price = float(holding_history.iloc[-1]["close"])
                    buy_price = float(holding["buy_price"])
                    quantity = int(holding["quantity"])
                    price_scale = 1_000.0 if max(abs(latest_price), abs(buy_price)) < 1_000 else 1.0
                    invested_vnd = quantity * buy_price * price_scale
                    market_value_vnd = quantity * latest_price * price_scale
                    pnl_vnd = market_value_vnd - invested_vnd
                    pnl_pct = (latest_price / buy_price - 1) * 100 if buy_price else 0.0
                    action = str(holding_analysis.get("system_action", "CHỜ_XÁC_NHẬN"))
                    score = float(holding_analysis.get("consensus_score", 0) or 0)
                    risk_flags = holding_analysis.get("risk_flags", [])
                    if action in {"BÁN_CÓ_XÁC_NHẬN", "GIẢM_TỶ_TRỌNG"} or (pnl_pct <= -8 and score < 0):
                        advice = "Ưu tiên bảo vệ vốn; xem xét giảm tỷ trọng hoặc thoát vị thế theo kế hoạch Stop Loss."
                    elif action == "MUA_CÓ_XÁC_NHẬN" and pnl_pct >= 0:
                        advice = "Xu hướng đang xác nhận; tiếp tục nắm giữ, dời Stop Loss bảo vệ lợi nhuận và không mua đuổi."
                    elif action in {"THEO_DÕI_MUA", "NẮM_GIỮ"}:
                        advice = "Duy trì vị thế có kiểm soát; chỉ gia tăng khi giá và RVOL xác nhận, tuân thủ vùng Entry/Stop Loss."
                    else:
                        advice = "Chưa có lợi thế rõ; giữ tỷ trọng thận trọng và chờ tín hiệu đa khung đồng thuận."
                    plan = holding_analysis.get("strategy_plan", {})
                    output_rows.append({
                        **portfolio_frame_evidence(holding_analysis, portfolio_tf),
                        "Mã":holding_symbol, "Số lượng":quantity, "Giá mua":buy_price,
                        "Giá hiện tại":latest_price, "Vốn đầu tư (₫)":invested_vnd,
                        "Giá trị hiện tại (₫)":market_value_vnd, "P&L (₫)":pnl_vnd,
                        "P&L (%)":pnl_pct, "System Action":action, "Signal":holding_analysis.get("final_signal"),
                        "Score":score, "Confidence (%)":holding_analysis.get("confidence",0),
                        "Alignment (%)":holding_analysis.get("timeframe_alignment",0),
                        "Grade":holding_analysis.get("decision_grade"), "Regime":holding_analysis.get("market_regime"),
                        "Entry Low":plan.get("entry_low"), "Entry High":plan.get("entry_high"),
                        "Stop Loss":plan.get("stop_loss") or plan.get("protective_stop"),
                        "Target 1":plan.get("target_1") or plan.get("reference_target"),
                        "Risk Flags":" | ".join(risk_flags), "Đánh giá":advice,
                        **valuation_columns(holding_analysis),
                        vt(LANG, "conclusion"): vt(LANG, holding_analysis["valuation_conclusion"]),
                    })
                    full_results[holding_symbol] = holding_analysis
                except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                    failures.append(f"{holding_symbol}: {exc}")
                progress.progress((algo_index + 1) / len(grouped), text=f"{algo_index + 1}/{len(grouped)}")
            st.session_state.portfolio_algorithm_result = {
                "timeframe":portfolio_tf,
                "rows":output_rows, "analyses":full_results, "failures":failures,
                "run_at":pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").isoformat(),
            }
            progress.empty()

    portfolio_algorithm_result = st.session_state.get("portfolio_algorithm_result", {})
    algorithm_rows = portfolio_algorithm_result.get("rows", [])
    if algorithm_rows:
        algorithm_df = pd.DataFrame(algorithm_rows)
        st.caption(pd.Timestamp(portfolio_algorithm_result.get('run_at')).strftime('%d/%m/%Y %H:%M:%S'))
        st.caption(f"Khung đã chạy: {portfolio_algorithm_result.get('timeframe', 'MULTI')} · Score/System Action tổng hợp đa khung giữ riêng; khung thiếu dữ liệu không có Signal/Score.")
        total_cost = float(algorithm_df["Vốn đầu tư (₫)"].sum())
        total_value = float(algorithm_df["Giá trị hiện tại (₫)"].sum())
        total_pnl = total_value - total_cost
        total_return = total_pnl / total_cost * 100 if total_cost else 0.0
        weighted_score = float(np.average(algorithm_df["Score"], weights=algorithm_df["Giá trị hiện tại (₫)"].clip(lower=1)))
        weak_count = int(algorithm_df["System Action"].isin(["BÁN_CÓ_XÁC_NHẬN","GIẢM_TỶ_TRỌNG"]).sum())
        strong_count = int(algorithm_df["System Action"].isin(["MUA_CÓ_XÁC_NHẬN","THEO_DÕI_MUA"]).sum())
        st.markdown(f"**{tr(LANG,'algo_results')}**")
        pa1,pa2,pa3,pa4,pa5 = st.columns(5)
        pa1.metric(tr(LANG,"algo_value"), f"{total_value:,.0f} ₫")
        pa2.metric("P&L", f"{total_pnl:+,.0f} ₫", delta=f"{total_return:+.2f}%")
        pa3.metric("Portfolio Score", f"{weighted_score:+.1f}")
        pa4.metric("Positive setups", strong_count)
        pa5.metric("Risk positions", weak_count)
        display_columns = [
            "Khung chọn", "Trạng thái khung", "Số nến khung", "Signal khung", "Score khung",
            "Mã","Số lượng","Giá mua","Giá hiện tại","P&L (₫)","P&L (%)",
            "System Action","Signal","Score","Confidence (%)","Alignment (%)","Grade",
            "Regime","Stop Loss","Target 1","Risk Flags","Đánh giá",
        ]
        desk_dataframe(
            themed_dataframe(algorithm_df[display_columns]), width="stretch", hide_index=True,
            column_config={
                "Giá mua":st.column_config.NumberColumn("Giá mua",format="%.3f"),
                "Giá hiện tại":st.column_config.NumberColumn("Giá hiện tại",format="%.3f"),
                "P&L (₫)":st.column_config.NumberColumn("P&L (₫)",format="%+.0f ₫"),
                "P&L (%)":st.column_config.NumberColumn("P&L (%)",format="%+.2f%%"),
                "Score":st.column_config.ProgressColumn("Score",min_value=-100,max_value=100,format="%+.1f"),
            },
        )
        st.markdown(f"**{tr(LANG,'algo_conclusion')}**")
        if weak_count:
            st.warning(f"Có {weak_count}/{len(algorithm_df)} vị thế đang có tín hiệu suy yếu. Ưu tiên kiểm tra Stop Loss, tỷ trọng và thanh khoản trước khi giữ tiếp.")
        elif weighted_score >= 25:
            st.success("Danh mục đang nghiêng tích cực. Tiếp tục quản trị Stop Loss, không mua đuổi và chỉ tăng tỷ trọng khi RVOL cùng đa khung xác nhận.")
        else:
            st.info("Danh mục chưa có lợi thế đủ mạnh. Ưu tiên giữ tiền mặt dự phòng, hạn chế tăng tỷ trọng và chờ tín hiệu đa khung rõ hơn.")
        for _, holding_row in algorithm_df.iterrows():
            with st.expander(
                f"{holding_row['Mã']} · {holding_row['System Action']} · P&L {holding_row['P&L (%)']:+.2f}%"
            ):
                st.write(holding_row["Đánh giá"])
                st.caption(
                    f"Regime {holding_row['Regime']} · Score {holding_row['Score']:+.1f} · "
                    f"Confidence {holding_row['Confidence (%)']}% · Alignment {holding_row['Alignment (%)']}% · "
                    f"Stop Loss {fmt(holding_row['Stop Loss'],2)} · Target 1 {fmt(holding_row['Target 1'],2)}"
                )
                if holding_row["Risk Flags"]:
                    st.warning(holding_row["Risk Flags"])
    for algorithm_failure in portfolio_algorithm_result.get("failures", []):
        st.warning(algorithm_failure)

    st.divider()
    st.markdown("### ◈ Phân tích danh mục hợp đồng phái sinh")
    st.caption(
        "Nhập các vị thế phái sinh cần đánh giá gồm mã hợp đồng, LONG/SHORT, số hợp đồng và Entry. "
        "Hệ thống cập nhật quote, phân tích 15M–1D, Wyckoff, MA, RSI, RVOL, Fibonacci và quản trị rủi ro."
    )
    try:
        algorithm_futures_contracts, _ = load_futures_contracts_cached(0)
        algorithm_futures_symbols = [item["symbol"] for item in algorithm_futures_contracts]
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        algorithm_futures_symbols = ["VN30F1M", "VN100F1M"]
    futures_portfolio_store = PortfolioStore(STATE_DIR / "saved_futures_portfolios.json")
    saved_futures_portfolios = futures_portfolio_store.list()
    with st.expander(
        f"▣ Danh mục phái sinh đã lưu · {len(saved_futures_portfolios)}",
        expanded=bool(saved_futures_portfolios),
    ):
        if not saved_futures_portfolios:
            st.caption("Chưa có danh mục phái sinh nào được lưu trong hệ thống.")
        else:
            saved_futures_names = [item["name"] for item in saved_futures_portfolios]
            selected_saved_futures_name = st.selectbox(
                "Chọn danh mục phái sinh đã lưu", saved_futures_names,
                key="selected_saved_futures_portfolio",
                format_func=lambda name: next(
                    f"{name} · {len(item.get('positions',[]))} vị thế"
                    for item in saved_futures_portfolios if item["name"] == name
                ),
            )
            futures_open_col, futures_delete_col = st.columns([2, 1], gap="medium")
            if futures_open_col.button(
                "↗ MỞ DANH MỤC PHÁI SINH", width="stretch",
                key="open_saved_futures_portfolio",
            ):
                try:
                    loaded_futures_portfolio = futures_portfolio_store.get(selected_saved_futures_name)
                    loaded_futures_positions = [
                        item for item in loaded_futures_portfolio.get("positions", [])
                        if str(item.get("symbol", "")).upper() in algorithm_futures_symbols
                    ]
                    loaded_futures_symbols = [
                        str(item["symbol"]).upper() for item in loaded_futures_positions
                    ]
                    if not loaded_futures_symbols:
                        raise ValueError("Các hợp đồng đã lưu không còn trong danh sách hiện tại.")
                    st.session_state.futures_portfolio_symbols = loaded_futures_symbols
                    st.session_state.futures_portfolio_editor_symbols = tuple(loaded_futures_symbols)
                    st.session_state.pop("futures_portfolio_algorithm_editor", None)
                    st.session_state.futures_portfolio_algorithm_input = pd.DataFrame(
                        loaded_futures_positions,
                        columns=["symbol","side","quantity","entry_price"],
                    )
                    st.session_state.futures_portfolio_name_input = selected_saved_futures_name
                    st.toast(f"Đã mở danh mục phái sinh {selected_saved_futures_name}", icon="✅")
                    st.rerun()
                except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                    st.error(f"Không thể mở danh mục phái sinh: {exc}")
            with futures_delete_col:
                with st.popover("⌫ XÓA DANH MỤC", use_container_width=True):
                    st.warning(f"Danh mục phái sinh “{selected_saved_futures_name}” sẽ bị xóa.")
                    confirm_futures_portfolio_delete = st.checkbox(
                        "Xác nhận xóa", key=f"confirm_delete_futures_portfolio_{selected_saved_futures_name}"
                    )
                    if st.button(
                        "⌫ XÁC NHẬN XÓA", type="primary", width="stretch",
                        disabled=not confirm_futures_portfolio_delete,
                        key=f"delete_futures_portfolio_{selected_saved_futures_name}",
                    ):
                        try:
                            futures_portfolio_store.delete(selected_saved_futures_name)
                            st.toast(f"Đã xóa danh mục phái sinh {selected_saved_futures_name}", icon="🗑️")
                            st.rerun()
                        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                            st.error(f"Không thể xóa danh mục phái sinh: {exc}")
    selected_futures_portfolio_symbols = st.multiselect(
        "Hợp đồng phái sinh cần phân tích", algorithm_futures_symbols,
        default=algorithm_futures_symbols[:1], key="futures_portfolio_symbols",
        help="Chọn một hoặc nhiều hợp đồng; bảng bên dưới chỉ dùng để nhập LONG/SHORT, số HĐ và Entry.",
    )
    existing_futures_input = st.session_state.get("futures_portfolio_algorithm_input", pd.DataFrame())
    existing_futures_positions = {}
    if isinstance(existing_futures_input, pd.DataFrame) and not existing_futures_input.empty:
        existing_futures_positions = {
            str(row.get("symbol", "")).upper(): row
            for _, row in existing_futures_input.iterrows()
        }
    futures_symbols_signature = tuple(selected_futures_portfolio_symbols)
    if st.session_state.get("futures_portfolio_editor_symbols") != futures_symbols_signature:
        st.session_state.futures_portfolio_editor_symbols = futures_symbols_signature
        st.session_state.pop("futures_portfolio_algorithm_editor", None)
        st.session_state.futures_portfolio_algorithm_input = pd.DataFrame([
            {
                "symbol":code,
                "side":str(existing_futures_positions.get(code, {}).get("side", "LONG") or "LONG"),
                "quantity":int(float(existing_futures_positions.get(code, {}).get("quantity", 0) or 0)),
                "entry_price":float(existing_futures_positions.get(code, {}).get("entry_price", 0) or 0),
            }
            for code in selected_futures_portfolio_symbols
        ], columns=["symbol","side","quantity","entry_price"])
    elif "futures_portfolio_algorithm_input" not in st.session_state:
        st.session_state.futures_portfolio_algorithm_input = pd.DataFrame(
            columns=["symbol","side","quantity","entry_price"]
        )
    with st.form("futures_portfolio_algorithm_form", clear_on_submit=False):
        futures_portfolio_tf = st.selectbox("Khung phân tích danh mục phái sinh", ["MULTI", *FUTURES_CHART_TIMEFRAMES], key="futures_portfolio_analysis_timeframe")
        st.caption("Khung chọn được tính từ nến thật. Kế hoạch giao dịch đa khung và chu kỳ BOT không thay đổi.")
        futures_portfolio_name = st.text_input(
            "Tên danh mục phái sinh", key="futures_portfolio_name_input",
            placeholder="Ví dụ: Danh mục phái sinh trong ngày", max_chars=80,
        )
        futures_portfolio_input = desk_data_editor(
            st.session_state.futures_portfolio_algorithm_input,
            key="futures_portfolio_algorithm_editor", num_rows="fixed", hide_index=True,
            width="stretch",
            column_config={
                "symbol":st.column_config.TextColumn("Hợp đồng", disabled=True),
                "side":st.column_config.SelectboxColumn("Vị thế", options=["LONG","SHORT"], required=True),
                "quantity":st.column_config.NumberColumn("Số HĐ", min_value=0, step=1, format="%d"),
                "entry_price":st.column_config.NumberColumn("Entry", min_value=0.0, step=.1, format="%.1f"),
            },
        )
        save_futures_col, run_futures_col = st.columns([1, 2], gap="medium")
        save_futures_portfolio_requested = save_futures_col.form_submit_button(
            "↓ LƯU DANH MỤC PHÁI SINH", width="stretch",
        )
        run_futures_portfolio_algorithm = run_futures_col.form_submit_button(
            "◈ CHẠY PHÂN TÍCH DANH MỤC PHÁI SINH", type="primary", width="stretch",
        )
    if futures_portfolio_input is None:
        save_futures_portfolio_requested = run_futures_portfolio_algorithm = False
    if save_futures_portfolio_requested:
        try:
            futures_positions_to_save = [
                {
                    "symbol":str(row.get("symbol") or "").upper().strip(),
                    "side":str(row.get("side") or "").upper().strip(),
                    "quantity":int(float(row.get("quantity") or 0)),
                    "entry_price":float(row.get("entry_price") or 0),
                }
                for _, row in futures_portfolio_input.iterrows()
            ]
            saved_futures_item = futures_portfolio_store.save_futures(
                futures_portfolio_name, futures_positions_to_save
            )
            st.session_state.futures_portfolio_algorithm_input = futures_portfolio_input.copy()
            st.toast(
                f"Đã lưu danh mục phái sinh {saved_futures_item['name']} · "
                f"{len(saved_futures_item['positions'])} vị thế",
                icon="✅",
            )
            st.rerun()
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            st.error(f"Không thể lưu danh mục phái sinh: {exc}")
    if run_futures_portfolio_algorithm:
        st.session_state.futures_portfolio_algorithm_input = futures_portfolio_input.copy()
        valid_futures_holdings = []
        for _, futures_holding in futures_portfolio_input.iterrows():
            futures_symbol = str(futures_holding.get("symbol") or "").upper().strip()
            futures_side = str(futures_holding.get("side") or "LONG").upper().strip()
            try:
                futures_quantity = int(float(futures_holding.get("quantity") or 0))
                futures_entry = float(futures_holding.get("entry_price") or 0)
            except (TypeError, ValueError):
                continue
            if futures_symbol and futures_symbol.isalnum() and futures_side in {"LONG","SHORT"} and futures_quantity > 0 and futures_entry > 0:
                valid_futures_holdings.append({
                    "symbol":futures_symbol, "side":futures_side,
                    "quantity":futures_quantity, "entry_price":futures_entry,
                })
        if not valid_futures_holdings:
            st.error("Chưa có vị thế phái sinh hợp lệ. Cần nhập mã, LONG/SHORT, số HĐ và Entry lớn hơn 0.")
        else:
            futures_output, futures_failures = [], []
            futures_progress = st.progress(0, text=f"0/{len(valid_futures_holdings)}")
            for futures_index, futures_holding in enumerate(valid_futures_holdings):
                contract = futures_holding["symbol"]
                try:
                    contract_frames, _ = load_futures_bundle(
                        RAW_DIR / "futures", refresh=True, symbol=contract
                    )
                    contract_quote = load_futures_quote(contract)
                    contract_price = (
                        float(contract_quote["price"])
                        if contract_quote.get("status") == "OK"
                        else next(
                            float(contract_frames[tf].iloc[-1]["close"])
                            for tf in ("15M","1H","1D") if not contract_frames.get(tf,pd.DataFrame()).empty
                        )
                    )
                    contract_analysis = analyze_vn30f1m(contract_frames, symbol=contract)
                    if contract_analysis.get("status") != "OK":
                        raise ValueError("Insufficient futures data")
                    side_factor = 1 if futures_holding["side"] == "LONG" else -1
                    pnl_points = side_factor * (contract_price - futures_holding["entry_price"])
                    pnl_vnd = pnl_points * futures_holding["quantity"] * 100_000
                    notional = contract_price * futures_holding["quantity"] * 100_000
                    margin = notional * float(contract_analysis.get("config",{}).get("initial_margin_ratio",.17))
                    algorithm_action = str(contract_analysis.get("action","WAIT_CONFIRMATION"))
                    aligned = (
                        futures_holding["side"] == "LONG" and algorithm_action == "LONG"
                    ) or (
                        futures_holding["side"] == "SHORT" and algorithm_action == "SHORT"
                    )
                    if aligned:
                        futures_advice = "Vị thế cùng chiều tín hiệu; tiếp tục quản trị Stop Loss và chốt lời từng phần, không nhồi lệnh."
                    elif algorithm_action in {"LONG","SHORT"}:
                        futures_advice = "Tín hiệu hệ thống ngược chiều vị thế; ưu tiên thu hẹp rủi ro và đánh giá đóng vị thế."
                    else:
                        futures_advice = "Tín hiệu chưa đủ xác nhận; không tăng số hợp đồng và giữ kỷ luật Stop Loss."
                    plan = contract_analysis.get("plan",{})
                    futures_output.append({
                        **portfolio_frame_evidence(contract_analysis, futures_portfolio_tf, futures_frames=contract_frames),
                        "Hợp đồng":contract, "Vị thế":futures_holding["side"],
                        "Số HĐ":futures_holding["quantity"], "Entry":futures_holding["entry_price"],
                        "Giá hiện tại":contract_price, "P&L điểm":pnl_points, "P&L (₫)":pnl_vnd,
                        "Giá trị danh nghĩa (₫)":notional, "Ký quỹ ước tính (₫)":margin,
                        "System Action":algorithm_action, "Score":contract_analysis.get("score",0),
                        "Confidence (%)":contract_analysis.get("confidence",0),
                        "Alignment (%)":contract_analysis.get("alignment",0), "Regime":contract_analysis.get("regime"),
                        "Stop Loss":plan.get("stop_loss"), "TP1":plan.get("target_1"), "TP2":plan.get("target_2"),
                        "Đánh giá":futures_advice,
                    })
                except (OSError, ValueError, RuntimeError, KeyError, TypeError, StopIteration) as exc:
                    futures_failures.append(f"{contract}: {exc}")
                futures_progress.progress((futures_index + 1) / len(valid_futures_holdings), text=f"{futures_index + 1}/{len(valid_futures_holdings)}")
            futures_progress.empty()
            st.session_state.futures_portfolio_algorithm_result = {
                "timeframe":futures_portfolio_tf,
                "rows":futures_output, "failures":futures_failures,
                "run_at":pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").isoformat(),
            }

    futures_algorithm_result = st.session_state.get("futures_portfolio_algorithm_result", {})
    if futures_algorithm_result.get("rows"):
        futures_algorithm_df = pd.DataFrame(futures_algorithm_result["rows"])
        st.caption(pd.Timestamp(futures_algorithm_result.get('run_at')).strftime('%d/%m/%Y %H:%M:%S'))
        st.caption(f"Khung đã chạy: {futures_algorithm_result.get('timeframe', 'MULTI')} · System Action/Entry/Stop/TP vẫn là kế hoạch đa khung 15M/1H/1D.")
        fa1,fa2,fa3,fa4 = st.columns(4)
        fa1.metric("Tổng P&L phái sinh", f"{futures_algorithm_df['P&L (₫)'].sum():+,.0f} ₫")
        fa2.metric("Tổng giá trị danh nghĩa", f"{futures_algorithm_df['Giá trị danh nghĩa (₫)'].sum():,.0f} ₫")
        fa3.metric("Ký quỹ ước tính", f"{futures_algorithm_df['Ký quỹ ước tính (₫)'].sum():,.0f} ₫")
        fa4.metric("Số vị thế", len(futures_algorithm_df))
        desk_dataframe(
            themed_dataframe(futures_algorithm_df), width="stretch", hide_index=True,
            column_config={
                "P&L (₫)":st.column_config.NumberColumn("P&L (₫)",format="%+.0f ₫"),
                "P&L điểm":st.column_config.NumberColumn("P&L điểm",format="%+.1f"),
                "Score":st.column_config.ProgressColumn("Score",min_value=-100,max_value=100,format="%+.1f"),
            },
        )
        for _, futures_result_row in futures_algorithm_df.iterrows():
            with st.expander(
                f"{futures_result_row['Hợp đồng']} · {futures_result_row['Vị thế']} · "
                f"P&L {futures_result_row['P&L (₫)']:+,.0f} ₫"
            ):
                st.write(futures_result_row["Đánh giá"])
                st.caption(
                    f"{futures_result_row['Regime']} · {futures_result_row['System Action']} · "
                    f"Score {futures_result_row['Score']:+.1f} · Confidence {futures_result_row['Confidence (%)']}% · "
                    f"Stop Loss {fmt(futures_result_row['Stop Loss'],1)} · TP1 {fmt(futures_result_row['TP1'],1)} · TP2 {fmt(futures_result_row['TP2'],1)}"
                )
    for futures_algorithm_failure in futures_algorithm_result.get("failures", []):
        st.warning(futures_algorithm_failure)

if LANG != "vi":
    st.markdown(
        f'<div class="section-heading detailed-help-heading"><h2>{tr(LANG, "detailed_help")}</h2><span>Signal • Wyckoff • Indicators • Multi-timeframe</span></div>',
        unsafe_allow_html=True,
    )
    with st.expander(tr(LANG, "detailed_help"), expanded=False):
        st.markdown(guide(LANG))
    st.info(tr(LANG, "disclaimer"), icon="ℹ️")
    st.html('<div class="app-copyright" aria-label="Thiết kế">• Thiết kế bởi NhatkyPham</div>')
    st.stop()

st.markdown(
    f'<div class="section-heading detailed-help-heading"><h2>{tr(LANG, "detailed_help")}</h2><span>Signal • Wyckoff • Indicators • Multi-timeframe</span></div>',
    unsafe_allow_html=True,
)
help_left, help_right = st.columns(2, gap="medium")
with help_left:
    with st.expander("SIGNAL — Tín hiệu hành động", expanded=False):
        st.markdown("\n".join(f"- `{code}` — {description}" for code, description in SIGNAL_HELP.items()))
    with st.expander("EVENT — Sự kiện Wyckoff", expanded=False):
        st.markdown("\n".join(f"- `{code}` — {description}" for code, description in WYCKOFF_EVENT_HELP.items()))
with help_right:
    with st.expander("PHASE & BIAS — Trạng thái cấu trúc", expanded=False):
        st.markdown("**Phase — Giai đoạn thị trường**")
        st.markdown("\n".join(f"- `{code}` — {description}" for code, description in WYCKOFF_PHASE_HELP.items()))
        st.markdown("**Bias — Thiên hướng**")
        st.markdown("\n".join(f"- `{code}` — {description}" for code, description in WYCKOFF_BIAS_HELP.items()))
    with st.expander("MA • RSI • RVOL • MULTI-TIMEFRAME", expanded=False):
        st.markdown(
            """
- `MA` — Các đường trung bình động dùng để nhận diện hướng và độ bền của xu hướng. Trật tự MA20–MA200 càng đồng bộ, cấu trúc xu hướng càng rõ.
- `RSI14` — Động lượng 14 kỳ. Vùng cao cho thấy lực tăng mạnh nhưng có thể quá nóng; vùng thấp cho thấy yếu hoặc quá bán. Không dùng RSI đơn độc để vào lệnh.
- `RVOL` — Khối lượng tương đối so với trung bình. Trên `1.0x` là cao hơn bình thường; RVOL cao giúp xác nhận breakout, SOS hoặc SOW.
- `Signal Score` — Điểm tổng hợp từ MA, Wyckoff, RSI, động lượng, khối lượng và rủi ro trong từng khung.
- `Confidence` — Mức đầy đủ của bằng chứng đang có, không phải xác suất chắc chắn sinh lời.
- `1D / 1W / 1M / 1Y` — Mỗi nến lần lượt đại diện 1 ngày, 1 tuần, 1 tháng và 1 năm.
- `Đồng thuận đa khung` — Mức các khung cùng nghiêng về một hướng. Khi khung ngắn hạn và trung–dài hạn xung đột, hệ thống ưu tiên chờ xác nhận.
            """
        )
    with st.expander("PRO DECISION V3 — Cách đọc độ tin cậy", expanded=False):
        st.markdown(
            """
- `Confidence` — Độ mạnh của bằng chứng hiện có, kết hợp độ phủ dữ liệu, chất lượng tín hiệu từng khung, đồng thuận đa khung và độ lớn điểm tổng hợp. Đây không phải xác suất chắc chắn sinh lời.
- `Hạng A` — Bằng chứng rất rõ và đồng thuận cao. Hạng A vẫn có thể là “theo dõi” nếu chưa đạt trigger mua/bán.
- `Hạng B` — Bằng chứng khá tốt nhưng còn thiếu một điều kiện hoặc chưa đủ mạnh.
- `Hạng C` — Chỉ phù hợp theo dõi; có xung đột, tín hiệu yếu hoặc quality gate đang hạn chế.
- `Hạng D` — Không đủ điều kiện dùng cho giao dịch tự động.
- `Mức xung đột` — So sánh hướng của các khung có điểm đủ rõ; khung gần 0 được xem là trung tính thay vì tạo xung đột giả.
- `Yếu tố dẫn dắt` — Các nhóm MA, Wyckoff, RSI, momentum, volume và risk có đóng góp tuyệt đối lớn nhất vào quyết định.
            """
        )

st.info(
    "Hệ thống chỉ cung cấp thông tin phân tích định lượng và không cấu thành khuyến nghị đầu tư. "
    "Người sử dụng tự đánh giá, tự quyết định và chịu hoàn toàn trách nhiệm đối với các quyết định đầu tư của mình."
)
st.html('<div class="app-copyright" aria-label="Thiết kế">• Thiết kế bởi NhatkyPham</div>')
