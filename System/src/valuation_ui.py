"""Shared Light/Dark, Paper/Live valuation presentation in five languages."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .ui_theme import FONT_STACK, palette

LANGS = ("vi", "en", "zh", "ru", "de")
TEXT = {
    "title": ("Định giá cổ phiếu", "Equity valuation", "股票估值", "Оценка акций", "Aktienbewertung"),
    "refresh": ("Cập nhật định giá", "Update valuation", "更新估值", "Обновить оценку", "Bewertung aktualisieren"),
    "loading": ("Đang tải dữ liệu định giá…", "Loading valuation…", "正在加载估值…", "Загрузка оценки…", "Bewertung wird geladen…"),
    "source": ("Nguồn", "Source", "来源", "Источник", "Quelle"),
    "period": ("Kỳ báo cáo", "Report period", "报告期", "Отчётный период", "Berichtszeitraum"),
    "fetched": ("Lần tải thành công", "Last successful fetch", "上次成功获取", "Последняя загрузка", "Letzter erfolgreicher Abruf"),
    "sector": ("Ngành ICB cấp 3", "ICB level 3 sector", "ICB三级行业", "Отрасль ICB уровня 3", "ICB-Sektor Ebene 3"),
    "snapshot": ("Số liệu theo kỳ do nguồn cung cấp, không phải P/E, P/B tính lại theo giá trực tiếp. ROE và tăng trưởng giữ nguyên kỳ/đơn vị của nguồn, không tự quy đổi năm hoặc gán là YoY.", "Provider-period snapshots, not P/E or P/B recalculated from live prices. ROE and growth retain provider periods/units; no automatic annualisation or YoY assumption.", "数据为来源报告期快照，并非实时价格重算。ROE及增长保留来源周期和单位，不自动年化或假定同比。", "Снимки данных за период источника, не пересчёт P/E и P/B по текущей цене. ROE и рост не пересчитываются в годовые и не считаются YoY автоматически.", "Periodenwerte des Anbieters, keine Neuberechnung mit Live-Kursen. ROE und Wachstum behalten Anbieterperioden und -einheiten; keine automatische Annualisierung oder YoY-Annahme."),
    "growth": ("Tăng trưởng LN theo nguồn (%)", "Provider profit growth (%)", "来源利润增长 (%)", "Рост прибыли по источнику (%)", "Gewinnwachstum laut Anbieter (%)"),
    "conclusion": ("Đánh giá kết hợp kỹ thuật và định giá", "Technical + valuation assessment", "技术与估值综合评估", "Техническая и стоимостная оценка", "Technische und fundamentale Einordnung"),
    "method": ("Cách đánh giá và giới hạn", "Method and limitations", "方法与限制", "Метод и ограничения", "Methode und Grenzen"),
    "method_body": ("So sánh trung vị tối thiểu 3 kỳ trước và 3 mã khác cùng ngành, cùng nguồn, cùng kỳ. Chênh lệch ±20% chỉ là ngưỡng mô tả tương đối, chưa được kiểm định khả năng sinh lời. Mẫu ngành chỉ gồm các mã đã tải, không đại diện toàn ngành. EPS/vốn chủ không dương, báo cáo quá 200 ngày hoặc cache quá 2 ngày không được dùng để kết luận định giá thấp. Không sửa tín hiệu, độ tin cậy, Entry/Stop/TP hay lệnh BOT. P/E, P/B thấp không đồng nghĩa cổ phiếu đáng mua.", "Compare medians from at least 3 prior periods and 3 other same-sector, same-source, same-period stocks. ±20% is a descriptive threshold, not a validated return predictor. Peers are downloaded stocks, not the whole sector. Nonpositive earnings/equity, reports over 200 days old or caches over 2 days old cannot support a low-valuation conclusion. Signals, confidence, Entry/Stop/TP and bot orders remain unchanged. Low multiples do not imply a buy.", "至少比较3个历史期和3只同业、同来源、同报告期股票的中位数。±20%仅为描述阈值，未经收益验证。样本仅包含已下载股票。盈利或净资产非正、报告超过200天或缓存超过2天，不支持低估结论。不改变信号、置信度、Entry/Stop/TP或机器人订单。低估值不等于买入。", "Медианы минимум 3 прошлых периодов и 3 других акций той же отрасли, источника и периода. ±20% — описательный порог, не прогноз доходности. Выборка ограничена загруженными акциями. Неположительная прибыль/капитал, отчёт старше 200 дней или кеш старше 2 дней не подтверждают низкую оценку. Сигналы, уверенность, Entry/Stop/TP и заявки бота не меняются. Низкие мультипликаторы не означают покупку.", "Mediane aus mindestens 3 Vorperioden und 3 anderen Aktien desselben Sektors, Anbieters und Zeitraums. ±20% ist eine beschreibende, nicht renditevalidierte Schwelle. Vergleichsgruppe nur aus geladenen Aktien. Nichtpositive Gewinne/Eigenkapital, Berichte über 200 Tage oder Cache über 2 Tage alt erlauben kein positives Bewertungsurteil. Signale, Konfidenz, Entry/Stop/TP und Bot-Orders bleiben unverändert. Niedrige Multiplikatoren sind kein Kaufsignal."),
    "metric": ("Chỉ số", "Metric", "指标", "Показатель", "Kennzahl"),
    "basis": ("Cơ sở so sánh", "Comparison basis", "比较基准", "База сравнения", "Vergleichsbasis"),
    "median": ("Trung vị", "Median", "中位数", "Медиана", "Median"),
    "count": ("Số mẫu", "Sample size", "样本数", "Размер выборки", "Stichprobe"),
    "deviation": ("Chênh lệch (%)", "Deviation (%)", "偏差 (%)", "Отклонение (%)", "Abweichung (%)"),
    "HISTORY": ("Lịch sử cùng mã", "Own history", "自身历史", "История акции", "Eigene Historie"),
    "PEERS": ("Mẫu cùng ngành đã tải", "Downloaded sector peers", "已加载同业样本", "Загруженные аналоги", "Geladene Branchenwerte"),
    "LOWER_RELATIVE": ("Thấp hơn mức tham chiếu", "Below reference", "低于参考值", "Ниже ориентира", "Unter Referenz"),
    "HIGHER_RELATIVE": ("Cao hơn mức tham chiếu", "Above reference", "高于参考值", "Выше ориентира", "Über Referenz"),
    "NEAR_REFERENCE": ("Gần mức tham chiếu", "Near reference", "接近参考值", "Около ориентира", "Nahe Referenz"),
    "MIXED": ("Các so sánh trái chiều", "Mixed comparisons", "比较结果不一致", "Противоречивые сравнения", "Gemischte Vergleiche"),
    "CAUTION": ("Cần thận trọng", "Caution", "需谨慎", "Осторожность", "Vorsicht"),
    "UNAVAILABLE": ("Chưa đủ dữ liệu hợp lệ", "No usable data", "无有效数据", "Нет пригодных данных", "Keine geeigneten Daten"),
    "INSUFFICIENT": ("Chưa đủ mẫu so sánh", "Insufficient comparisons", "比较样本不足", "Недостаточно сравнений", "Zu wenige Vergleiche"),
    "INCOMPLETE": ("Chưa đủ bằng chứng định giá; chỉ tham khảo kỹ thuật, không nâng độ tin cậy.", "Valuation evidence incomplete; technical context only, no confidence boost.", "估值证据不足；仅参考技术，不提高置信度。", "Данных оценки мало; только технический контекст, без повышения уверенности.", "Bewertungsdaten unvollständig; nur technischer Kontext, keine höhere Konfidenz."),
    "RISK_REVIEW": ("Ưu tiên rà soát dữ liệu, sức khỏe tài chính và rủi ro trước khi quyết định.", "Review data, financial health and risk before deciding.", "决策前审查数据、财务状况和风险。", "До решения проверьте данные, финансы и риск.", "Vor einer Entscheidung Daten, Finanzlage und Risiken prüfen."),
    "VALUE_TREND_CONFLICT": ("Định giá tương đối thấp nhưng kỹ thuật yếu: cảnh giác bẫy giá trị, chờ xác nhận.", "Lower relative valuation but weak technicals: watch for value traps; wait for confirmation.", "相对估值低但技术弱：警惕价值陷阱，等待确认。", "Оценка ниже, но техника слаба: риск ловушки стоимости, ждите подтверждения.", "Niedrigere Bewertung, schwache Technik: Value-Trap-Risiko; Bestätigung abwarten."),
    "WATCH_CONFIRMATION": ("Định giá tương đối và kỹ thuật cùng hỗ trợ theo dõi; vẫn cần kiểm tra tài chính và điều kiện Entry/Stop, không tự động mua.", "Relative valuation and technicals support monitoring; still verify financials and Entry/Stop conditions, no automatic buy.", "估值与技术支持观察；仍需检查财务及Entry/Stop条件，不自动买入。", "Оценка и техника поддерживают наблюдение; проверьте финансы и Entry/Stop, без автопокупки.", "Bewertung und Technik unterstützen Beobachtung; Finanzen und Entry/Stop prüfen, kein automatischer Kauf."),
    "WAIT_CONFIRMATION": ("Chưa có lợi thế kết hợp rõ ràng; chờ tín hiệu xác nhận và giữ kỷ luật rủi ro.", "No clear combined advantage; wait for confirmation and respect risk limits.", "综合优势不明确；等待确认并遵守风险限制。", "Явного совместного преимущества нет; ждите подтверждения, соблюдайте риск-лимиты.", "Kein klarer kombinierter Vorteil; Bestätigung abwarten und Risikolimits einhalten."),
    "NO_DATA": ("Không có dữ liệu tài chính.", "No financial data.", "无财务数据。", "Нет финансовых данных.", "Keine Finanzdaten."),
    "FUTURE_REPORT": ("Kỳ báo cáo nằm trong tương lai, không sử dụng.", "Future report period excluded.", "排除未来报告期。", "Будущий период исключён.", "Zukünftiger Berichtszeitraum ausgeschlossen."),
    "STALE_REPORT": ("Báo cáo đã quá 200 ngày.", "Report older than 200 days.", "报告已超过200天。", "Отчёт старше 200 дней.", "Bericht älter als 200 Tage."),
    "FETCH_FAILED": ("Không tải được dữ liệu mới; bản lưu chỉ để tham khảo.", "Refresh failed; cached data for reference only.", "更新失败；缓存仅供参考。", "Обновление не удалось; кеш только для справки.", "Aktualisierung fehlgeschlagen; Cache nur zur Orientierung."),
    "STALE_CACHE": ("Dữ liệu chưa cập nhật trong hơn 2 ngày.", "Data not refreshed for over 2 days.", "数据超过2天未更新。", "Нет обновления более 2 дней.", "Seit über 2 Tagen nicht aktualisiert."),
    "CACHE_WRITE_FAILED": ("Không lưu được bộ nhớ đệm.", "Could not save cache.", "无法保存缓存。", "Не удалось сохранить кеш.", "Cache konnte nicht gespeichert werden."),
    "NONPOSITIVE_EARNINGS": ("P/E hoặc EPS không dương: không diễn giải là rẻ.", "Nonpositive P/E or EPS: not evidence of cheapness.", "P/E或EPS非正：不能视为便宜。", "P/E или EPS неположительны: не признак дешевизны.", "P/E oder EPS nicht positiv: kein Hinweis auf günstige Bewertung."),
    "NONPOSITIVE_EQUITY": ("P/B hoặc BVPS không dương: cần rà soát vốn chủ.", "Nonpositive P/B or BVPS: review equity.", "P/B或BVPS非正：检查净资产。", "P/B или BVPS неположительны: проверьте капитал.", "P/B oder BVPS nicht positiv: Eigenkapital prüfen."),
    "MISSING_RATIOS": ("Thiếu P/E hoặc P/B.", "P/E or P/B missing.", "缺少P/E或P/B。", "Нет P/E или P/B.", "P/E oder P/B fehlt."),
    "MISSING_ROE": ("ROE: nguồn chưa cung cấp giá trị hợp lệ cho kỳ này.", "ROE: no valid provider value for this period.", "ROE：本期来源无有效值。", "ROE: нет пригодного значения за период.", "ROE: kein gültiger Anbieterwert für diesen Zeitraum."),
    "MISSING_GROWTH": ("Tăng trưởng lợi nhuận: nguồn chưa cung cấp giá trị hợp lệ cho kỳ này.", "Profit growth: no valid provider value for this period.", "利润增长：本期来源无有效值。", "Рост прибыли: нет пригодного значения за период.", "Gewinnwachstum: kein gültiger Anbieterwert für diesen Zeitraum."),
    "MISSING_DEBT_EQUITY": ("Debt/Equity: nguồn chưa cung cấp giá trị hợp lệ cho kỳ này; không điền bằng 0.", "Debt/Equity: no valid provider value for this period; not replaced with zero.", "Debt/Equity：本期无有效值，不填零。", "Debt/Equity: нет пригодного значения; ноль не подставляется.", "Debt/Equity: kein gültiger Wert; wird nicht durch null ersetzt."),
    "WEAK_ROE": ("ROE không dương: cần rà soát khả năng sinh lời.", "Nonpositive ROE: review profitability.", "ROE非正：检查盈利能力。", "ROE неположителен: проверьте рентабельность.", "ROE nicht positiv: Rentabilität prüfen."),
    "PROFIT_DECLINE": ("Nguồn ghi nhận tăng trưởng lợi nhuận âm: thận trọng với định giá thấp.", "Provider reports declining profit: be cautious with low valuation.", "来源显示利润下降：谨慎看待低估值。", "Источник сообщает о снижении прибыли: осторожнее с низкой оценкой.", "Anbieter meldet Gewinnrückgang: niedrige Bewertung vorsichtig beurteilen."),
    "PARTIAL_FUNDAMENTALS": ("Thiếu một phần ROE, tăng trưởng hoặc Debt/Equity; không suy diễn dữ liệu thiếu.", "ROE, growth or Debt/Equity partially missing; no imputation.", "ROE、增长或Debt/Equity部分缺失，不推测。", "Не все ROE, рост или Debt/Equity доступны; без подстановки.", "ROE, Wachstum oder Debt/Equity teilweise fehlend; keine Schätzung."),
    "NO_SECTOR": ("Chưa xác định được ngành.", "Sector unavailable.", "行业未知。", "Отрасль неизвестна.", "Sektor unbekannt."),
    "FEW_PEERS": ("Chưa đủ 3 mã cùng ngành, nguồn và kỳ trong bộ nhớ đệm.", "Fewer than 3 cached peers with matching sector, source and period.", "同业、同来源和报告期缓存不足3只。", "Менее 3 аналогов отрасли, источника и периода в кеше.", "Weniger als 3 passende Branchenwerte im Cache."),
    "SHORT_HISTORY": ("Chưa đủ 3 kỳ lịch sử hợp lệ trước kỳ hiện tại.", "Fewer than 3 valid prior periods.", "有效历史期不足3个。", "Менее 3 пригодных прошлых периодов.", "Weniger als 3 gültige Vorperioden."),
    "AMBIGUOUS_PERIODS": ("Nguồn có kỳ báo cáo trùng/không rõ nhãn; không sử dụng để kết luận định giá.", "Duplicate/ambiguous provider periods; valuation conclusion disabled.", "来源报告期重复或模糊；禁用估值结论。", "Дубли/неоднозначные периоды источника; вывод об оценке отключён.", "Doppelte/unklare Anbieterperioden; Bewertungsurteil deaktiviert."),
}


def vt(lang, key):
    return TEXT[key][LANGS.index(lang) if lang in LANGS else 0]


METRIC_HELP = {
    "pe": ("P/E = Giá cổ phiếu / EPS. Cho biết giá đang bằng bao nhiêu lần thu nhập trên mỗi cổ phiếu. EPS không dương thì P/E không phù hợp để kết luận rẻ. So sánh cùng ngành, cùng kỳ và chất lượng lợi nhuận; đây là tỷ số nguồn cung cấp, không tính lại theo giá realtime.", "P/E = share price / EPS. Compare like-for-like peers and earnings quality. Nonpositive EPS cannot support a cheapness conclusion. Provider snapshot, not a live-price recalculation.", "P/E=股价/EPS。需比较同业及盈利质量；EPS非正不能据此判断便宜。本值为来源快照，非实时重算。", "P/E = цена акции / EPS. Сравнивайте аналоги и качество прибыли. Неположительный EPS не доказывает дешевизну. Снимок источника, не пересчёт по текущей цене.", "P/E = Aktienkurs / EPS. Vergleich mit passenden Branchenwerten und Gewinnqualität. Nichtpositive EPS belegen keine günstige Bewertung. Anbieterwert, nicht mit Live-Kurs neu berechnet."),
    "pb": ("P/B = Giá cổ phiếu / BVPS. So sánh giá với giá trị sổ sách mỗi cổ phiếu. P/B thấp chưa chắc rẻ nếu tài sản kém chất lượng hoặc ROE thấp. Vốn chủ không dương thì không dùng để đánh giá rẻ.", "P/B = share price / BVPS. A low value can reflect weak assets or low ROE; nonpositive equity cannot support cheapness.", "P/B=股价/BVPS。低值可能来自资产质量差或ROE低；净资产非正不能用于低估判断。", "P/B = цена / BVPS. Низкий показатель может отражать слабые активы или ROE; неположительный капитал не доказывает дешевизну.", "P/B = Kurs / BVPS. Niedrige Werte können schwache Aktiva oder ROE widerspiegeln; nichtpositives Eigenkapital erlaubt kein günstiges Urteil."),
    "roe": ("ROE = Lợi nhuận / Vốn chủ sở hữu bình quân. Đo khả năng sinh lời trên vốn chủ. Hệ thống giữ nguyên kỳ và cách tính của nguồn; không tự quy đổi ROE quý thành năm. ROE cao do đòn bẩy vẫn cần thận trọng.", "ROE measures profit relative to average equity. Provider period and method retained; quarterly values are not automatically annualised. Leverage can inflate ROE.", "ROE衡量利润相对平均净资产。保留来源周期，不自动年化；杠杆可能抬高ROE。", "ROE — прибыль к среднему капиталу. Период источника сохраняется, квартальный ROE не annualize. Долг может завышать ROE.", "ROE misst Gewinn im Verhältnis zum durchschnittlichen Eigenkapital. Anbieterperiode bleibt erhalten, Quartale werden nicht annualisiert. Hebel kann ROE erhöhen."),
    "debt_equity": ("Debt/Equity so sánh nợ với vốn chủ theo định nghĩa của nguồn; đơn vị là lần. Không dùng một ngưỡng chung cho ngân hàng và doanh nghiệp công nghiệp. Dấu — nghĩa là thiếu dữ liệu, không phải không có nợ.", "Debt/Equity compares debt with equity under the provider definition, in multiples. No universal threshold for banks and industrials. — means missing, not debt-free.", "Debt/Equity按来源定义衡量债务/净资产，单位倍。银行与工业不共用阈值。—表示缺失，不表示无债务。", "Debt/Equity — долг к капиталу по определению источника. Нет общего порога для банков и промышленности. — означает отсутствие данных, не долга.", "Debt/Equity vergleicht Schulden und Eigenkapital nach Anbieterdefinition. Keine gemeinsame Schwelle für Banken und Industrie. — bedeutet fehlende Daten, nicht schuldenfrei."),
    "eps": ("EPS là lợi nhuận trên mỗi cổ phiếu, đơn vị VND. Nguồn có thể dùng EPS 4 quý gần nhất. EPS âm là doanh nghiệp đang ghi nhận lỗ theo cơ sở tính đó; không dùng P/E âm để kết luận rẻ.", "EPS is earnings per share in VND; the provider may use trailing four quarters. Negative EPS denotes a loss under that basis, not cheapness.", "EPS为每股收益，单位VND；来源可能使用最近四季度。负EPS表示该口径亏损，非便宜。", "EPS — прибыль на акцию в VND; источник может использовать 4 последних квартала. Отрицательный EPS означает убыток, не дешевизну.", "EPS ist Gewinn je Aktie in VND; der Anbieter kann vier zurückliegende Quartale verwenden. Negative EPS bedeuten Verlust, nicht günstige Bewertung."),
    "bvps": ("BVPS là giá trị sổ sách vốn chủ trên mỗi cổ phiếu, đơn vị VND. Đây là số liệu kế toán, không phải giá bán tài sản hay giá mục tiêu cổ phiếu.", "BVPS is book equity per share in VND. It is an accounting value, not liquidation value or a share-price target.", "BVPS为每股账面净资产，单位VND，不是清算价值或目标股价。", "BVPS — балансовый капитал на акцию в VND, не ликвидационная стоимость и не целевая цена.", "BVPS ist Buch-Eigenkapital je Aktie in VND, kein Liquidationswert oder Kursziel."),
    "profit_growth": ("Tăng trưởng lợi nhuận (%) được giữ theo kỳ so sánh của nguồn. Không tự giả định là YoY. Cần kiểm tra lợi nhuận bất thường và mức nền kỳ trước; tăng trưởng cao không bảo đảm giá tăng.", "Profit growth (%) retains the provider comparison basis, not assumed YoY. Review one-off gains and the base period; growth does not guarantee price gains.", "利润增长保留来源比较口径，不默认同比。检查一次性收益和基期；增长不保证股价上涨。", "Рост прибыли сохраняет базу сравнения источника, не обязательно YoY. Проверьте разовые доходы и базу; рост не гарантирует доходность.", "Gewinnwachstum behält die Vergleichsbasis des Anbieters, nicht automatisch YoY. Einmaleffekte und Basis prüfen; Wachstum garantiert keine Kursgewinne."),
}


def metric_popover(col, key, title, value, lang):
    display = "—" if value is None else f"{value:,.2f}"
    with col.popover(f"{title} · {display}", width="stretch"):
        st.markdown(f"**{title}**")
        st.write(METRIC_HELP[key][LANGS.index(lang) if lang in LANGS else 0])


def render_valuation(result, lang="vi", light=False):
    v = result["valuation"]
    p = palette(light)
    st.markdown(f"**{vt(lang, v['status'])}**")
    st.caption(" · ".join(f"{vt(lang, label)}: {v.get(field) or '—'}" for label, field in (
        ("source", "source"), ("period", "period"), ("fetched", "fetched_at"), ("sector", "sector"))))
    with st.container(key="valuation_snapshot_notice"):
        st.info(vt(lang, "snapshot"))
    metrics = v["metrics"]
    with st.container(key="valuation_metric_cards"):
        for col, key, title in zip(st.columns(4), ("pe", "pb", "roe", "debt_equity"), ("P/E", "P/B", "ROE (%)", "Debt/Equity")):
            value = metrics.get(key)
            metric_popover(col, key, title, value, lang)
        for col, key, title in zip(st.columns(3), ("eps", "bvps", "profit_growth"), ("EPS (VND)", "BVPS (VND)", vt(lang, "growth"))):
            value = metrics.get(key)
            metric_popover(col, key, title, value, lang)
    with st.container(key="valuation_combined_assessment"):
        with st.container(key="valuation_combined_copy"):
            st.markdown(f"**{vt(lang, 'conclusion')}**")
            st.write(vt(lang, result["valuation_conclusion"]))
        if v["warnings"]:
            with st.container(key="valuation_warning_list"):
                for warning in v["warnings"]:
                    st.warning(vt(lang, warning))
    rows = [{vt(lang, "metric"): c["metric"], vt(lang, "basis"): vt(lang, c["basis"]),
             vt(lang, "median"): c["median"], vt(lang, "count"): c["count"],
             vt(lang, "deviation"): c["deviation_pct"]} for c in v["comparisons"]]
    st.table(pd.DataFrame(rows).style.format(precision=2, na_rep="—").hide(axis="index"))
    for c in v["comparisons"]:
        if c["symbols"]:
            st.caption(f"{c['metric']} · {vt(lang, 'PEERS')}: {', '.join(c['symbols'])}")
    if len(v["history"]) >= 2:
        with st.container(key="valuation_history_charts"):
            for col, key in zip(st.columns(2), ("pe", "pb")):
                fig = go.Figure(go.Scatter(x=[r["period"] for r in v["history"]], y=[r.get(key) for r in v["history"]],
                                          mode="lines+markers", connectgaps=False, line={"color": p["purple" if key == "pe" else "blue"], "width": 2.5}))
                fig.update_layout(title="P/E" if key == "pe" else "P/B", height=240, autosize=True, margin=dict(l=30,r=20,t=45,b=35),
                                  template="plotly_white" if light else "plotly_dark", paper_bgcolor=p["panel"], plot_bgcolor=p["panel"],
                                  font={"family": FONT_STACK, "color": p["text"], "size": 12}, showlegend=False)
                fig.update_xaxes(type="category", gridcolor=p["grid"], tickfont={"color":p["text"]}, automargin=True)
                fig.update_yaxes(gridcolor=p["grid"], tickfont={"color":p["text"]}, automargin=True)
                col.plotly_chart(fig, width="stretch", theme=None, key=f"valuation_{v['symbol']}_{key}", config={"displayModeBar":False, "responsive":False})
    with st.expander(vt(lang, "method")):
        st.write(vt(lang, "method_body"))
