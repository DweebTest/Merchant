"""Turn a Report into a PDF with ReportLab (pure Python, no system libraries)."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    CondPageBreak,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ACCENT = colors.HexColor("#1f5fbf")
MUTED = colors.HexColor("#5d6677")
BORDER = colors.HexColor("#dde1e8")
STRIPE = colors.HexColor("#f6f7f9")

_base = getSampleStyleSheet()
STYLES = {
    "title": ParagraphStyle("title", parent=_base["Title"], alignment=TA_LEFT, fontSize=20, leading=24,
                            spaceAfter=2, textColor=colors.HexColor("#1d2330")),
    "meta": ParagraphStyle("meta", parent=_base["Normal"], fontSize=9.5, leading=13, textColor=MUTED),
    "h2": ParagraphStyle("h2", parent=_base["Heading2"], fontSize=13, leading=16, spaceBefore=14, spaceAfter=4,
                         textColor=colors.HexColor("#1d2330")),
    "intro": ParagraphStyle("intro", parent=_base["Normal"], fontSize=8.5, leading=11, textColor=MUTED,
                            spaceAfter=4),
    "cell": ParagraphStyle("cell", parent=_base["Normal"], fontSize=8, leading=10),
    "head": ParagraphStyle("head", parent=_base["Normal"], fontSize=8, leading=10, fontName="Helvetica-Bold",
                           textColor=colors.white),
    "stat_num": ParagraphStyle("stat_num", parent=_base["Normal"], fontSize=16, leading=19,
                               fontName="Helvetica-Bold"),
    "stat_label": ParagraphStyle("stat_label", parent=_base["Normal"], fontSize=8, leading=10, textColor=MUTED),
    "empty": ParagraphStyle("empty", parent=_base["Normal"], fontSize=9, leading=12, textColor=MUTED),
}

PAGE = landscape(letter)
MARGIN = 0.5 * inch
CONTENT_WIDTH = PAGE[0] - 2 * MARGIN


def _p(value, style="cell"):
    text = escape("" if value is None else str(value)).replace("\n", "<br/>")
    return Paragraph(text, STYLES[style])


def _summary_table(summary):
    cells = [[_p(value, "stat_num") for _, value in summary], [_p(label, "stat_label") for label, _ in summary]]
    width = min(CONTENT_WIDTH / max(len(summary), 1), 1.8 * inch)
    table = Table(cells, colWidths=[width] * len(summary), hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _data_table(section):
    widths = section.widths or [1] * len(section.columns)
    scale = CONTENT_WIDTH / sum(widths)
    data = [[_p(c, "head") for c in section.columns]] + [[_p(v) for v in row] for row in section.rows]
    table = Table(data, colWidths=[w * scale for w in widths], repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, BORDER),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(2, len(data), 2):
        style.append(("BACKGROUND", (0, i), (-1, i), STRIPE))
    table.setStyle(TableStyle(style))
    return table


def _bar_chart(title, pairs):
    pairs = [(label, value) for label, value in pairs if value][:12]
    if not pairs:
        return None
    bar_h = 16
    height = bar_h * len(pairs) + 40
    drawing = Drawing(CONTENT_WIDTH * 0.7, height)
    chart = HorizontalBarChart()
    chart.x = 150
    chart.y = 10
    chart.width = CONTENT_WIDTH * 0.7 - 170
    chart.height = bar_h * len(pairs)
    # Largest at the top.
    ordered = list(reversed(pairs))
    chart.data = [[v for _, v in ordered]]
    chart.categoryAxis.categoryNames = [label[:28] for label, _ in ordered]
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.barLabels.fontName = "Helvetica"
    chart.categoryAxis.labels.dx = -4
    chart.categoryAxis.strokeColor = BORDER
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.strokeColor = BORDER
    top = max(v for _, v in pairs)
    chart.valueAxis.valueStep = max(1, round(top / 5))
    chart.valueAxis.valueMax = top + chart.valueAxis.valueStep
    chart.bars[0].fillColor = ACCENT
    chart.bars[0].strokeColor = None
    chart.barLabelFormat = "%d"
    chart.barLabels.fontSize = 7
    chart.barLabels.nudge = 7
    drawing.add(chart)
    drawing.add(String(0, height - 12, title, fontSize=9, fontName="Helvetica-Bold", fillColor=MUTED))
    return drawing


def render_pdf(report, generated_by=""):
    buffer = BytesIO()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 0.3 * inch, f"Merchant · {report.title} · {report.period}")
        canvas.drawRightString(PAGE[0] - MARGIN, 0.3 * inch, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buffer, pagesize=PAGE, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=0.55 * inch,
        title=report.title, author="Merchant",
    )
    meta = f"{report.period} · {report.filters} · Generated {report.generated_at:%Y-%m-%d %H:%M}"
    if generated_by:
        meta += f" by {generated_by}"
    story = [_p(report.title, "title"), _p(meta, "meta"), Spacer(1, 10)]
    if report.summary:
        story += [_summary_table(report.summary), Spacer(1, 4)]

    for section in report.sections:
        head = [_p(section.heading, "h2")]
        if section.intro:
            head.append(_p(section.intro, "intro"))
        if not section.rows:
            story.append(KeepTogether(head + [_p(section.empty_text, "empty")]))
            continue
        # Start a new page rather than leave a heading stranded at the bottom.
        story.append(CondPageBreak(1.6 * inch))
        story += head
        chart = _bar_chart(section.chart_title, section.chart) if section.chart else None
        if chart:
            story += [chart, Spacer(1, 6)]
        story.append(_data_table(section))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
