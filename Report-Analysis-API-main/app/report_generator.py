# report_generator.py
# Generates HTML and PDF reports following the exact 11-section format.

import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image as RLImage, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sc(label: str) -> str:
    """Status string → hex color."""
    if any(x in label for x in ("🔴", "❌", "Critical", "High", "Slow")):
        return "#e74c3c"
    if any(x in label for x in ("⚠️", "Warning", "Moderate", "Attention")):
        return "#e67e22"
    if any(x in label for x in ("✅", "Normal", "Healthy", "Fast", "Low")):
        return "#27ae60"
    return "#95a5a6"


def _rl_color(label: str):
    return colors.HexColor(_sc(label))


def _na(v, suffix="", decimals=1):
    if v is None or v == "N/A":
        return "N/A"
    try:
        return f"{round(float(v), decimals)}{suffix}"
    except (TypeError, ValueError):
        return str(v)


def _chart(trend_data, title, ylabel, color="steelblue", warn_line=None):
    if not trend_data:
        return None
    ts  = [datetime.fromtimestamp(p["ts"], tz=timezone.utc) for p in trend_data]
    val = [p["value"] for p in trend_data]
    fig, ax = plt.subplots(figsize=(7, 2.6))
    ax.plot(ts, val, color=color, linewidth=1.8, zorder=3)
    ax.fill_between(ts, val, alpha=0.12, color=color)
    if warn_line is not None:
        ax.axhline(warn_line, color="#e67e22", linewidth=1,
                   linestyle="--", label=f"Threshold ({warn_line})")
        ax.legend(fontsize=7)
    ax.set_title(title, fontsize=10, fontweight="bold", pad=5)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.tick_params(axis="both", labelsize=7)
    ax.grid(True, linestyle="--", alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    buf.seek(0)
    return buf


# ── HTML Report ───────────────────────────────────────────────────────────────

def generate_html_report(report: dict) -> str:
    r   = report
    fs  = r["final_status"]
    km  = r["key_metrics"]
    pf  = r["performance"]
    ea  = r["error_analysis"]
    res = r["resource"]
    gc  = r["gc_analysis"]
    stb = r["stability"]
    fc  = fs["color"]

    def badge(label):
        c = _sc(label)
        return f'<span class="badge" style="background:{c}">{label}</span>'

    def kv(label, value):
        return f'<tr><td class="lbl">{label}</td><td>{value}</td></tr>'

    def section(title, content):
        return f'<div class="section"><h2>{title}</h2>{content}</div>'

    # Section 3 — Key Metrics
    def _km_val(v, suffix=""):
        """Show value or a styled monitoring-gap warning."""
        if v is None or str(v).startswith("N/A"):
            return '<span style="color:#e67e22;font-weight:600">⚠️ Data not available — monitoring needs improvement</span>'
        try:
            return f"{round(float(v), 1)}{suffix}"
        except (TypeError, ValueError):
            return str(v)

    missing_banner = ""
    if km.get("missing_metrics"):
        missing_banner = (
            '<div class="gap-banner">⚠️ <b>Monitoring Gap Detected:</b> '
            f'The following metrics are missing: <b>{", ".join(km["missing_metrics"])}</b>. '
            'Add the required Prometheus exporters to get full visibility. '
            'Use <b>Grafana</b> for dashboards and <b>Alertmanager</b> for alerts.</div>'
        )

    km_html = missing_banner + f"""<table class="metrics-grid">
      {kv("Total Requests", _km_val(km.get("total_requests")))}
      {kv("Total Errors", _km_val(km.get("total_errors")))}
      {kv("Error Rate", _km_val(km.get("error_rate_pct"), "%"))}
      {kv("Avg Response Time", _km_val(km.get("avg_response_ms"), " ms"))}
      {kv("CPU Usage", _km_val(km.get("cpu_percent"), "%"))}
      {kv("Memory Usage", _km_val(km.get("memory_mb"), " MB"))}
      {kv("System Uptime", km.get("uptime", "N/A"))}
    </table>"""

    # Section 4 — Performance
    pf_html = f"""
      {badge(pf.get("label","❓"))}
      <table>
        {kv("Average Response Time", _na(pf.get("avg_ms"), " ms"))}
        {kv("95th Percentile (p95)", _na(pf.get("p95_ms"), " ms"))}
        {kv("99th Percentile (p99)", _na(pf.get("p99_ms"), " ms"))}
        {kv("Classification", pf.get("classification","N/A"))}
        {kv("Trend", pf.get("trend","—"))}
      </table>
      <p class="note">{pf.get("explanation","")}</p>"""

    # Section 5 — Errors
    ea_html = f"""
      {badge(ea.get("label","❓") + " " + ea.get("status",""))}
      <table>
        {kv("Total Errors", _na(ea.get("total_errors"), ""))}
        {kv("Total Requests", _na(ea.get("total_requests"), ""))}
        {kv("Error Rate", _na(ea.get("error_rate_pct"), "%"))}
        {kv("Trend", ea.get("trend","—"))}
      </table>
      <p class="note">{ea.get("impact","")}</p>"""

    # Section 6 — Resources
    res_html = f"""
      <table>
        {kv("Memory Usage", f'{_na(res.get("memory_mb"), " MB")} &nbsp; {res.get("memory_label","")} {res.get("memory_cat","")}')}
        {kv("Memory Trend", res.get("memory_trend","—"))}
        {kv("CPU Usage", f'{_na(res.get("cpu_percent"), "%")} &nbsp; {res.get("cpu_label","")} {res.get("cpu_cat","")}')}
        {kv("CPU Trend", res.get("cpu_trend","—"))}
      </table>
      <p class="note">{res.get("memory_note","")}</p>
      <p class="note">{res.get("cpu_note","")}</p>"""

    # Section 7 — GC
    gc_html = f"""
      {badge(gc.get("label","❓") + " " + gc.get("status",""))}
      <table>
        {kv("Objects Collected", _na(gc.get("collected"), ""))}
        {kv("Uncollectable Objects", _na(gc.get("uncollectable"), ""))}
        {kv("Memory Leak Risk", gc.get("leak_risk","N/A"))}
        {kv("Memory Trend", gc.get("memory_trend","—"))}
      </table>
      <p class="note">{gc.get("explanation","")}</p>"""

    # Section 8 — Stability
    stb_html = f"""
      <table>
        {kv("System Uptime", f'{stb.get("uptime","N/A")} &nbsp; {stb.get("uptime_label","")}')}
        {kv("Open File Descriptors", _na(stb.get("open_fds"), ""))}
        {kv("Max File Descriptors", _na(stb.get("max_fds"), ""))}
        {kv("FD Usage", _na(stb.get("fd_pct"), "%") + f' &nbsp; {stb.get("fd_label","")}')}
      </table>
      <p class="note">{stb.get("uptime_note","")}</p>
      <p class="note">{stb.get("fd_note","")}</p>"""

    # Section 9 — Business Impact
    impacts_html = "".join(
        f'<p class="impact-item">{i}</p>'
        for i in r.get("business_impact", [])
    )

    # Section 10 — Actions
    priority_color = {"Critical": "#e74c3c", "High": "#e74c3c",
                      "Medium": "#e67e22", "Low": "#27ae60"}
    actions_html = ""
    for a in r.get("actions", []):
        pc = priority_color.get(a.get("priority", ""), "#95a5a6")
        actions_html += f"""
        <div class="action-card" style="border-left:4px solid {pc}">
          <span class="priority-badge" style="background:{pc}">{a.get("priority","")}</span>
          <p>⚠️ <b>Problem:</b> {a.get("problem","")}</p>
          <p>📉 <b>Impact:</b> {a.get("impact","")}</p>
          <p>🛠 <b>Action:</b> {a.get("action","")}</p>
        </div>"""
    if not actions_html:
        actions_html = '<p class="note">✅ No actions required. System is healthy.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>EMS Health Report — {r['job']}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',Arial,sans-serif;background:#f0f2f5;color:#2c3e50;padding:28px}}
  h1{{font-size:1.7em;margin-bottom:4px}}
  h2{{font-size:1em;font-weight:700;color:#2980b9;margin-bottom:12px;
      padding-bottom:4px;border-bottom:2px solid #eaf0fb}}
  .header{{background:#fff;padding:22px 26px;border-radius:10px;
           box-shadow:0 2px 8px rgba(0,0,0,.08);margin-bottom:18px}}
  .meta{{color:#7f8c8d;font-size:.83em;margin-top:5px;line-height:1.8}}
  .final-status{{font-size:1.2em;font-weight:700;color:{fc};
                 margin-top:12px;padding:10px 14px;background:#f8f9fa;
                 border-radius:6px;border-left:5px solid {fc}}}
  .exec{{background:#fff;padding:16px 20px;border-radius:10px;
         box-shadow:0 2px 8px rgba(0,0,0,.08);margin-bottom:18px;
         font-size:.93em;line-height:1.65;color:#444}}
  .section{{background:#fff;padding:18px 22px;border-radius:10px;
            box-shadow:0 2px 8px rgba(0,0,0,.07);margin-bottom:16px}}
  .metrics-grid{{width:100%;border-collapse:collapse;font-size:.9em}}
  .metrics-grid td{{padding:7px 10px;border-bottom:1px solid #f0f0f0}}
  table{{width:100%;border-collapse:collapse;font-size:.85em}}
  td{{padding:5px 8px;border-bottom:1px solid #f0f0f0;vertical-align:top}}
  .lbl{{color:#7f8c8d;width:40%;font-weight:600}}
  .badge{{display:inline-block;font-size:.78em;padding:3px 10px;
          border-radius:12px;color:#fff;margin-bottom:10px}}
  .note{{font-size:.84em;color:#555;margin-top:8px;padding:6px 10px;
         background:#f8f9fa;border-radius:4px;line-height:1.5}}
  .impact-item{{padding:8px 12px;margin-bottom:8px;background:#f8f9fa;
                border-radius:6px;font-size:.88em;line-height:1.6;
                border-left:3px solid #3498db}}
  .action-card{{padding:12px 14px;margin-bottom:12px;background:#fafafa;
                border-radius:6px;font-size:.87em;line-height:1.7}}
  .action-card p{{margin-bottom:3px}}
  .priority-badge{{display:inline-block;font-size:.72em;padding:2px 8px;
                   border-radius:10px;color:#fff;margin-bottom:6px}}
  .gap-banner{{background:#fef9e7;border-left:4px solid #e67e22;padding:10px 14px;
               border-radius:4px;font-size:.84em;margin-bottom:12px;line-height:1.5}}
  .footer{{text-align:center;color:#bbb;font-size:.76em;margin-top:22px}}
</style>
</head>
<body>

<!-- Section 1: Project Details -->
<div class="header">
  <h1>📊 Application Health Report</h1>
  <div class="meta">
    <b>Project Name:</b> {r['job']} ({r['instance']})<br>
    <b>Time Range:</b> {r['time_range']}<br>
    <b>Report Generated At:</b> {r['fetched_at']}
  </div>
  <div class="final-status">{fs['label']} — {fs['message']}</div>
</div>

<!-- Section 2: Executive Summary -->
<div class="exec">
  <b>Executive Summary</b><br>{r['executive_summary']}
</div>

<!-- Section 3: Key Metrics -->
{section("3. Key Metrics Summary", km_html)}

<!-- Section 4: Performance -->
{section("4. Performance Analysis", pf_html)}

<!-- Section 5: Errors -->
{section("5. Error Analysis", ea_html)}

<!-- Section 6: Resources -->
{section("6. Resource Usage Analysis", res_html)}

<!-- Section 7: GC -->
{section("7. Memory & GC Analysis", gc_html)}

<!-- Section 8: Stability -->
{section("8. System Stability", stb_html)}

<!-- Section 9: Business Impact -->
{section("9. Business Impact", impacts_html)}

<!-- Section 10: Actions -->
{section("10. Recommended Actions", actions_html)}

<!-- Section 11: Final Status -->
<div class="section">
  <h2>11. Final Status</h2>
  <div style="font-size:1.4em;font-weight:700;color:{fc};padding:12px 0">
    {fs['label']}
  </div>
  <p style="font-size:.9em;color:#555;margin-top:4px">{fs['message']}</p>
  <p style="font-size:.82em;color:#888;margin-top:8px;font-style:italic">
    Justification: {fs.get('justification','')}
  </p>
</div>

<div class="footer">Generated by EMS Backend &nbsp;·&nbsp; Powered by Prometheus</div>
</body></html>"""


# ── PDF Report ────────────────────────────────────────────────────────────────

def generate_pdf_report(report: dict) -> bytes:
    r   = report
    raw = r.get("_raw", {})
    fs  = r["final_status"]
    km  = r["key_metrics"]
    pf  = r["performance"]
    ea  = r["error_analysis"]
    res = r["resource"]
    gc  = r["gc_analysis"]
    stb = r["stability"]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=1.8*cm, leftMargin=1.8*cm,
                            topMargin=1.8*cm, bottomMargin=1.8*cm)
    styles = getSampleStyleSheet()
    story  = []

    def S(name, **kw):
        return ParagraphStyle(name, parent=styles["Normal"], **kw)

    title_s   = S("T",  fontSize=18, fontName="Helvetica-Bold",
                  textColor=colors.HexColor("#1a252f"), spaceAfter=4)
    h2_s      = S("H2", fontSize=11, fontName="Helvetica-Bold",
                  textColor=colors.HexColor("#2980b9"), spaceBefore=12, spaceAfter=5)
    body_s    = S("B",  fontSize=9,  leading=14, spaceAfter=3)
    small_s   = S("Sm", fontSize=8,  leading=12, textColor=colors.HexColor("#555555"),
                  spaceAfter=3)
    exec_s    = S("Ex", fontSize=9,  leading=14, spaceAfter=4,
                  backColor=colors.HexColor("#f8f9fa"),
                  borderPadding=(6, 8, 6, 8))
    footer_s  = S("Ft", fontSize=7,  textColor=colors.HexColor("#aaaaaa"),
                  alignment=TA_CENTER)

    def hr(thick=1, c="#dee2e6"):
        return HRFlowable(width="100%", thickness=thick,
                          color=colors.HexColor(c), spaceAfter=5)

    def two_col_table(rows, col1=4.5*cm, col2=12.5*cm):
        t = Table(rows, colWidths=[col1, col2])
        t.setStyle(TableStyle([
            ("FONTNAME",  (0,0), (-1,-1), "Helvetica"),
            ("FONTNAME",  (0,0), (0,-1),  "Helvetica-Bold"),
            ("FONTSIZE",  (0,0), (-1,-1), 9),
            ("TEXTCOLOR", (0,0), (0,-1),  colors.HexColor("#555")),
            ("VALIGN",    (0,0), (-1,-1), "TOP"),
            ("ROWBACKGROUNDS", (0,0), (-1,-1),
             [colors.HexColor("#f8f9fa"), colors.white]),
            ("GRID",    (0,0), (-1,-1), 0.3, colors.HexColor("#e0e0e0")),
            ("PADDING", (0,0), (-1,-1), 6),
        ]))
        return t

    # ── Cover / Section 1 ──
    story.append(Paragraph("APPLICATION HEALTH REPORT", title_s))
    story.append(hr(2, "#2980b9"))
    story.append(Spacer(1, 0.15*cm))
    story.append(two_col_table([
        ["Project Name", f"{r['job']} ({r['instance']})"],
        ["Time Range",   r["time_range"]],
        ["Generated At", r["fetched_at"]],
    ]))
    story.append(Spacer(1, 0.25*cm))

    # Final status banner
    fc_rl = _rl_color(fs["label"])
    story.append(Paragraph(
        fs["label"],
        S("FS", fontSize=13, fontName="Helvetica-Bold", textColor=fc_rl, spaceAfter=3)
    ))
    story.append(Paragraph(fs["message"], small_s))
    story.append(hr())

    # ── Section 2: Executive Summary ──
    story.append(Paragraph("2. Executive Summary", h2_s))
    story.append(Paragraph(r["executive_summary"], exec_s))
    story.append(Spacer(1, 0.2*cm))

    # ── Section 3: Key Metrics ──
    story.append(Paragraph("3. Key Metrics Summary", h2_s))
    # Monitoring gap banner
    if km.get("missing_metrics"):
        gap_s = S("Gap", fontSize=8, leading=12,
                  backColor=colors.HexColor("#fef9e7"),
                  textColor=colors.HexColor("#e67e22"),
                  borderPadding=(5, 7, 5, 7), spaceAfter=6)
        story.append(Paragraph(
            f"⚠️ Monitoring Gap: Missing metrics — {', '.join(km['missing_metrics'])}. "
            "Add required Prometheus exporters. Use Grafana for dashboards, "
            "Alertmanager for alerts.",
            gap_s
        ))

    def km_val(v, suffix=""):
        if v is None or str(v).startswith("N/A"):
            return "⚠️ Data not available — monitoring needs improvement"
        try:
            return f"{round(float(v), 1)}{suffix}"
        except (TypeError, ValueError):
            return str(v)

    story.append(two_col_table([
        ["Total Requests",    km_val(km.get("total_requests"))],
        ["Total Errors",      km_val(km.get("total_errors"))],
        ["Error Rate",        km_val(km.get("error_rate_pct"), "%")],
        ["Avg Response Time", km_val(km.get("avg_response_ms"), " ms")],
        ["CPU Usage",         km_val(km.get("cpu_percent"), "%")],
        ["Memory Usage",      km_val(km.get("memory_mb"), " MB")],
        ["System Uptime",     str(km.get("uptime", "N/A"))],
    ]))
    story.append(Spacer(1, 0.2*cm))

    # ── Section 4: Performance ──
    pf_color = _rl_color(pf.get("label", ""))
    story.append(KeepTogether([
        Paragraph("4. Performance Analysis", h2_s),
        Paragraph(
            f"{pf.get('label','')} {pf.get('classification','')}",
            S("PF", fontSize=10, fontName="Helvetica-Bold", textColor=pf_color, spaceAfter=4)
        ),
        two_col_table([
            ["Avg Response Time", str(_na(pf.get("avg_ms"), " ms"))],
            ["p95 Response Time", str(_na(pf.get("p95_ms"), " ms"))],
            ["p99 Response Time", str(_na(pf.get("p99_ms"), " ms"))],
            ["Trend",             pf.get("trend", "—")],
        ]),
        Spacer(1, 0.1*cm),
        Paragraph(pf.get("explanation", ""), small_s),
        Spacer(1, 0.15*cm),
    ]))

    # ── Section 5: Error Analysis ──
    ea_color = _rl_color(ea.get("label", ""))
    story.append(KeepTogether([
        Paragraph("5. Error Analysis", h2_s),
        Paragraph(
            f"{ea.get('label','')} {ea.get('status','')}",
            S("EA", fontSize=10, fontName="Helvetica-Bold", textColor=ea_color, spaceAfter=4)
        ),
        two_col_table([
            ["Total Errors",    str(_na(ea.get("total_errors"), ""))],
            ["Total Requests",  str(_na(ea.get("total_requests"), ""))],
            ["Error Rate",      str(_na(ea.get("error_rate_pct"), "%"))],
            ["Trend",           ea.get("trend", "—")],
        ]),
        Spacer(1, 0.1*cm),
        Paragraph(ea.get("impact", ""), small_s),
        Spacer(1, 0.15*cm),
    ]))

    # ── Section 6: Resources ──
    story.append(Paragraph("6. Resource Usage Analysis", h2_s))
    story.append(two_col_table([
        ["Memory Usage",  f"{_na(res.get('memory_mb'), ' MB')}  {res.get('memory_label','')} {res.get('memory_cat','')}"],
        ["Memory Trend",  res.get("memory_trend", "—")],
        ["CPU Usage",     f"{_na(res.get('cpu_percent'), '%')}  {res.get('cpu_label','')} {res.get('cpu_cat','')}"],
        ["CPU Trend",     res.get("cpu_trend", "—")],
    ]))
    story.append(Spacer(1, 0.1*cm))
    story.append(Paragraph(res.get("memory_note", ""), small_s))
    story.append(Paragraph(res.get("cpu_note", ""), small_s))
    story.append(Spacer(1, 0.15*cm))

    # ── Section 7: GC ──
    gc_color = _rl_color(gc.get("label", ""))
    story.append(KeepTogether([
        Paragraph("7. Memory & GC Analysis", h2_s),
        Paragraph(
            f"{gc.get('label','')} {gc.get('status','')}",
            S("GC", fontSize=10, fontName="Helvetica-Bold", textColor=gc_color, spaceAfter=4)
        ),
        two_col_table([
            ["Objects Collected",    str(_na(gc.get("collected"), ""))],
            ["Uncollectable Objects", str(_na(gc.get("uncollectable"), ""))],
            ["Memory Leak Risk",     gc.get("leak_risk", "N/A")],
            ["Memory Trend",         gc.get("memory_trend", "—")],
        ]),
        Spacer(1, 0.1*cm),
        Paragraph(gc.get("explanation", ""), small_s),
        Spacer(1, 0.15*cm),
    ]))

    # ── Section 8: Stability ──
    story.append(Paragraph("8. System Stability", h2_s))
    story.append(two_col_table([
        ["System Uptime",         f"{stb.get('uptime','N/A')}  {stb.get('uptime_label','')}"],
        ["Open File Descriptors", str(stb.get("open_fds", "N/A"))],
        ["Max File Descriptors",  str(stb.get("max_fds", "N/A"))],
        ["FD Usage",              f"{_na(stb.get('fd_pct'), '%')}  {stb.get('fd_label','')}"],
    ]))
    story.append(Spacer(1, 0.1*cm))
    story.append(Paragraph(stb.get("uptime_note", ""), small_s))
    story.append(Paragraph(stb.get("fd_note", ""), small_s))
    story.append(Spacer(1, 0.15*cm))

    # ── Charts ──
    chart_defs = [
        ("latency", "trend", "API Response Time (p95)", "Seconds",  "steelblue",    1.0),
        ("errors",  "trend", "Error Rate Over Time",    "% Errors", "tomato",       1.0),
        ("cpu",     "trend", "CPU Usage Over Time",     "CPU %",    "darkorange",  70.0),
        ("memory",  "trend", "Memory Usage Over Time",  "MB",       "mediumpurple", 400.0),
    ]
    has_charts = False
    for a_key, t_key, title, ylabel, color, warn in chart_defs:
        td = raw.get(a_key, {}).get(t_key, [])
        if not td:
            continue
        if not has_charts:
            story.append(Paragraph("Performance Trend Charts", h2_s))
            has_charts = True
        cbuf = _chart(td, title, ylabel, color, warn)
        if cbuf:
            story.append(RLImage(cbuf, width=15*cm, height=4.8*cm))
            story.append(Spacer(1, 0.25*cm))

    # ── Section 9: Business Impact ──
    story.append(Paragraph("9. Business Impact", h2_s))
    for item in r.get("business_impact", []):
        story.append(Paragraph(f"• {item}", small_s))
    story.append(Spacer(1, 0.15*cm))

    # ── Section 10: Recommended Actions ──
    story.append(Paragraph("10. Recommended Actions", h2_s))
    actions = r.get("actions", [])
    if not actions:
        story.append(Paragraph("✅ No actions required. System is healthy.", small_s))
    else:
        priority_colors = {
            "Critical": "#e74c3c", "High": "#e74c3c",
            "Medium": "#e67e22",   "Low": "#27ae60",
        }
        for i, a in enumerate(actions, 1):
            pc = colors.HexColor(priority_colors.get(a.get("priority", ""), "#95a5a6"))
            rows = [
                [f"{i}. {a.get('priority','')} Priority", ""],
                ["⚠️ Problem",  a.get("problem", "")],
                ["📉 Impact",   a.get("impact", "")],
                ["🛠 Action",   a.get("action", "")],
            ]
            t = Table(rows, colWidths=[4*cm, 13*cm])
            t.setStyle(TableStyle([
                ("BACKGROUND",  (0,0), (-1,0), colors.HexColor("#fef9e7")),
                ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
                ("TEXTCOLOR",   (0,0), (-1,0), pc),
                ("SPAN",        (0,0), (-1,0)),
                ("FONTNAME",    (0,1), (0,-1), "Helvetica-Bold"),
                ("FONTSIZE",    (0,0), (-1,-1), 9),
                ("VALIGN",      (0,0), (-1,-1), "TOP"),
                ("GRID",        (0,0), (-1,-1), 0.3, colors.HexColor("#e0e0e0")),
                ("PADDING",     (0,0), (-1,-1), 6),
                ("ROWBACKGROUNDS", (0,1), (-1,-1),
                 [colors.HexColor("#f8f9fa"), colors.white]),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.2*cm))

    # ── Section 11: Final Status ──
    story.append(Paragraph("11. Final Status", h2_s))
    fc_rl2 = _rl_color(fs["label"])
    story.append(Paragraph(
        fs["label"],
        S("FS2", fontSize=14, fontName="Helvetica-Bold", textColor=fc_rl2, spaceAfter=4)
    ))
    story.append(Paragraph(fs["message"], body_s))
    story.append(Paragraph(
        f"Justification: {fs.get('justification', '')}",
        S("Just", fontSize=8, textColor=colors.HexColor("#888888"),
          fontName="Helvetica-Oblique", spaceAfter=4)
    ))

    # ── Footer ──
    story.append(Spacer(1, 0.5*cm))
    story.append(hr())
    story.append(Paragraph(
        "Generated by EMS Backend  ·  Powered by Prometheus  ·  For internal use only",
        footer_s,
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()
