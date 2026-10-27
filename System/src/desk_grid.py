"""Theme-owned HTML tables. No native canvas colors, network or trading actions.

Editors are form widgets: each input updates the pending form value, not the app.
Only whitelisted editable cells are accepted back from the browser.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.ui_theme import palette

_component = components.declare_component(
    "desk_grid", path=str(Path(__file__).resolve().parents[1] / "assets" / "desk_grid")
)

LABELS = {
    "vi": ["Tìm trong bảng…", "Xuất CSV", "Trước", "Sau", "dòng", "Không có dữ liệu", "Giá trị không hợp lệ"],
    "en": ["Search table…", "Export CSV", "Previous", "Next", "rows", "No data", "Invalid value"],
    "zh": ["搜索表格…", "导出 CSV", "上一页", "下一页", "行", "暂无数据", "无效值"],
    "ru": ["Поиск в таблице…", "Экспорт CSV", "Назад", "Далее", "строк", "Нет данных", "Недопустимое значение"],
    "de": ["Tabelle durchsuchen…", "CSV exportieren", "Zurück", "Weiter", "Zeilen", "Keine Daten", "Ungültiger Wert"],
}


def grid_payload(data, column_config=None, editable=False):
    frame = data if isinstance(data, pd.DataFrame) else data.data
    # Pandas normalizes timestamps, numpy scalars and missing values to safe JSON.
    records = json.loads(frame.to_json(orient="records", date_format="iso"))
    columns = []
    for name in frame.columns:
        cfg = (column_config or {}).get(name, {})
        if cfg is None:
            continue
        cfg = {"label": cfg} if isinstance(cfg, str) else cfg
        spec = cfg.get("type_config") or {}
        inferred_type = "number" if pd.api.types.is_numeric_dtype(frame[name]) else "text"
        columns.append({
            "name": str(name), "label": cfg.get("label") or str(name),
            "help": cfg.get("help") or "", "type": spec.get("type", inferred_type),
            "editable": editable and not cfg.get("disabled", False),
            "required": bool(cfg.get("required")),
            **{k: spec.get(k) for k in ("format", "min_value", "max_value", "step", "options")},
        })
    schema = [{k: v for k, v in col.items() if k not in ("label", "help")} for col in columns]
    revision = hashlib.sha256(json.dumps([records, schema], sort_keys=True).encode()).hexdigest()
    return frame, {"rows": records, "columns": columns, "revision": revision}


def validated_edits(frame, payload, value):
    """Reject stale/tampered edits; never change row identity or disabled columns."""
    result = frame.copy()
    if not isinstance(value, dict) or value.get("revision") != payload["revision"]:
        return result
    rows = value.get("rows")
    if not isinstance(rows, list) or len(rows) != len(frame):
        raise ValueError("Invalid row count")
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("Invalid row")
        for col in payload["columns"]:
            if not col["editable"]:
                continue
            name = col["name"]
            cell = row.get(name)
            if col["type"] == "number":
                if cell is None or isinstance(cell, bool) or str(cell).strip() == "":
                    raise ValueError(name)
                try:
                    cell = float(cell)
                except (ValueError, TypeError):
                    raise ValueError(name) from None
                if not math.isfinite(cell):
                    raise ValueError(name)
                if col["min_value"] is not None and cell < col["min_value"]:
                    raise ValueError(name)
                if col["max_value"] is not None and cell > col["max_value"]:
                    raise ValueError(name)
                # Integer quantities must not be silently truncated. Step is an
                # input increment, not a lot-size rule (matches native editor).
                if col["format"] == "%d":
                    if not cell.is_integer():
                        raise ValueError(name)
                    cell = int(cell)
            elif col["type"] == "selectbox":
                if cell not in (col["options"] or []):
                    raise ValueError(name)
            else:
                cell = "" if cell is None else str(cell)
                if col["required"] and not cell:
                    raise ValueError(name)
            result.iat[i, result.columns.get_loc(name)] = cell
    return result


def _render(data, *, key, column_config=None, editable=False, height=None, light=None, lang=None):
    frame, payload = grid_payload(data, column_config, editable)
    selected_light = st.session_state.get("ui_light_mode", False) if light is None else light
    language = lang or st.session_state.get("ui_language", "vi")
    previous = st.session_state.get(key)
    draft_rows = None
    if (editable and isinstance(previous, dict)
            and previous.get("revision") == payload["revision"]
            and isinstance(previous.get("rows"), list)
            and len(previous["rows"]) == len(frame)):
        draft_rows = previous["rows"]
    value = _component(
        **payload, colors=palette(selected_light), light=selected_light,
        labels=LABELS.get(language, LABELS["vi"]), editable=editable,
        draft_rows=draft_rows,
        max_height=height if isinstance(height, int) and height > 0 else 430,
        key=key, default=None,
    )
    if editable:
        try:
            return validated_edits(frame, payload, value)
        except ValueError as error:
            st.error(f"{LABELS.get(language, LABELS['vi'])[6]}: {error}")
            # Keep the form and its submit buttons rendered so users can fix
            # invalid cells. None is fail-closed, never a fallback portfolio.
            return None
    return None


def desk_dataframe(data, *, width=None, hide_index=True, column_config=None, height=None, key=None, light=None, lang=None):
    caller = inspect.currentframe().f_back
    key = key or f"desk_table:{caller.f_code.co_filename}:{caller.f_lineno}"
    return _render(data, key=key, column_config=column_config, height=height, light=light, lang=lang)


def desk_data_editor(data, *, key, num_rows="fixed", hide_index=True, width=None, column_config=None, light=None, lang=None):
    if num_rows != "fixed":
        raise ValueError("Only fixed portfolio rows are supported")
    return _render(data, key=key, column_config=column_config, editable=True, light=light, lang=lang)
