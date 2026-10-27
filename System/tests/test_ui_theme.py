import ast
import re
import unittest
from pathlib import Path

from src.ui_theme import palette, signal_colors, stylesheet

ROOT = Path(__file__).resolve().parents[1]


def luminance(hex_color):
    values = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
    return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))


class AppearanceTests(unittest.TestCase):
    def test_same_tokens_in_both_appearances(self):
        self.assertEqual(palette(True).keys(), palette(False).keys())
        p = palette(True)
        p["text"] = "changed"
        self.assertNotEqual(p["text"], palette(True)["text"])

    def test_text_and_semantic_colors_meet_normal_text_contrast(self):
        for light in (True, False):
            p = palette(light)
            for surface in ("bg", "panel", "panel2", "panel3"):
                for foreground in ("text", "muted", "blue", "green", "red", "purple", "amber", "orange"):
                    a, b = sorted((luminance(p[surface]), luminance(p[foreground])))
                    with self.subTest(light=light, surface=surface, foreground=foreground):
                        self.assertGreaterEqual((b + .05) / (a + .05), 4.5)

    def test_css_tokens_resolve_and_styles_are_not_markdown(self):
        for light in (True, False):
            css = stylesheet(light)
            defined = set(re.findall(r"(--[\w-]+)\s*:", css))
            used = set(re.findall(r"var\((--[\w-]+)\)", css))
            self.assertFalse(used - defined)
            self.assertIn("prefers-reduced-motion", css)
            self.assertIn("focus-visible", css)
            self.assertIn('height:3px', css)
            self.assertIn('[role="tablist"]', css)
            self.assertIn('[role="tab"][aria-selected="true"]', css)
            self.assertIn('[data-testid="stTextInputRootElement"]', css)
            self.assertIn('[data-testid="stSelectbox"] input', css)
        tree = ast.parse((ROOT / "app.py").read_text())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        themes = [n for n in calls if n.args and isinstance(n.args[0], ast.Call)
                  and isinstance(n.args[0].func, ast.Name) and n.args[0].func.id == "stylesheet"]
        self.assertEqual(len(themes), 1)
        self.assertEqual(themes[0].func.attr, "html")

    def test_signal_semantics_are_consistent(self):
        for light in (True, False):
            colors = signal_colors(light)
            self.assertEqual(colors["BUY"], palette(light)["green"])
            self.assertEqual(colors["SELL"], palette(light)["red"])
            self.assertNotEqual(colors["BUY"], colors["SELL"])

    def test_canvas_headers_do_not_receive_incomplete_styler_overrides(self):
        tree = ast.parse((ROOT / "app.py").read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "themed_dataframe")
        source = ast.unparse(function)
        self.assertNotIn("map_index", source)
        self.assertNotIn("set_table_styles", source)

    def test_valuation_help_covers_every_metric_and_language(self):
        from src.valuation_ui import METRIC_HELP, LANGS
        self.assertEqual(set(METRIC_HELP), {"pe", "pb", "roe", "eps", "bvps", "debt_equity", "profit_growth"})
        for explanations in METRIC_HELP.values():
            self.assertEqual(len(explanations), len(LANGS))
            self.assertTrue(all(len(text) > 20 for text in explanations))

    def test_validation_label_has_no_version_in_any_language(self):
        from src.i18n import tr
        for lang in ("vi", "en", "zh", "ru", "de"):
            self.assertNotIn("V3", tr(lang, "validation"))

    def test_vietnamese_futures_tab_uses_full_name(self):
        from src.i18n import tr
        self.assertEqual(tr("vi", "futures_desk"), "Hợp đồng tương lai")
        self.assertNotIn("HĐTL", tr("vi", "futures_desk").upper())

    def test_portal_toasts_pair_foreground_and_background(self):
        css = stylesheet(True)
        rule = re.search(r'\[data-testid="stToast"\]\s*\{([^}]+)\}', css)
        self.assertIsNotNone(rule)
        self.assertIn('background:var(--panel)!important', rule[1])
        self.assertIn('color:var(--text)!important', rule[1])
        self.assertIn('[data-testid="stToast"] button', css)

    def test_caption_and_primary_button_contrast(self):
        css = stylesheet(True)
        self.assertRegex(css, r'\[data-testid="stCaptionContainer"\]\s*\{[^}]*opacity:1!important')
        self.assertRegex(css, r'button\[data-testid="stBaseButton-primaryFormSubmit"\] p\s*\{[^}]*color:#ffffff!important')

    def test_collapsed_sidebar_always_has_a_visible_reopen_control(self):
        for light in (True, False):
            css = stylesheet(light)
            self.assertIn('[data-testid="stToolbar"] { visibility:visible; }', css)
            self.assertIn('[data-testid="stExpandSidebarButton"]', css)
            self.assertNotIn('[data-testid="stToolbar"] { visibility:hidden; }', css)

    def test_credit_is_plain_static_footer(self):
        css = stylesheet(True)
        rule = re.search(r'\.app-copyright\s*\{([^}]+)\}', css)
        self.assertIsNotNone(rule)
        self.assertIn('position:static', rule[1])
        self.assertIn('background:transparent', rule[1])
        self.assertIn('border:0', rule[1])
        self.assertIn('box-shadow:none', rule[1])
        self.assertNotIn('position:fixed', rule[1])
        app_source = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertIn('• Thiết kế bởi NhatkyPham', app_source)
        self.assertNotIn("tr(LANG, 'brand_credit')", app_source)

    def test_download_data_has_main_tab_and_no_data_recovery_panel(self):
        app_source = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertIn('tab9, tab10 = st.tabs', app_source)
        self.assertIn('with tab10:', app_source)
        self.assertIn('render_data_download_panel(LANG, "recovery_download")', app_source)
        self.assertIn('render_data_download_panel(LANG, "main_download")', app_source)

    def test_expander_surfaces_follow_app_theme(self):
        css = stylesheet(True)
        for selector, surface in (
            ('[data-testid="stExpander"] summary', 'panel'),
            ('[data-testid="stExpander"] details[open]>summary', 'panel2'),
            ('[data-testid="stExpander"] details[open]>summary:hover', 'panel3'),
            ('[data-testid="stExpanderDetails"]', 'panel'),
        ):
            rule = re.search(re.escape(selector) + r'\s*\{([^}]+)\}', css)
            self.assertIsNotNone(rule, selector)
            self.assertIn(f'background:var(--{surface})', rule[1])
            self.assertIn('color:var(--text)', rule[1])

    def test_strategy_formula_is_plain_wrapped_text(self):
        tree = ast.parse((ROOT / "app.py").read_text())
        formulas = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute) and n.func.attr == 'code'
                    and 'position_formula' in ast.unparse(n)]
        self.assertEqual(len(formulas), 1)
        kwargs = {k.arg: ast.literal_eval(k.value) for k in formulas[0].keywords}
        self.assertIsNone(kwargs['language'])
        self.assertTrue(kwargs['wrap_lines'])

    def test_futures_chart_symbol_is_always_named(self):
        tree = ast.parse((ROOT / "app.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "lightweight_futures_execution_chart":
                self.assertLessEqual(len(node.args), 4)
                self.assertIn("symbol", [kw.arg for kw in node.keywords])

    def test_paper_overview_summarizes_the_whole_portfolio(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('total_quantity = sum(', app_source)
        self.assertIn('position_count = len(paper_positions)', app_source)
        self.assertIn("tr(LANG,'paper_total_quantity')", app_source)
        self.assertNotIn("tr(LANG,'quantity')} {symbol}", app_source)
        from src.i18n import tr
        for lang in ("vi", "en", "zh", "ru", "de"):
            self.assertNotEqual(tr(lang, "paper_total_quantity"), "paper_total_quantity")
            self.assertIn("3", tr(lang, "paper_positions_summary", count=3))

    def test_cards_use_content_aware_workstation_spacing(self):
        css = stylesheet(True)
        self.assertIn('--space-3: 12px', css)
        self.assertIn('gap: var(--space-3)', css)
        self.assertIn('container-type:inline-size', css)
        self.assertIn('overflow-wrap:anywhere', css)
        self.assertIn('white-space:normal!important', css)
        self.assertNotIn('.cockpit { padding:18px; margin:0; min-height:300px', css)

    def test_valuation_charts_have_a_stable_frame(self):
        css = stylesheet(True)
        self.assertIn('.st-key-valuation_history_charts [data-testid="stPlotlyChart"]', css)
        self.assertIn('height:242px; min-height:242px; max-height:242px', css)
        source = (ROOT / 'src' / 'valuation_ui.py').read_text(encoding='utf-8')
        self.assertIn('key="valuation_history_charts"', source)
        self.assertIn('"responsive":False', source)

    def test_workstation_surfaces_are_flat_and_consistent(self):
        css = stylesheet(True)
        self.assertIn('--radius-card: 10px', css)
        self.assertIn('--radius-control: 7px', css)
        self.assertIn('backdrop-filter:none', css)
        self.assertIn('.sidebar-section-label', css)
        self.assertIn('[role="dialog"]:has(.trade-fill-alert)', css)
        self.assertIn('@media(max-width:768px)', css)
        app_source = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertGreaterEqual(app_source.count('sidebar-section-label'), 4)

    def test_risk_levels_have_distinct_semantic_icons(self):
        app_source = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertIn('"LOW":"Thấp"', app_source)
        self.assertIn('"MEDIUM":"Trung bình"', app_source)
        self.assertIn('"HIGH":"Cao"', app_source)
        self.assertIn('.risk-confirm-icon.risk-low{--risk-accent:#16a34a}', app_source)
        self.assertIn('.risk-confirm-icon.risk-high{--risk-accent:#dc2626}', app_source)


if __name__ == "__main__":
    unittest.main()
