"""Exercise the real report renderer without starting the app or any broker."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.ui_theme import FONT_STACK, palette


class PerformanceChartThemeTests(unittest.TestCase):
    def render(self, light, report):
        source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
        function = next(n for n in ast.parse(source).body
                        if isinstance(n, ast.FunctionDef) and n.name == "performance_analytics_chart")
        colors = palette(light)
        st = Mock()
        scope = {"pd": pd, "go": go, "make_subplots": make_subplots, "st": st,
                 "tr": lambda lang, key: key, "LANG": "vi", "UI_LIGHT": light,
                 "UI_COLORS": colors, "FONT_STACK": FONT_STACK,
                 "CHART_TEXT": colors["text"], "CHART_BG": colors["panel"],
                 "CHART_BORDER": colors["border"], "CHART_GRID": colors["grid"]}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), scope)
        scope[function.name](report, key="test_report", title="VN30F1M")
        args, kwargs = st.plotly_chart.call_args
        return args[0], kwargs

    def test_light_empty_report_has_explicit_readable_text(self):
        fig, options = self.render(True, {})
        self.assertIsNone(options["theme"])
        self.assertEqual(fig.layout.paper_bgcolor, "#ffffff")
        self.assertEqual(fig.layout.legend.font.color, "#1c1c1e")
        self.assertEqual(fig.layout.hoverlabel.bgcolor, "#ffffff")
        self.assertEqual(fig.layout.hoverlabel.font.color, "#1c1c1e")
        for name in ("xaxis", "xaxis2", "xaxis3", "yaxis", "yaxis2", "yaxis3"):
            self.assertEqual(fig.layout[name].tickfont.color, "#1c1c1e")
            self.assertEqual(fig.layout[name].tickfont.size, 13)
        for annotation in fig.layout.annotations:
            self.assertEqual(annotation.font.color, "#1c1c1e")

    def test_light_and_dark_preserve_report_values(self):
        report = {
            "capital_before_pnl_vnd": 100_000_000, "total_pnl_vnd": -200_000,
            "equity_curve": [{"time": "2026-08-26T09:00:00+07:00", "equity_vnd": 99_800_000,
                              "drawdown_pct": -.2, "kind": "MARK"}],
            "close_orders": [{"time": "2026-08-26T09:00:00+07:00", "pnl_vnd": -200_000}],
        }
        light, _ = self.render(True, report)
        dark, options = self.render(False, report)
        self.assertEqual(options["theme"], "streamlit")
        self.assertEqual(dark.layout.font.size, 12)
        self.assertEqual(dark.layout.paper_bgcolor, palette(False)["panel"])
        self.assertIsNone(dark.layout.yaxis.tickfont.color)
        for a, b in zip(light.data, dark.data):
            self.assertEqual(list(a.y), list(b.y))
        self.assertEqual(len(light.data), len(dark.data))
        self.assertEqual(light.layout.yaxis3.tickformat, ".2f")
        self.assertEqual(light.layout.yaxis3.ticksuffix, "%")


if __name__ == "__main__":
    unittest.main()
