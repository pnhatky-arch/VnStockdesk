import ast
import copy
from pathlib import Path
import unittest
from types import SimpleNamespace

import pandas as pd
import streamlit as st

from src.desk_grid import grid_payload, validated_edits, LABELS

ROOT = Path(__file__).resolve().parents[1]


class DeskGridTests(unittest.TestCase):
    def setUp(self):
        self.data = pd.DataFrame({"symbol": ["ACB", "BID"], "quantity": [500, 100], "price": [20.876, 30.1]})
        self.config = {
            "symbol": st.column_config.TextColumn(disabled=True),
            "quantity": st.column_config.NumberColumn(min_value=0, format="%d"),
            "price": st.column_config.NumberColumn(min_value=0, format="%.3f"),
        }
        _, self.payload = grid_payload(self.data, self.config, True)
        self.value = {"revision": self.payload["revision"], "rows": copy.deepcopy(self.payload["rows"])}

    def test_exact_price_and_immutable_symbol(self):
        self.value["rows"][0].update(price="21.987", symbol="TAMPERED", quantity="600")
        result = validated_edits(self.data, self.payload, self.value)
        self.assertEqual(result.iloc[0].price, 21.987)
        self.assertEqual(result.iloc[0].symbol, "ACB")
        self.assertEqual(result.iloc[0].quantity, 600)
        self.assertEqual(self.data.iloc[0].price, 20.876)

    def test_stale_response_does_not_replace_new_portfolio(self):
        self.value["revision"] = "old"
        self.value["rows"][0]["price"] = "1"
        pd.testing.assert_frame_equal(validated_edits(self.data, self.payload, self.value), self.data)

    def test_rejects_invalid_numbers_without_partial_results(self):
        for bad in ("", None, "NaN", "Infinity", "-1", True, "abc"):
            with self.subTest(bad=bad):
                self.value["rows"][0]["price"] = bad
                with self.assertRaises(ValueError):
                    validated_edits(self.data, self.payload, self.value)
        self.value["rows"][0]["price"] = "21.987"
        self.value["rows"][0]["quantity"] = "1.5"
        with self.assertRaises(ValueError):
            validated_edits(self.data, self.payload, self.value)

    def test_rejects_changed_row_count(self):
        self.value["rows"].pop()
        with self.assertRaises(ValueError):
            validated_edits(self.data, self.payload, self.value)

    def test_futures_side_is_validated(self):
        data = pd.DataFrame({"side": ["LONG"]})
        _, payload = grid_payload(data, {"side": st.column_config.SelectboxColumn(options=["LONG", "SHORT"])}, True)
        value = {"revision": payload["revision"], "rows": [{"side": "SHORT"}]}
        self.assertEqual(validated_edits(data, payload, value).iloc[0].side, "SHORT")
        value["rows"][0]["side"] = "SELL"
        with self.assertRaises(ValueError):
            validated_edits(data, payload, value)

    def test_missing_values_timestamps_and_styler(self):
        data = pd.DataFrame({"time": [pd.Timestamp("2026-08-26")], "price": [float("nan")]})
        _, payload = grid_payload(SimpleNamespace(data=data))
        self.assertIsNone(payload["rows"][0]["price"])
        self.assertTrue(payload["rows"][0]["time"].startswith("2026-08-26"))

    def test_numeric_columns_are_inferred_and_vietnamese_money_format_is_preserved(self):
        data = pd.DataFrame({"Mã": ["ACB"], "Lãi/lỗ chưa thực hiện": [1250000.0]})
        _, payload = grid_payload(data, {
            "Lãi/lỗ chưa thực hiện": {
                "type_config": {"type": "number", "format": "vn_signed_vnd"},
            },
        })
        columns = {column["name"]: column for column in payload["columns"]}
        self.assertEqual(columns["Mã"]["type"], "text")
        self.assertEqual(columns["Lãi/lỗ chưa thực hiện"]["type"], "number")
        self.assertEqual(columns["Lãi/lỗ chưa thực hiện"]["format"], "vn_signed_vnd")

    def test_translation_does_not_reset_edits(self):
        self.config["price"]["label"] = "Giá mua"
        _, translated = grid_payload(self.data, self.config, True)
        self.assertEqual(translated["revision"], self.payload["revision"])
        self.assertEqual(set(LABELS), {"vi", "en", "zh", "ru", "de"})

    def test_all_app_grids_use_theme_owned_renderer(self):
        tree = ast.parse((ROOT / "app.py").read_text())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                if isinstance(n.func.value, ast.Name) and n.func.value.id == "st":
                    self.assertNotIn(n.func.attr, ("dataframe", "data_editor"))
        source = (ROOT / "app.py").read_text()
        self.assertIn("if portfolio_input is None:", source)
        self.assertIn("if futures_portfolio_input is None:", source)

    def test_frontend_has_no_injected_html_or_network(self):
        js = (ROOT / "assets/desk_grid/grid.js").read_text()
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("fetch(", js)
        self.assertIn("event.source!==parent", js)
        self.assertIn("event.origin!==parentOrigin", js)
        self.assertIn('col.format==="vn_signed_vnd"', js)
        css = (ROOT / "assets/desk_grid/grid.css").read_text()
        self.assertIn("background:var(--panel)", css)
        self.assertIn("color:var(--text)", css)
        self.assertIn("focus-visible", css)
        self.assertIn("td.number.positive{color:var(--green)", css)
        self.assertIn("td.number.negative{color:var(--red)", css)


if __name__ == "__main__":
    unittest.main()
