from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import copy
import io
import math
import numbers
import re
import tempfile
from datetime import datetime
from xml.sax.saxutils import escape
from pathlib import Path
from typing import Dict, List, Optional, Sequence

try:
    import ezdxf
    from ezdxf.addons.drawing import layout
    from ezdxf import bbox
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.svg import SVGBackend
except Exception:  # DXF rendering is optional when --omit-drawings is used
    ezdxf = None
    layout = None
    bbox = None
    Frontend = None
    RenderContext = None
    SVGBackend = None
import pandas as pd
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A0, A3, A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Flowable,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents
try:
    from svglib.svglib import svg2rlg
except Exception:  # SVG conversion is optional when --omit-drawings is used
    svg2rlg = None

from amr_report_analysis import fmt_duration, fmt_ts


REPORT_SECTIONS = [
    ("front_summary", "Executive summary"),
    ("operational_kpis", "Operational KPIs (demand, service, capacity and cost)"),
    ("scenario_impact", "Scenario impact and resilience"),
    ("method", "Method"),
    ("amr_list", "AMR list"),
    ("amr_fleet", "AMR fleet summary"),
    ("amr_utilisation", "AMR utilisation and recharge"),
    ("payload_summary", "Payload summary"),
    ("pending_tasks", "Pending tasks"),
    ("task_sla", "Task SLA performance"),
    ("sla_categories", "SLA categories and assigned targets"),
    ("failed_delivery", "Failed delivery analysis"),
    ("lift_usage", "Lift usage and waits"),
    ("journey_flows", "Journey origins, destinations and returns"),
    ("lift_usage_profile", "Lift usage profile"),
    ("lift_trip_cohorts", "Lift trip cohorts"),
    ("lift_wait_profiles", "Lift wait time profiles"),
    ("generated_tasks", "Generated task category summary"),
    ("deferred_releases", "Deferred task releases"),
    ("staff_handling", "Category staff handling"),
    ("staff_timetable", "Staff handling timetable"),
    ("location_space", "Location space utilisation"),
    ("peak_occupancy", "Peak location occupancy"),
    ("dropoff_zone_occupancy", "Drop-off zone peak occupancy"),
    ("location_recommendations", "Location storage recommendations"),
    ("task_detail", "Task detail grouped by AMR"),
    ("heatmaps", "Congestion heatmaps"),
]

REPORT_SECTION_LABELS = dict(REPORT_SECTIONS)
DEFAULT_REPORT_SECTION_ORDER = [section_id for section_id, _label in REPORT_SECTIONS]

REPORT_SECTION_PAGE_TEMPLATES = {
    "front_summary": "standard",
    "operational_kpis": "landscape",
    "scenario_impact": "landscape",
    "generated_tasks": "landscape",
    "deferred_releases": "a3_landscape",
    "staff_handling": "standard",
    "staff_timetable": "a3_landscape",
    "method": "standard",
    "amr_list": "landscape",
    "amr_fleet": "landscape",
    "amr_utilisation": "landscape",
    "lift_usage": "landscape",
    "journey_flows": "a3_landscape",
    "lift_usage_profile": "a3_landscape",
    "lift_trip_cohorts": "a3_landscape",
    "lift_wait_profiles": "a3_landscape",
    "payload_summary": "standard",
    "location_space": "a3_landscape",
    "peak_occupancy": "a3_landscape",
    "dropoff_zone_occupancy": "a3_landscape",
    "failed_delivery": "a3_landscape",
    "location_recommendations": "a3_landscape",
    "pending_tasks": "a3_landscape",
    "task_sla": "a3_landscape",
    "sla_categories": "landscape",
    "task_detail": "a3_landscape",
    "heatmaps": "a0_landscape",
}


def normalise_report_sections(
    report_sections: Optional[Sequence[str]] = None,
) -> List[str]:
    if not report_sections:
        return list(DEFAULT_REPORT_SECTION_ORDER)
    seen = set()
    result = []
    valid = set(REPORT_SECTION_LABELS)
    for section_id in report_sections:
        section_id = str(section_id or "").strip()
        if section_id in valid and section_id not in seen:
            result.append(section_id)
            seen.add(section_id)
    return result or list(DEFAULT_REPORT_SECTION_ORDER)


class SectionedStory:
    def __init__(self, section_order: Optional[Sequence[str]] = None):
        self.section_order = normalise_report_sections(section_order)
        self.selected = set(self.section_order)
        self.current_section = self.section_order[0] if self.section_order else ""
        self.sections: Dict[str, List] = {key: [] for key in DEFAULT_REPORT_SECTION_ORDER}

    def section(self, section_id: str) -> None:
        section_id = str(section_id or "").strip()
        if section_id in REPORT_SECTION_LABELS:
            self.current_section = section_id

    def append(self, flowable) -> None:
        if self.current_section in self.selected:
            self.sections.setdefault(self.current_section, []).append(flowable)

    def extend(self, flowables) -> None:
        for flowable in flowables:
            self.append(flowable)

    def __iadd__(self, flowables):
        self.extend(flowables)
        return self

    @staticmethod
    def _is_template_marker(flowable) -> bool:
        return isinstance(flowable, NextPageTemplate)

    @staticmethod
    def _is_page_break(flowable) -> bool:
        return isinstance(flowable, PageBreak)

    def _normalised_section_content(self, flowables: List) -> List:
        cleaned = [
            flowable
            for flowable in flowables
            if not self._is_template_marker(flowable)
        ]

        while cleaned and self._is_page_break(cleaned[0]):
            cleaned.pop(0)
        while cleaned and self._is_page_break(cleaned[-1]):
            cleaned.pop()

        return cleaned

    def flowables(self, styles=None) -> List:
        styles = styles or make_styles()
        result = []
        first_section = True
        for number, section_id in enumerate(self.section_order, 1):
            section_flowables = self._normalised_section_content(
                self.sections.get(section_id, [])
            )
            if not section_flowables:
                section_flowables = [Paragraph('No records in the observed period.', styles['BodyText'])]

            template_id = REPORT_SECTION_PAGE_TEMPLATES.get(section_id, "standard")
            result.append(NextPageTemplate(template_id))
            if not first_section:
                result.append(PageBreak())
            title = f'{number} {REPORT_SECTION_LABELS[section_id]}'
            def heading(text, level, key, style):
                paragraph = Paragraph(text, style)
                paragraph._report_heading = (level, paragraph.getPlainText(), key)
                return paragraph
            if section_id == 'heatmaps' and isinstance(section_flowables[0], FloorOverlayFlowable):
                # Heatmaps occupy the complete frame; draw their title inside the overlay.
                section_flowables[0]._report_heading = (0, title, section_id)
                for floor_number, overlay in enumerate((f for f in section_flowables if isinstance(f, FloorOverlayFlowable)), 1):
                    floor_title = f'{number}.{floor_number} Floor {overlay.floor_label}'
                    overlay.report_title = title + ' / ' + floor_title
                    overlay._report_floor_heading = (1, floor_title, f'{section_id}-floor-{floor_number}')
            else:
                result.append(heading(escape(title), 0, section_id, styles['Section']))
            sub = child = 0
            parent_seen = False
            for flowable in section_flowables:
                if isinstance(flowable, Paragraph) and flowable.style.name in ('Section', 'Heading1', 'Heading2', 'Heading3'):
                    text = flowable.getPlainText()
                    if text.lower() == REPORT_SECTION_LABELS[section_id].lower():
                        continue
                    if section_id == 'operational_kpis':
                        match = re.match(r'^1\.(\d+)\s+(.*)', text)
                        if match:
                            sub, child = int(match[1]), 0
                            prefix, text, level = f'{number}.{sub}', match[2], 1
                        else:
                            child += 1
                            prefix, level = f'{number}.{max(sub, 1)}.{child}', 2
                    elif flowable.style.name == 'Heading3' and parent_seen:
                        child += 1
                        prefix, level = f'{number}.{sub}.{child}', 2
                    else:
                        sub += 1
                        child = 0
                        prefix, level = f'{number}.{sub}', 1
                        parent_seen = flowable.style.name != 'Heading3'
                    flowable = heading(escape(f'{prefix} {text}'), level,
                                       f'{section_id}-{sub}-{child}', styles['Subsection'] if level == 1 else styles['Heading3'])
                result.append(flowable)
            first_section = False
        return result


def make_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#17365D"),
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportSub",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#4F81BD"),
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#17365D"),
            spaceBefore=6,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            spaceAfter=4,
        )
    )
    styles.add(ParagraphStyle(name='Subsection', parent=styles['Section'], fontSize=12, leading=15))
    return styles


class NumberedDocTemplate(BaseDocTemplate):
    def afterFlowable(self, flowable):
        for entry in (getattr(flowable, '_report_heading', None), getattr(flowable, '_report_floor_heading', None)):
            if not entry:
                continue
            level, text, key = entry
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=False)
            self.notify('TOCEntry', (level, escape(text), self.page, key))

    def __init__(self, filename, first_template_id: str = "standard", **kwargs):
        super().__init__(filename, **kwargs)

        portrait_frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="portrait",
        )

        a4_landscape_width, a4_landscape_height = landscape(A4)
        landscape_frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            a4_landscape_width - self.leftMargin - self.rightMargin,
            a4_landscape_height - self.topMargin - self.bottomMargin,
            id="landscape",
        )

        a3_portrait_width, a3_portrait_height = A3
        a3_portrait_frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            a3_portrait_width - self.leftMargin - self.rightMargin,
            a3_portrait_height - self.topMargin - self.bottomMargin,
            id="a3_portrait",
        )

        a3_landscape_width, a3_landscape_height = landscape(A3)
        a3_landscape_frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            a3_landscape_width - self.leftMargin - self.rightMargin,
            a3_landscape_height - self.topMargin - self.bottomMargin,
            id="a3_landscape",
        )

        a0_portrait_width, a0_portrait_height = A0
        a0_portrait_frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            a0_portrait_width - self.leftMargin - self.rightMargin,
            a0_portrait_height - self.topMargin - self.bottomMargin,
            id="a0_portrait",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )

        a0_landscape_width, a0_landscape_height = landscape(A0)
        a0_landscape_frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            a0_landscape_width - self.leftMargin - self.rightMargin,
            a0_landscape_height - self.topMargin - self.bottomMargin,
            id="a0_landscape",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )

        templates = {
            "standard": PageTemplate(
                id="standard",
                pagesize=A4,
                frames=[portrait_frame],
                onPage=self._draw_header_footer,
            ),
            "landscape": PageTemplate(
                id="landscape",
                pagesize=landscape(A4),
                frames=[landscape_frame],
                onPage=self._draw_header_footer,
            ),
            "a3_portrait": PageTemplate(
                id="a3_portrait",
                pagesize=A3,
                frames=[a3_portrait_frame],
                onPage=self._draw_header_footer,
            ),
            "a3_landscape": PageTemplate(
                id="a3_landscape",
                pagesize=landscape(A3),
                frames=[a3_landscape_frame],
                onPage=self._draw_header_footer,
            ),
            "a0_portrait": PageTemplate(
                id="a0_portrait",
                pagesize=A0,
                frames=[a0_portrait_frame],
                onPage=self._draw_header_footer,
            ),
            "a0_landscape": PageTemplate(
                id="a0_landscape",
                pagesize=landscape(A0),
                frames=[a0_landscape_frame],
                onPage=self._draw_header_footer,
            ),
        }
        first_template_id = first_template_id if first_template_id in templates else "standard"
        ordered_template_ids = [first_template_id] + [
            template_id for template_id in templates if template_id != first_template_id
        ]
        self.addPageTemplates([templates[template_id] for template_id in ordered_template_ids])

    def _draw_header_footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))

        page_width, page_height = canvas._pagesize
        header = doc.title
        while pdfmetrics.stringWidth(header, 'Helvetica', 8) > page_width - doc.leftMargin - doc.rightMargin:
            header = header[:-4] + '...'
        canvas.drawString(
            doc.leftMargin,
            page_height - 12 * mm,
            header,
        )
        canvas.drawRightString(
            page_width - doc.rightMargin,
            10 * mm,
            f"Page {canvas.getPageNumber()}",
        )
        canvas.restoreState()


def natural_key(s):
    return tuple(
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r"(\d+)", str(s))
    )


class PageWidthTable(Table):
    """Fit report tables to the actual frame, including split continuations.

    Section widths express column proportions, not a fixed paper size. ReportLab
    creates split pieces using this class, so repeated headers and continuation
    pages retain the same sizing rule on portrait and landscape templates.
    """

    def _fit_frame(self, available_width):
        if getattr(self, '_report_frame_width', None) == available_width:
            return
        if not hasattr(self, '_report_column_weights'):
            self._report_column_weights = tuple(float(w) for w in self._argW)
            minimums = []
            for cell, style in zip(self._cellvalues[0], self._cellStyles[0]):
                if isinstance(cell, (list, tuple)):
                    cell = cell[0] if cell else None
                if isinstance(cell, Paragraph):
                    word_width = max((pdfmetrics.stringWidth(word, cell.style.fontName, cell.style.fontSize)
                                      for word in cell.getPlainText().split()), default=0)
                else:
                    word_width = 0
                minimums.append(word_width + style.leftPadding + style.rightPadding + 2)
            self._report_column_minimums = tuple(minimums)

        weights = self._report_column_weights
        minimums = self._report_column_minimums
        widths = [0.0] * len(weights)
        remaining = set(range(len(weights)))
        budget = available_width
        if sum(minimums) > available_width:
            # Extremely dense tables still stay inside the page; paragraphs can
            # wrap long words when no allocation can satisfy every header.
            widths = [available_width * w / sum(minimums) for w in minimums]
        else:
            while remaining:
                total_weight = sum(weights[i] for i in remaining)
                shares = {i: budget * weights[i] / total_weight for i in remaining}
                constrained = {i for i in remaining if shares[i] < minimums[i]}
                if not constrained:
                    for i, width in shares.items():
                        widths[i] = width
                    break
                for i in constrained:
                    widths[i] = minimums[i]
                    budget -= widths[i]
                remaining -= constrained
        widths[-1] += available_width - sum(widths)
        self._argW = self._colWidths = widths
        self.__dict__.pop('_width_calculated_once', None)
        self._report_frame_width = available_width

    def wrap(self, availWidth, availHeight):
        self._fit_frame(availWidth)
        return super().wrap(availWidth, availHeight)

    def split(self, availWidth, availHeight):
        self._fit_frame(availWidth)
        return super().split(availWidth, availHeight)


def table_from_df(
    df: pd.DataFrame,
    col_widths: List[float],
    styles,
    right_align: Optional[List[int]] = None,
    format_values: bool = True,
) -> Table:
    df = df.loc[:, ~pd.Index(df.columns).duplicated()].copy()
    col_widths = list(col_widths[: len(df.columns)])
    if len(col_widths) < len(df.columns):
        col_widths.extend([20 * mm] * (len(df.columns) - len(col_widths)))

    header_style = ParagraphStyle(
        "TblHead",
        parent=styles["Small"],
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#17365D"),
        leading=10,
    )
    body_style = ParagraphStyle(
        "TblBody",
        parent=styles["Small"],
        fontName="Helvetica",
        textColor=colors.black,
        leading=10,
    )

    header = [Paragraph(str(c), header_style) for c in df.columns]
    rows = []
    for row in df.fillna("-").itertuples(index=False, name=None):
        rows.append(
            [
                Paragraph(
                    (format_report_cell(cell) if format_values else str(cell)).replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"),
                    body_style,
                )
                for cell in row
            ]
        )

    data = [header] + rows
    tbl = PageWidthTable(data, colWidths=col_widths, repeatRows=1, hAlign='LEFT')
    style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#17365D")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LEADING", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8CCE4")),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [colors.white, colors.HexColor("#F7F9FC")],
            ),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
    )
    if right_align:
        for idx in right_align:
            style.add("ALIGN", (idx, 1), (idx, -1), "RIGHT")
    tbl.setStyle(style)
    return tbl


def format_report_cell(value) -> str:
    """Use consistent precision for measured values without altering counts or IDs."""
    if isinstance(value, numbers.Real) and not isinstance(value, (bool, numbers.Integral)):
        return f"{value:.2f}" if math.isfinite(value) else "-"
    text = str(value)
    match = re.fullmatch(r"([+-]?\d+(?:,\d{3})*\.\d+)(\s*(?:%|[A-Za-z][A-Za-z0-9²³/ ]*))?", text)
    if match:
        number, suffix = match.groups()
        precision = f"{float(number.replace(',', '')):,.2f}" if "," in number else f"{float(number):.2f}"
        return precision + (suffix or "")
    return text


def lift_trip_cohort_matrix(cohort_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot a long lift cohort result into a report-friendly trip matrix."""
    if (
        cohort_df is None
        or cohort_df.empty
        or not {
            "cohort_date",
            "cohort_start",
            "interval",
            "interval_start_min",
            "lift_id",
            "trips",
        }.issubset(
            cohort_df.columns
        )
    ):
        return pd.DataFrame()

    rows = cohort_df.copy()
    rows["interval_start_min"] = pd.to_numeric(
        rows["interval_start_min"], errors="coerce"
    )
    rows["trips"] = pd.to_numeric(rows["trips"], errors="coerce").fillna(0)
    rows = rows[rows["interval_start_min"].notna()].copy()
    if rows.empty:
        return pd.DataFrame()

    lift_ids = sorted(
        rows["lift_id"].dropna().astype(str).unique().tolist(), key=natural_key
    )
    matrix = rows.pivot_table(
        index=[
            "cohort_start",
            "cohort_date",
            "interval_start_min",
            "interval",
        ],
        columns="lift_id",
        values="trips",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    for lift_id in lift_ids:
        if lift_id not in matrix.columns:
            matrix[lift_id] = 0
    matrix = matrix.sort_values("cohort_start")
    matrix = matrix[["cohort_date", "interval"] + lift_ids]
    for lift_id in lift_ids:
        matrix[lift_id] = (
            pd.to_numeric(matrix[lift_id], errors="coerce").fillna(0).astype(int)
        )
    matrix["Total"] = matrix[lift_ids].sum(axis=1).astype(int)
    matrix = matrix[matrix["Total"] > 0].copy()
    return matrix.rename(
        columns={"cohort_date": "Date", "interval": "Time"}
    ).reset_index(drop=True)


CATEGORY_PALETTE = [
    "#2F5597",
    "#548235",
    "#C55A11",
    "#7F6000",
    "#7030A0",
    "#008C95",
    "#A64D79",
    "#5B9BD5",
]


def category_colour(category_key: str) -> str:
    text = str(category_key or "").strip().lower()
    if not text:
        return CATEGORY_PALETTE[0]
    value = sum((idx + 1) * ord(char) for idx, char in enumerate(text))
    return CATEGORY_PALETTE[value % len(CATEGORY_PALETTE)]


def contrasting_text_colour(hex_colour: str) -> Color:
    text = str(hex_colour or "#2F5597").lstrip("#")
    try:
        r = int(text[0:2], 16)
        g = int(text[2:4], 16)
        b = int(text[4:6], 16)
    except Exception:
        return colors.white
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    return colors.black if brightness > 150 else colors.white


def fmt_wait_duration(value) -> str:
    """Format wait durations without hiding positive sub-second values."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return fmt_duration(value)
    if 0 < seconds < 1:
        return f"{seconds:.2f} s"
    return fmt_duration(seconds)


class LiftUsageProfileChart(Flowable):
    """A3-friendly line chart showing one metric per lift and time bucket."""

    def __init__(
        self,
        profile_df: pd.DataFrame,
        width: float,
        height: float,
        value_column: str = "trips",
        y_axis_label: str = "Trips per 30 minute interval",
        empty_message: str = "No lift usage profile data was available.",
        integer_ticks: bool = True,
    ):
        super().__init__()
        self.profile_df = profile_df.copy() if profile_df is not None else pd.DataFrame()
        self.width = float(width)
        self.height = float(height)
        self.value_column = str(value_column or "trips")
        self.y_axis_label = str(y_axis_label or "")
        self.empty_message = str(empty_message or "No lift profile data was available.")
        self.integer_ticks = bool(integer_ticks)

    def wrap(self, availWidth, availHeight):
        self.width = min(self.width, availWidth)
        return self.width, self.height

    def draw(self):
        c = self.canv
        x0 = 20 * mm
        y0 = 24 * mm
        plot_w = max(10 * mm, self.width - 48 * mm)
        plot_h = max(10 * mm, self.height - 54 * mm)

        c.saveState()
        c.setStrokeColor(colors.HexColor("#B8CCE4"))
        c.setLineWidth(0.5)
        c.setFillColor(colors.white)
        c.rect(0, 0, self.width, self.height, stroke=0, fill=1)

        df = self.profile_df.copy()
        if df.empty:
            c.setFillColor(colors.HexColor("#666666"))
            c.setFont("Helvetica", 10)
            c.drawString(x0, y0 + plot_h / 2, self.empty_message)
            c.restoreState()
            return

        df["interval_start_min"] = pd.to_numeric(df.get("interval_start_min"), errors="coerce")
        df[self.value_column] = pd.to_numeric(
            df.get(self.value_column), errors="coerce"
        ).fillna(0)
        df = df[df["interval_start_min"].notna()].copy()
        if df.empty:
            c.setFillColor(colors.HexColor("#666666"))
            c.setFont("Helvetica", 10)
            c.drawString(x0, y0 + plot_h / 2, self.empty_message)
            c.restoreState()
            return

        intervals = sorted(df["interval_start_min"].dropna().unique().tolist())
        lift_ids = sorted(df["lift_id"].dropna().astype(str).unique().tolist(), key=natural_key)
        if not intervals or not lift_ids:
            c.restoreState()
            return

        max_y = max(1.0, float(df[self.value_column].max()))
        tick_count = 6
        if self.integer_ticks:
            max_y = float(max(1, int(math.ceil(max_y))))
            y_ticks = sorted(
                set(
                    int(round(i * max_y / max(1, tick_count - 1)))
                    for i in range(tick_count)
                )
            )
        else:
            y_ticks = [i * max_y / max(1, tick_count - 1) for i in range(tick_count)]
        if y_ticks[0] != 0:
            y_ticks.insert(0, 0)

        def x_pos(minute):
            if len(intervals) == 1:
                return x0 + plot_w / 2
            return x0 + (float(minute) - float(intervals[0])) / max(1.0, float(intervals[-1] - intervals[0])) * plot_w

        def y_pos(value):
            return y0 + (float(value) / max_y) * plot_h

        # Grid and axes
        c.setFont("Helvetica", 7)
        for tick in y_ticks:
            y = y_pos(tick)
            c.setStrokeColor(colors.HexColor("#E6EEF8"))
            c.line(x0, y, x0 + plot_w, y)
            c.setFillColor(colors.HexColor("#666666"))
            tick_label = str(int(tick)) if self.integer_ticks else fmt_duration(tick)
            c.drawRightString(x0 - 3 * mm, y - 2, tick_label)

        c.setStrokeColor(colors.HexColor("#17365D"))
        c.setLineWidth(0.8)
        c.line(x0, y0, x0 + plot_w, y0)
        c.line(x0, y0, x0, y0 + plot_h)

        # X axis labels every two hours, plus the final bucket if needed.
        label_minutes = [minute for minute in intervals if int(minute) % 120 == 0]
        if intervals[-1] not in label_minutes:
            label_minutes.append(intervals[-1])
        for minute in label_minutes:
            x = x_pos(minute)
            c.setStrokeColor(colors.HexColor("#E6EEF8"))
            c.line(x, y0, x, y0 + plot_h)
            label = f"{int(minute // 60):02d}:{int(minute % 60):02d}"
            c.setFillColor(colors.HexColor("#666666"))
            c.drawCentredString(x, y0 - 5 * mm, label)

        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(colors.HexColor("#17365D"))
        c.drawCentredString(x0 + plot_w / 2, y0 - 13 * mm, "Time of day")
        c.saveState()
        c.translate(x0 - 14 * mm, y0 + plot_h / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, self.y_axis_label)
        c.restoreState()

        palette = [
            "#2F5597", "#548235", "#C55A11", "#7030A0", "#008C95", "#A64D79",
            "#5B9BD5", "#70AD47", "#FFC000", "#4472C4", "#ED7D31", "#7F7F7F",
        ]
        for lift_index, lift_id in enumerate(lift_ids):
            sub = df[df["lift_id"].astype(str) == lift_id].set_index("interval_start_min")
            points = []
            for minute in intervals:
                value = (
                    sub[self.value_column].get(minute, 0)
                    if self.value_column in sub.columns
                    else 0
                )
                points.append((x_pos(minute), y_pos(value)))
            if len(points) < 2:
                continue
            colour = colors.HexColor(palette[lift_index % len(palette)])
            c.setStrokeColor(colour)
            c.setLineWidth(1.2)
            path = c.beginPath()
            path.moveTo(points[0][0], points[0][1])
            for x, y in points[1:]:
                path.lineTo(x, y)
            c.drawPath(path, stroke=1, fill=0)

        # Legend
        legend_x = x0
        legend_y = y0 + plot_h + 9 * mm
        c.setFont("Helvetica", 7.5)
        cursor_x = legend_x
        for lift_index, lift_id in enumerate(lift_ids):
            label = str(lift_id)
            item_w = min(42 * mm, 7 * mm + c.stringWidth(label, "Helvetica", 7.5) + 5 * mm)
            if cursor_x + item_w > x0 + plot_w:
                legend_y += 5 * mm
                cursor_x = legend_x
            colour = colors.HexColor(palette[lift_index % len(palette)])
            c.setStrokeColor(colour)
            c.setLineWidth(2)
            c.line(cursor_x, legend_y, cursor_x + 5 * mm, legend_y)
            c.setFillColor(colors.black)
            c.drawString(cursor_x + 7 * mm, legend_y - 2, label)
            cursor_x += item_w

        c.restoreState()


class PillListFlowable(Flowable):
    def __init__(
        self,
        entries: List[str],
        fill_colour: str,
        max_width: float,
        max_visible: int = 6,
    ):
        super().__init__()
        raw_entries = [
            str(x).strip() for x in entries if str(x).strip() and str(x).strip() != "-"
        ]
        max_visible = max(1, int(max_visible or 1))
        overflow = max(0, len(raw_entries) - max_visible)
        self.entries = raw_entries[:max_visible]
        if overflow:
            self.entries.append(f"+{overflow} more")
        self.fill_colour = colors.HexColor(fill_colour)
        self.text_colour = contrasting_text_colour(fill_colour)
        self.max_width = max(20.0, float(max_width))
        self.font_name = "Helvetica-Bold"
        self.font_size = 6.5
        self.line_height = 11
        self.pad_x = 4
        self.pad_y = 2
        self.gap = 2
        self.width = self.max_width
        self.height = min(max(10, len(self.entries) * self.line_height), 82)

    def wrap(self, availWidth, availHeight):
        self.width = min(self.max_width, availWidth)
        self.height = min(max(10, len(self.entries) * self.line_height), 82)
        return self.width, self.height

    def draw(self):
        if not self.entries:
            self.canv.setFillColor(colors.HexColor("#666666"))
            self.canv.setFont("Helvetica", 7)
            self.canv.drawString(0, max(0, self.height - 8), "-")
            return

        y = self.height - self.line_height + 1
        for entry in self.entries:
            label = entry.replace("|", "  ")
            max_chars = max(8, int(self.width / 3.8))
            if len(label) > max_chars:
                label = label[: max_chars - 1] + "..."
            text_width = self.canv.stringWidth(label, self.font_name, self.font_size)
            pill_width = min(self.width, text_width + (self.pad_x * 2))
            self.canv.setFillColor(self.fill_colour)
            self.canv.roundRect(0, y, pill_width, self.line_height - self.gap, 4, fill=1, stroke=0)
            self.canv.setFillColor(self.text_colour)
            self.canv.setFont(self.font_name, self.font_size)
            self.canv.drawString(self.pad_x, y + self.pad_y + 1, label)
            y -= self.line_height


def payload_timetable_table(df: pd.DataFrame, styles) -> Table:
    """Build a weekly staff timetable that can split safely across pages.

    ReportLab can split a table between rows, but it cannot split one individual
    row. A busy member of staff can have enough handling entries to make a
    seven-day row taller than the landscape frame. Split each person's schedule
    into bounded continuation rows so every physical task remains visible while
    the table can paginate normally.
    """
    day_cols = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    day_labels = {
        "Mon": "Monday",
        "Tue": "Tuesday",
        "Wed": "Wednesday",
        "Thu": "Thursday",
        "Fri": "Friday",
        "Sat": "Saturday",
        "Sun": "Sunday",
    }
    col_widths = [36 * mm] + [34 * mm] * len(day_cols)

    header_style = ParagraphStyle(
        "TimetableHead",
        parent=styles["Small"],
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#17365D"),
        leading=9,
    )
    batch_style = ParagraphStyle(
        "TimetableBatch",
        parent=styles["Small"],
        fontName="Helvetica",
        fontSize=7,
        leading=9,
    )
    cell_style = ParagraphStyle(
        "TimetableFullCell",
        parent=styles["Small"],
        fontName="Helvetica",
        fontSize=6.2,
        leading=7.4,
    )
    data = [
        [Paragraph("Person", header_style)]
        + [Paragraph(day_labels.get(day, day), header_style) for day in day_cols]
    ]

    # Four entries normally occupy no more than about 80-130 points, even when
    # location names wrap. This leaves ample room for headings and guarantees
    # that an individual body row remains smaller than the landscape frame.
    max_entries_per_cell = 4
    row_background_commands = []
    body_row_index = 1

    for person_index, (_, row) in enumerate(df.iterrows()):
        day_entries = {}
        continuation_count = 1
        for day in day_cols:
            entries = [
                part.strip()
                for part in str(row.get(day, "") or "").split("\n")
                if part.strip() and part.strip() != "-"
            ]
            day_entries[day] = entries
            continuation_count = max(
                continuation_count,
                int((len(entries) + max_entries_per_cell - 1) // max_entries_per_cell)
                if entries
                else 1,
            )

        batch_name = str(row.get("batch", "-") or "-")
        background = (
            colors.white
            if person_index % 2 == 0
            else colors.HexColor("#F7F9FC")
        )

        for continuation_index in range(continuation_count):
            if continuation_index == 0:
                batch_label = batch_name
            else:
                batch_label = (
                    f'{batch_name}<br/><font size="6">'
                    f"continued {continuation_index + 1}/{continuation_count}"
                    "</font>"
                )

            data_row = [Paragraph(batch_label, batch_style)]
            slice_start = continuation_index * max_entries_per_cell
            slice_end = slice_start + max_entries_per_cell

            for day in day_cols:
                entries = day_entries[day][slice_start:slice_end]
                if entries:
                    lines = []
                    for entry in entries:
                        window, _, location = entry.partition("|")
                        label = f"<b>{escape(window.strip())}</b>"
                        if location.strip():
                            label = f"{label}<br/>{escape(location.strip())}"
                        lines.append(label)
                    data_row.append(Paragraph("<br/>".join(lines), cell_style))
                else:
                    data_row.append(Paragraph("-", cell_style))

            data.append(data_row)
            row_background_commands.append(
                ("BACKGROUND", (0, body_row_index), (-1, body_row_index), background)
            )
            if continuation_index == 0:
                row_background_commands.append(
                    (
                        "LINEABOVE",
                        (0, body_row_index),
                        (-1, body_row_index),
                        0.55,
                        colors.HexColor("#8EA9C1"),
                    )
                )
            body_row_index += 1

    tbl = PageWidthTable(
        data,
        colWidths=col_widths,
        repeatRows=1,
        splitByRow=1,
        hAlign="LEFT",
    )
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8CCE4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    style_commands.extend(row_background_commands)
    tbl.setStyle(TableStyle(style_commands))
    return tbl


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def heat_color(value: float, vmin: float, vmax: float) -> Color:
    if vmax <= vmin:
        t = 0.0
    else:
        t = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))

    r = lerp(0.0, 1.0, t)
    g = lerp(1.0, 0.0, t)
    b = lerp(0.2, 0.0, t)
    return Color(r, g, b)


def compute_floor_extents(floor_df: pd.DataFrame) -> tuple[float, float, float, float]:
    xmin = float(min(floor_df["x1"].min(), floor_df["x2"].min()))
    xmax = float(max(floor_df["x1"].max(), floor_df["x2"].max()))
    ymin = float(min(floor_df["y1"].min(), floor_df["y2"].min()))
    ymax = float(max(floor_df["y1"].max(), floor_df["y2"].max()))

    if xmax <= xmin:
        xmax = xmin + 1.0
    if ymax <= ymin:
        ymax = ymin + 1.0

    return xmin, xmax, ymin, ymax


DXF_UNIT_TO_METRES = {
    0: None,  # Unitless
    1: 0.0254,  # Inches
    2: 0.3048,  # Feet
    4: 0.001,  # Millimetres
    5: 0.01,  # Centimetres
    6: 1.0,  # Metres
    7: 1000.0,  # Kilometres
    10: 0.9144,  # Yards
    14: 0.1,  # Decimetres
    21: 1200.0 / 3937.0,  # US survey feet
}


def get_dxf_unit_scale(doc) -> float:
    """Return the drawing-unit-to-metre scale used by the live map viewer."""
    try:
        insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    except Exception:
        insunits = 0
    scale = DXF_UNIT_TO_METRES.get(insunits)
    return 1.0 if scale is None else float(scale)


def _get_raw_dxf_extents(doc) -> tuple[float, float, float, float]:
    msp = doc.modelspace()

    # --- Attempt 1: bbox (fast)
    try:
        ext = bbox.extents(msp, fast=True)
        if ext.has_data:
            xmin = float(ext.extmin.x)
            ymin = float(ext.extmin.y)
            xmax = float(ext.extmax.x)
            ymax = float(ext.extmax.y)
            if xmax > xmin and ymax > ymin:
                return xmin, xmax, ymin, ymax
    except Exception:
        pass

    try:
        extmin = doc.header.get("$EXTMIN")
        extmax = doc.header.get("$EXTMAX")

        if extmin and extmax:
            xmin, ymin = float(extmin[0]), float(extmin[1])
            xmax, ymax = float(extmax[0]), float(extmax[1])

            if xmax > xmin and ymax > ymin:
                return xmin, xmax, ymin, ymax
    except Exception:
        pass

    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for e in msp:
        try:
            if hasattr(e, "vertices"):
                for v in e.vertices():
                    x, y = float(v[0]), float(v[1])
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)
        except Exception:
            continue

    if min_x < max_x and min_y < max_y:
        return min_x, max_x, min_y, max_y

    # --- Final fallback (prevent crash)
    return 0.0, 100.0, 0.0, 100.0


def get_dxf_extents(dxf_path: str) -> tuple[float, float, float, float]:
    """Return DXF extents in metres so they align with simulation coordinates."""
    import ezdxf

    doc = ezdxf.readfile(dxf_path)
    unit_scale = get_dxf_unit_scale(doc)
    xmin, xmax, ymin, ymax = _get_raw_dxf_extents(doc)
    return (
        xmin * unit_scale,
        xmax * unit_scale,
        ymin * unit_scale,
        ymax * unit_scale,
    )


def get_cached_dxf_svg_path(dxf_path: str) -> Path:
    dxf_file = Path(dxf_path)
    cache_dir = Path(tempfile.gettempdir()) / "amr_report_dxf_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{dxf_file.stem}_{int(dxf_file.stat().st_mtime)}.svg"
    return cache_dir / stamp


def render_dxf_to_svg(
    dxf_path: str,
    output_path: str,
) -> tuple[float, float, float, float]:

    if ezdxf is None or layout is None or SVGBackend is None or Frontend is None or RenderContext is None:
        raise RuntimeError("ezdxf is required to render DXF drawings. Use --omit-drawings to skip drawing overlays.")

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    unit_scale = get_dxf_unit_scale(doc)
    raw_xmin, raw_xmax, raw_ymin, raw_ymax = _get_raw_dxf_extents(doc)

    backend = SVGBackend()
    ctx = RenderContext(doc)

    ctx.set_current_layout(msp)

    # 🔧 Reduce lineweight scaling
    ctx.lineweight_scaling = 0.1  # try 0.1–0.3
    ctx.lineweight_policy = 1  # 0=off, 1=relative (best option)

    # Draw the whole layout so the backend builds its render box properly
    Frontend(ctx, backend).draw_layout(msp, finalize=True)

    data_w = max(raw_xmax - raw_xmin, 1.0)
    data_h = max(raw_ymax - raw_ymin, 1.0)

    page = layout.Page(
        data_w,
        data_h,
        layout.Units.mm,
        margins=layout.Margins.all(0),
    )

    try:
        settings = layout.Settings(
            fit_page=False,
            scale=1.0,
        )
        svg_string = backend.get_string(page, settings=settings)
    except ValueError:
        # Fallback for DXFs where ezdxf still reports an empty render box
        svg_string = f"""<?xml version="1.0" encoding="utf-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{data_w}mm"
     height="{data_h}mm"
     viewBox="{raw_xmin} {raw_ymin} {data_w} {data_h}">
</svg>
"""

    # stroke-width as attribute
    svg_string = re.sub(
        r'stroke-width="[^"]+"',
        'stroke-width="0.02"',
        svg_string,
    )

    # stroke-width inside style=""
    svg_string = re.sub(
        r'stroke-width:\s*[^;"]+',
        "stroke-width:0.02",
        svg_string,
    )

    # optional: force round joins/caps to look cleaner
    svg_string = re.sub(
        r'stroke-linejoin:\s*[^;"]+',
        "stroke-linejoin:round",
        svg_string,
    )
    svg_string = re.sub(
        r'stroke-linecap:\s*[^;"]+',
        "stroke-linecap:round",
        svg_string,
    )

    # remove full-page background fills
    svg_string = re.sub(
        r'<rect[^>]*fill="#212830"[^>]*/?>',
        "",
        svg_string,
        flags=re.IGNORECASE,
    )

    # remove style-based background fills
    svg_string = re.sub(
        r"fill:\s*rgb\([^)]+\)",
        "fill:none",
        svg_string,
    )

    # Force all stroke colours to dark grey/black
    svg_string = re.sub(
        r'stroke="[^"]+"',
        'stroke="#111111"',  # dark grey (nicer than pure black)
        svg_string,
    )

    # Also catch style-based stroke colours
    svg_string = re.sub(
        r'stroke:\s*[^;"]+',
        "stroke:#111111",
        svg_string,
    )

    Path(output_path).write_text(svg_string, encoding="utf-8")
    return (
        raw_xmin * unit_scale,
        raw_xmax * unit_scale,
        raw_ymin * unit_scale,
        raw_ymax * unit_scale,
    )


def load_svg_as_drawing(svg_path: str):
    if svg2rlg is None:
        raise RuntimeError(
            "svglib is required to render DXF drawings. Use --omit-drawings to skip drawing overlays."
        )
    return svg2rlg(io.BytesIO(Path(svg_path).read_bytes()))


def thin_drawing_strokes(node, factor: float) -> None:
    """
    Reduce stroke widths recursively after scaling a ReportLab drawing.
    """
    if factor <= 0:
        return

    # Common svglib/reportlab stroke width attributes
    for attr in ("strokeWidth", "stroke-width"):
        if hasattr(node, attr):
            try:
                current = getattr(node, attr)
                if current is not None:
                    setattr(node, attr, max(float(current) / factor, 0.05))
            except Exception:
                pass

    # Recurse into child nodes
    children = getattr(node, "contents", None)
    if children:
        for child in children:
            thin_drawing_strokes(child, factor)


class FloorOverlayFlowable(Flowable):
    def __init__(
        self,
        floor_df: pd.DataFrame,
        floor_label: str,
        dxf_drawing,
        extents: tuple[float, float, float, float],
        width: float,
        height: float,
    ):
        super().__init__()
        self.floor_df = floor_df.copy()
        self.floor_label = floor_label
        self.dxf_drawing = dxf_drawing
        self.extents = extents
        self.width = width
        self.height = height

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        width = self.width
        height = self.height

        title_h = 14 * mm
        legend_h = 14 * mm
        outer_margin = 6 * mm

        plot_x = outer_margin
        plot_y = outer_margin
        plot_w = width - 2 * outer_margin
        plot_h = height - title_h - legend_h - 2 * outer_margin

        canvas.setFont("Helvetica-Bold", 20)
        canvas.drawString(
            plot_x,
            height - 8 * mm,
            getattr(self, 'report_title', f"Congestion heatmap - Floor {self.floor_label}"),
        )

        if self.floor_df.empty:
            canvas.setFont("Helvetica", 14)
            canvas.drawString(
                plot_x,
                height / 2,
                f"No congestion data available for floor {self.floor_label}.",
            )
            return

        xmin, xmax, ymin, ymax = self.extents
        data_w = xmax - xmin
        data_h = ymax - ymin
        if data_w <= 0:
            data_w = 1.0
        if data_h <= 0:
            data_h = 1.0

        scale = min(plot_w / data_w, plot_h / data_h)
        scaled_w = data_w * scale
        scaled_h = data_h * scale
        offset_x = plot_x + (plot_w - scaled_w) / 2
        offset_y = plot_y + (plot_h - scaled_h) / 2

        if self.dxf_drawing is not None:
            drawing = copy.deepcopy(self.dxf_drawing)
            d_w = float(getattr(drawing, "width", scaled_w) or scaled_w)
            d_h = float(getattr(drawing, "height", scaled_h) or scaled_h)
            if d_w > 0 and d_h > 0:
                d_scale = min(scaled_w / d_w, scaled_h / d_h)
                drawing.scale(d_scale, d_scale)

                # Compensate for stroke widths thickening when the whole drawing is scaled up
                thin_drawing_strokes(drawing, d_scale)

                renderPDF.draw(drawing, canvas, offset_x, offset_y)

        canvas.setStrokeColor(colors.black)
        canvas.rect(offset_x, offset_y, scaled_w, scaled_h, stroke=1, fill=0)

        vmin = float(self.floor_df["congestion_score"].min())
        vmax = float(self.floor_df["congestion_score"].max())

        for _, row in self.floor_df.iterrows():
            x1 = offset_x + (float(row["x1"]) - xmin) * scale
            y1 = offset_y + (float(row["y1"]) - ymin) * scale
            x2 = offset_x + (float(row["x2"]) - xmin) * scale
            y2 = offset_y + (float(row["y2"]) - ymin) * scale

            dx = x2 - x1
            dy = y2 - y1
            length = (dx**2 + dy**2) ** 0.5
            if length <= 0.01:
                continue

            ux = dx / length
            uy = dy / length

            # perpendicular
            px = -uy
            py = ux

            score = float(row["congestion_score"])
            colour = heat_color(score, vmin, vmax)

            # strip width in page units
            half_w = 3 + 10 * (score / vmax if vmax > 0 else 0)

            p1 = (x1 + px * half_w, y1 + py * half_w)
            p2 = (x2 + px * half_w, y2 + py * half_w)
            p3 = (x2 - px * half_w, y2 - py * half_w)
            p4 = (x1 - px * half_w, y1 - py * half_w)

            path = canvas.beginPath()
            path.moveTo(*p1)
            path.lineTo(*p2)
            path.lineTo(*p3)
            path.lineTo(*p4)
            path.close()

            canvas.setFillColor(colour)
            try:
                canvas.setFillAlpha(0.28)
            except Exception:
                pass
            # canvas.setStrokeColor(colors.red)
            # canvas.setLineWidth(1)
            # canvas.line(x1, y1, x2, y2)
            canvas.drawPath(path, stroke=0, fill=1)

        try:
            canvas.setFillAlpha(1.0)
        except Exception:
            pass

        legend_w = 50 * mm
        legend_x = width - legend_w - 12 * mm
        legend_y = height - 12 * mm

        canvas.setFont("Helvetica", 10)
        canvas.drawString(legend_x, legend_y, "Cold")
        canvas.drawRightString(legend_x + legend_w, legend_y, "Hot")

        steps = 20
        bar_y = legend_y - 5 * mm
        for i in range(steps):
            t = i / max(steps - 1, 1)
            c = heat_color(t, 0.0, 1.0)
            canvas.setFillColor(c)
            canvas.rect(
                legend_x + i * (legend_w / steps),
                bar_y,
                (legend_w / steps),
                4 * mm,
                stroke=0,
                fill=1,
            )


def prepare_heatmap_floor(
    floor: int,
    floor_df: pd.DataFrame,
    floor_dxf_map: Dict[int, str],
    include_drawings: bool = True,
) -> tuple[int, dict]:
    floor_df = floor_df.sort_values("congestion_score", ascending=False).reset_index(
        drop=True
    )

    dxf_path = floor_dxf_map.get(int(floor)) if include_drawings else None
    dxf_drawing = None

    if dxf_path:
        cached_svg = get_cached_dxf_svg_path(dxf_path)

        if not cached_svg.exists():
            extents = render_dxf_to_svg(
                dxf_path,
                output_path=str(cached_svg),
            )
        else:
            extents = get_dxf_extents(dxf_path)

        try:
            dxf_drawing = load_svg_as_drawing(str(cached_svg))
        except Exception:
            dxf_drawing = None
    else:
        extents = compute_floor_extents(floor_df)

    return int(floor), {
        "floor_df": floor_df,
        "dxf_drawing": dxf_drawing,
        "extents": extents,
    }


def append_kpi_story(story, results, styles):
    summary = results.get('kpi_summary', pd.DataFrame())
    story.section('operational_kpis')
    if summary.empty:
        story.append(Paragraph('Operational KPI evidence is unavailable for this report.', styles['BodyText']))
        return

    def table(key, columns, labels, widths, limit=None):
        frame = results.get(key, pd.DataFrame()).copy()
        if frame.empty:
            story.append(Paragraph('No records in the observed period.', styles['BodyText']))
            return
        if limit and len(frame) > limit:
            story.append(Paragraph(f'First {limit} of {len(frame):,} records shown. The accompanying {key} CSV contains every record.', styles['Small']))
            frame = frame.head(limit)
        frame = frame.reindex(columns=columns)
        for column in frame.columns:
            if column == 'reason':
                frame[column] = frame[column].map(lambda v: str(v)[:280] + ('...' if len(str(v)) > 280 else ''))
            elif pd.api.types.is_numeric_dtype(frame[column]):
                frame[column] = frame[column].map(lambda v: '-' if pd.isna(v) else
                    f'{v:,.6g}' if 0 < abs(v) < .01 else f'{v:,.2f}'.rstrip('0').rstrip('.'))
        story.append(table_from_df(frame.rename(columns=dict(zip(columns, labels))), [w*mm for w in widths], styles, format_values=False))

    observation = results.get('kpi_observation', {})
    for index, group in enumerate(summary.group.drop_duplicates(), 1):
        if index > 1:
            story.append(PageBreak())
        story.append(Paragraph(f'1.{index} {escape(group)}', styles['Section']))
        if index == 1:
            story.append(Paragraph('Operational KPIs cover delivery and collection requests in the observed run. '
                'Unavailable values require additional evidence; estimates and supplied inputs are labelled. '
                'Empty vehicle returns and charging records are excluded from request counts. '
                f"Observed duration (h:mm:ss or m:ss): {fmt_duration(observation.get('horizon_s', 0))}; fleet: {observation.get('fleet', 0):g} vehicles. "
                f"Request-time fallback used for {observation.get('request_time_fallbacks', 0)} tasks.", styles['BodyText']))
        metrics = summary[summary.group.eq(group)].copy()
        metrics['Result'] = metrics.apply(lambda row: 'Unavailable' if pd.isna(row.value) else
            f'{row.value:,.6g}' + ' ' + row.unit, axis=1)
        story.append(table_from_df(metrics[['metric', 'Result', 'status', 'basis']].rename(
            columns={'metric': 'KPI', 'status': 'Evidence', 'basis': 'Definition and scope'}),
            [48*mm, 32*mm, 32*mm, 145*mm], styles, format_values=False))
        story.append(Spacer(1, 10))
        if group == 'Demand':
            story.append(Paragraph('Hourly requests and fleet use', styles['Section']))
            table('kpi_hourly', ['hour', 'observed_minutes', 'requests', 'tasks_per_hour', 'fleet_utilisation_pct'],
                ['Hour', 'Minutes observed', 'Requests', 'Requests/h', 'Fleet use %'], [53, 45, 40, 48, 50])
        elif group == 'Service':
            story.append(Paragraph('Service performance by logistics stream', styles['Section']))
            table('kpi_streams', ['stream', 'requests', 'completed', 'mean_delivery_s', 'p95_delivery_s', 'sla_assessed', 'compliance_pct', 'overdue', 'overdue_pct'],
                ['Stream', 'Requests', 'Completed', 'Mean (s)', 'P95 (s)', 'SLA assessed', 'SLA %', 'Overdue', 'Overdue %'],
                [43, 25, 27, 27, 27, 29, 25, 25, 29])
            story.append(Spacer(1, 10))
            if not results.get('kpi_overdue', pd.DataFrame()).empty:
                story.append(CondPageBreak(70*mm))
            story.append(Paragraph('Overdue tasks and recorded reasons', styles['Section']))
            table('kpi_overdue', ['task_id', 'stream', 'outcome', 'target_s', 'overdue_s', 'reason'],
                ['Task', 'Stream', 'Outcome', 'Target (s)', 'Overdue (s)', 'Recorded reason'], [47, 35, 25, 27, 28, 95], limit=100)
        elif group == 'Efficiency':
            story.append(Paragraph('Distance by service and route', styles['Section']))
            story.append(Paragraph('Shared movement distance is allocated equally across completed tasks named on the segment. '
                'Unassigned empty and charging travel is included in the fleet KPI but has no service-route allocation.', styles['Small']))
            table('kpi_routes', ['stream', 'origin', 'destination', 'completed', 'allocated_distance_m', 'distance_per_delivery_m'],
                ['Stream', 'Origin', 'Destination', 'Completed', 'Distance (m)', 'Metres/task'], [35, 62, 62, 29, 35, 34], limit=100)
        elif group == 'Bottleneck':
            story.append(Paragraph('Queue time by location and cause', styles['Section']))
            table('kpi_queues', ['location', 'cause', 'waits', 'total_wait_s', 'mean_wait_s', 'max_wait_s'],
                ['Location', 'Cause', 'Waits', 'Total (s)', 'Mean (s)', 'Maximum (s)'], [53, 78, 23, 34, 34, 35], limit=100)
        elif group == 'Resources':
            story.append(Paragraph('Charging locations and infrastructure', styles['Section']))
            table('kpi_chargers', ['location', 'configured_chargers', 'peak_charging', 'charging_hours', 'recommended_with_spare', 'charger_type'],
                ['Location', 'Chargers', 'Peak charging', 'Charge hours', 'With spare', 'Type'], [58, 31, 34, 33, 31, 70])
            rates = ', '.join(str(v) for v in observation.get('charge_rates_kw', []) if v is not None and str(v) != '-')
            story.append(Paragraph('Configured vehicle charge rates (kW): ' + escape(rates or 'Unavailable') +
                '. Charger recommendations reflect observed use; confirm compatibility, access and future demand before sizing.', styles['Small']))


def build_report(
    results: Dict[str, pd.DataFrame],
    csv_path: Path,
    pdf_path: Path,
    progress_callback=None,
    heatmap_workers: Optional[int] = None,
    include_drawings: bool = True,
    report_sections: Optional[Sequence[str]] = None,
    report_title: str = "AMR Simulation Performance Report",
) -> None:
    styles = make_styles()
    selected_section_order = normalise_report_sections(report_sections)
    selected_section_ids = set(selected_section_order)
    first_template_id = REPORT_SECTION_PAGE_TEMPLATES.get(
        selected_section_order[0] if selected_section_order else "front_summary",
        "standard",
    )
    doc = NumberedDocTemplate(
        str(pdf_path),
        first_template_id='standard',
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=18 * mm,
        bottomMargin=15 * mm,
        title=report_title,
        author="",
    )

    def report_progress(current: int, total: int, message: str) -> None:
        if progress_callback:
            progress_callback(current, total, message)

    report_progress(0, 10, "Preparing report")

    story = SectionedStory(selected_section_order)
    schedule_story = []

    # --- START front page ---
    story.section("front_summary")
    story += [
        Paragraph(
            "This report summarises task completion, wait time, lift usage, and resource recommendations derived from the simulation event log.",
            styles["BodyText"],
        ),
        Spacer(1, 6),
        Paragraph("Executive summary", styles["Section"]),
        table_from_df(results["summary"], [70 * mm, 100 * mm], styles),
        NextPageTemplate("landscape"),
        PageBreak(),
    ]

    append_kpi_story(story, results, styles)

    story.section('sla_categories')
    story.append(Paragraph('SLA categories and assigned targets', styles['Section']))
    story.append(Paragraph('Only positive delivery targets and timeframe deadlines are SLA assignments. '
        'The clock starts at task release and ends at recorded task completion. '
        'Effective rules include department and group overrides; disabled generation rules are excluded. '
        'Observed targets below reflect the actual run, including targets that differ from configuration.', styles['BodyText']))
    story.append(Paragraph('Configured assignments', styles['Section']))
    assignments = results.get('sla_assignments', pd.DataFrame()).copy()
    if assignments.empty:
        story.append(Paragraph('No enabled SLA assignments found in the supplied configuration. '
                               'Supply the matching configuration to list configured categories.', styles['BodyText']))
    else:
        category_rows = []
        for category, rules in assignments.groupby('category', sort=True):
            targets = [f'{v:g} s ({v/60:.6g} min)' for v in sorted(rules.target_s.dropna().unique())]
            deadlines = rules.loc[rules.target_s.isna(), 'detail'].str.extract(r'Complete by (\S+)')[0].dropna().unique()
            targets += ['Deadline ' + value for value in sorted(deadlines)]
            category_rows.append({'Category': category, 'Rules': len(rules), 'Scopes': rules.scope.nunique(),
                                  'Assigned targets': '; '.join(targets)})
        story.append(table_from_df(pd.DataFrame(category_rows), [45*mm, 25*mm, 25*mm, 162*mm], styles, format_values=False))
        story.append(Paragraph('Assignment detail', styles['Section']))
        assignments['target_s'] = assignments.target_s.map(lambda v: 'Deadline rule' if pd.isna(v) else f'{v:g} s / {v/60:.6g} min')
        story.append(table_from_df(assignments[['category', 'scope', 'task_type', 'target_s', 'detail', 'source']].rename(
            columns={'category': 'Category', 'scope': 'Scope', 'task_type': 'Task type', 'target_s': 'Target',
                     'detail': 'SLA detail', 'source': 'Rule source'}),
            [30*mm, 40*mm, 28*mm, 23*mm, 91*mm, 45*mm], styles, format_values=False))
    story.append(Paragraph('Targets recorded in this run', styles['Section']))
    observed = results.get('sla_observed_targets', pd.DataFrame()).copy()
    if observed.empty:
        story.append(Paragraph('No requests with a positive SLA target were recorded.', styles['BodyText']))
    else:
        observed['target_s'] = observed.target_s.map(lambda v: f'{v:g}')
        observed['compliance_pct'] = observed.compliance_pct.map(lambda v: '-' if pd.isna(v) else f'{v:.2f}')
        story.append(table_from_df(observed[['category', 'target_s', 'requests', 'completed', 'overdue', 'assessed', 'compliance_pct']].rename(
            columns={'category': 'Logistics stream', 'target_s': 'Target (s)', 'requests': 'Requests', 'completed': 'Completed',
                     'overdue': 'Overdue', 'assessed': 'Assessed', 'compliance_pct': 'Compliance %'}),
            [62*mm, 30*mm, 30*mm, 33*mm, 30*mm, 30*mm, 42*mm], styles, format_values=False))
    story.append(Paragraph('Compliance counts completed tasks within target, divided by assessed tasks: '
        'completed, failed/cancelled, or already overdue. Pending tasks before their deadline are excluded. '
        'The accompanying CSVs contain the configured assignments and observed target groups.', styles['Small']))

    scenario_impact_df = results.get("scenario_impact", pd.DataFrame()).copy()
    story.section("scenario_impact")
    story += [
        Paragraph("Scenario impact and resilience", styles["Section"]),
        Paragraph(
            "This section quantifies operational effects applied by the active scenario, including corridor and AMR degradation, pedestrian route occupancy, wash cycles, payload-width lane restrictions, lift health and charger demand. Run the same configuration in normal operation and each scenario to compare completed work, delay and resource shortfall on a like-for-like basis.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
    ]
    if scenario_impact_df.empty:
        story.append(Paragraph("No scenario impact fields were present in the event log.", styles["BodyText"]))
    else:
        scenario_impact_df = scenario_impact_df.rename(
            columns={
                "metric": "Metric",
                "value": "Value",
                "unit": "Unit",
                "interpretation": "Interpretation",
            }
        )
        story.append(
            table_from_df(
                scenario_impact_df,
                [55 * mm, 28 * mm, 22 * mm, 145 * mm],
                styles,
                right_align=[1],
            )
        )
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "In reduced scenario logging mode, payload names and payload transition rows are intentionally omitted from CSV output. Trip completion, route use, delay, lift, charger and failure information remain available; enable enhanced logging when validating detailed payload state changes.",
            styles["BodyText"],
        ))
    story += [NextPageTemplate("landscape"), PageBreak()]

    task_generation_df = results.get("task_generation_summary", pd.DataFrame()).copy()
    story.section("generated_tasks")
    story += [
        Paragraph("Generated task category summary", styles["Section"]),
        Paragraph(
            "Generated task categories are grouped from simulator task-generated events. Locations use descriptive config names where available.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
    ]
    if task_generation_df.empty:
        story.append(
            Paragraph(
                "No generated task events were identified in the CSV.",
                styles["BodyText"],
            )
        )
    else:
        task_generation_df = task_generation_df.rename(
            columns={
                "category": "Category",
                "tasks": "Tasks",
                "first_time": "First task",
                "last_time": "Last task",
                "pickup_locations": "Pickup locations",
                "dropoff_locations": "Drop-off locations",
                "payloads": "Payloads",
                "human_assist": "Human assist",
            }
        )
        story.append(
            table_from_df(
                task_generation_df,
                [30 * mm, 14 * mm, 32 * mm, 32 * mm, 48 * mm, 48 * mm, 34 * mm, 24 * mm],
                styles,
                right_align=[1],
            )
        )

    deferred_summary_df = results.get(
        "deferred_release_summary", pd.DataFrame()
    ).copy()
    deferred_detail_df = results.get(
        "deferred_release_detail", pd.DataFrame()
    ).copy()
    story.section("deferred_releases")
    story += [
        Paragraph("Deferred task releases", styles["Section"]),
        Paragraph(
            "This section shows how the optional shared-zone workflow changed "
            "job release times. Lower-priority tasks using the option wait until "
            "the preceding return has collected its payload and freed the "
            "drop-off-zone inventory space; unchecked priority categories "
            "continue to release normally.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
    ]
    if deferred_detail_df.empty:
        story.append(
            Paragraph(
                "No jobs were deferred pending a return inventory-space pickup.",
                styles["BodyText"],
            )
        )
    else:
        total_jobs = int(len(deferred_detail_df))
        total_delay = float(
            pd.to_numeric(
                deferred_detail_df.get("delay_s", 0.0), errors="coerce"
            )
            .fillna(0.0)
            .sum()
        )
        average_delay = total_delay / total_jobs if total_jobs else 0.0
        maximum_delay = float(
            pd.to_numeric(
                deferred_detail_df.get("delay_s", 0.0), errors="coerce"
            )
            .fillna(0.0)
            .max()
        )
        story += [
            Paragraph(
                f"<b>{total_jobs}</b> deferred job(s); total workflow deferral "
                f"<b>{escape(fmt_duration(total_delay))}</b>, average "
                f"<b>{escape(fmt_duration(average_delay))}</b>, maximum "
                f"<b>{escape(fmt_duration(maximum_delay))}</b>.",
                styles["BodyText"],
            ),
            Spacer(1, 8),
        ]

        if not deferred_summary_df.empty:
            for column in (
                "total_delay_s",
                "average_delay_s",
                "maximum_delay_s",
            ):
                if column in deferred_summary_df.columns:
                    deferred_summary_df[column] = deferred_summary_df[column].map(
                        fmt_duration
                    )
            deferred_summary_df = deferred_summary_df.rename(
                columns={
                    "category": "Category",
                    "dropoff_zone": "Shared drop-off zone",
                    "deferred_jobs": "Deferred jobs",
                    "total_delay_s": "Total delay",
                    "average_delay_s": "Average delay",
                    "maximum_delay_s": "Maximum delay",
                }
            )
            story.append(
                table_from_df(
                    deferred_summary_df,
                    [42 * mm, 58 * mm, 28 * mm, 35 * mm, 35 * mm, 35 * mm],
                    styles,
                    right_align=[2],
                )
            )
            story.append(Spacer(1, 10))

        deferred_detail_df["delay_s"] = deferred_detail_df["delay_s"].map(
            fmt_duration
        )
        deferred_detail_df = deferred_detail_df.rename(
            columns={
                "category": "Category",
                "department": "Department",
                "dropoff_zone": "Shared zone",
                "task_id": "Deferred job",
                "scheduled_release": "Scheduled release",
                "actual_release": "Actual release",
                "blocking_return_task_id": "Return that cleared space",
                "delay_s": "Deferral",
            }
        )
        story.append(
            table_from_df(
                deferred_detail_df,
                [
                    32 * mm,
                    25 * mm,
                    38 * mm,
                    52 * mm,
                    42 * mm,
                    42 * mm,
                    62 * mm,
                    28 * mm,
                ],
                styles,
            )
        )

    staff_df = results.get("staff_handling_summary", pd.DataFrame()).copy()
    story.section("staff_handling")
    story += [
        Spacer(1, 10),
        Paragraph("Category staff handling", styles["Section"]),
    ]
    if staff_df.empty:
        story.append(
            Paragraph(
                "No category staff handling rows were identified in the CSV.",
                styles["BodyText"],
            )
        )
    else:
        staff_evidence = staff_df.reindex(columns=[
            "category", "recorded_busy_time_s", "evidence_notes"
        ]).copy()
        staff_df = staff_df[["category", "handling_tasks", "people_required",
                             "initial_people", "added_people", "total_handling_time_s"]]
        staff_df["total_handling_time_s"] = staff_df["total_handling_time_s"].map(
            lambda x: fmt_duration(x) if isinstance(x, (int, float)) else x
        )
        staff_df = staff_df.rename(
            columns={
                "category": "Category",
                "handling_tasks": "Handling records",
                "people_required": "People required",
                "initial_people": "Initial",
                "added_people": "Added",
                "total_handling_time_s": "Task handling time",
            }
        )
        story.append(
            table_from_df(
                staff_df,
                [38 * mm, 25 * mm, 25 * mm, 18 * mm, 18 * mm, 32 * mm],
                styles,
                right_align=[1, 2, 3, 4],
            )
        )
        story.append(Paragraph(
            "Task handling time sums the handling and exchange records. Shared "
            "batches can overlap, so this is not staff busy time or a count of unique "
            "physical payloads. Recorded busy handling time merges overlapping "
            "intervals for each person, then sums across people. It excludes travel "
            "and covers only the supplied records; no utilisation percentage is inferred.",
            styles["BodyText"],
        ))
        staff_evidence["recorded_busy_time_s"] = staff_evidence["recorded_busy_time_s"].map(
            lambda value: "Unknown" if pd.isna(value) else fmt_duration(value)
        )
        staff_evidence["evidence_notes"] = staff_evidence["evidence_notes"].fillna("Evidence unavailable")
        story.append(table_from_df(
            staff_evidence.rename(columns={"category": "Category",
                                           "recorded_busy_time_s": "Recorded busy handling",
                                           "evidence_notes": "Evidence and limits"}),
            [38 * mm, 28 * mm, 110 * mm], styles,
        ))

    payload_timetable_df = results.get("payload_handling_timetable", pd.DataFrame()).copy()
    ward_collection_df = results.get("linen_ward_collection", pd.DataFrame()).copy()
    staff_hours_df = results.get("staff_hours_summary", pd.DataFrame()).copy()
    story.section("staff_timetable")
    story += [
        NextPageTemplate("landscape"),
        PageBreak(),
    ]
    if payload_timetable_df.empty:
        story += [
            Paragraph("Staff handling timetable", styles["Section"]),
            Paragraph(
                "No in-hours staff handling timetable could be derived from the CSV.",
                styles["BodyText"],
            ),
        ]
    else:
        category_names = sorted(
            {
                str(value).strip()
                for value in payload_timetable_df["category"].dropna().tolist()
                if str(value).strip()
            },
            key=natural_key,
        )
        for category_index, category in enumerate(category_names):
            if category_index:
                story.append(PageBreak())
            sub = payload_timetable_df[
                payload_timetable_df["category"].astype(str) == category
            ].copy()
            category_key = str(sub["category_key"].iloc[0] or category).strip().lower()
            colour = category_colour(category_key)
            description = (
                "Each entry shows the actual destination-side handling window, including set-down and person pack-away time. Rows are grouped by person."
            )
            if category_key == "linen":
                hours_match = staff_hours_df[
                    staff_hours_df.get("category_key", pd.Series(dtype=str)).astype(str).str.lower()
                    == "linen"
                ] if not staff_hours_df.empty else pd.DataFrame()
                linen_hours = (
                    str(hours_match.iloc[0].get("staff_hours", "09:00-17:00"))
                    if not hours_match.empty
                    else "09:00-17:00"
                )
                description += (
                    f" Linen staff are fixed to {linen_hours}; deliveries whose handling falls outside this window are excluded and listed separately for ward staff collection."
                )
            story += [
                Paragraph("Staff handling timetable", styles["Section"]),
                Paragraph(description, styles["BodyText"]),
                Spacer(1, 8),
                Paragraph(
                    f'<font color="{colour}">{str(category)}</font>',
                    styles["Heading2"],
                ),
                Spacer(1, 4),
                payload_timetable_table(sub, styles),
            ]

    if not ward_collection_df.empty:
        story += [
            PageBreak(),
            Paragraph(
                "Out-of-hours linen deliveries - ward staff collection",
                styles["Section"],
            ),
            Paragraph(
                "These linen deliveries arrive before the linen shift starts or require set-down and pack-away after it finishes. They are removed from the linen staff timetable and must be collected or managed by ward staff at the final delivery destination.",
                styles["BodyText"],
            ),
            Spacer(1, 8),
        ]
        ward_collection_df = ward_collection_df.rename(
            columns={
                "date": "Date",
                "day": "Day",
                "delivery_time": "Delivery",
                "handling_finish": "Handling finish",
                "department": "Department",
                "location": "Final destination",
                "payload": "Payload",
                "task_id": "Task",
                "linen_staff_hours": "Linen staff hours",
                "collection_by": "Collection by",
                "reason": "Reason",
            }
        )
        ward_display_cols = [
            c
            for c in [
                "Date",
                "Day",
                "Delivery",
                "Handling finish",
                "Department",
                "Final destination",
                "Payload",
                "Task",
                "Linen staff hours",
                "Collection by",
                "Reason",
            ]
            if c in ward_collection_df.columns
        ]
        ward_collection_df = ward_collection_df[ward_display_cols]
        width_map = {
            "Date": 20 * mm,
            "Day": 12 * mm,
            "Delivery": 15 * mm,
            "Handling finish": 20 * mm,
            "Department": 24 * mm,
            "Final destination": 34 * mm,
            "Payload": 25 * mm,
            "Task": 30 * mm,
            "Linen staff hours": 22 * mm,
            "Collection by": 20 * mm,
            "Reason": 50 * mm,
        }
        story.append(
            table_from_df(
                ward_collection_df,
                [width_map.get(c, 20 * mm) for c in ward_collection_df.columns],
                styles,
            )
        )

    story.section("method")
    story += [
        NextPageTemplate("standard"),
        PageBreak(),
        Paragraph("Method", styles["Section"]),
        table_from_df(results["methodology"], [38 * mm, 132 * mm], styles),
        PageBreak(),
    ]

    # --- END front page ---

    # --- START AMR List Summary ---

    amr_list_df = results["amr_list"].copy()
    amr_list_df = amr_list_df.drop(columns=["payload_capacity_size_units"])
    story.section("amr_list")
    story += [Spacer(1, 8), Paragraph("AMR list", styles["Section"])]

    if amr_list_df.empty:
        story.append(
            Paragraph(
                "No AMR parameter data was provided from the config JSON.",
                styles["BodyText"],
            )
        )
    else:
        amr_list_df = amr_list_df.rename(
            columns={
                "amr": "AMR ID",
                "quantity": "Qty",
                "payload_capacity_kg": "Payload (kg)",
                "speed_m_per_sec": "Speed (m/s)",
                "battery_capacity_kwh": "Battery (kWh)",
                "battery_charge_rate_kw": "Charge rate (kW)",
                "recharge_threshold_percent": "Recharge threshold (%)",
                "battery_soc_percent": "Start SoC %",
                "start_location": "Start location",
            }
        )
        story.append(
            table_from_df(
                amr_list_df,
                [
                    18 * mm,
                    12 * mm,
                    18 * mm,
                    16 * mm,
                    18 * mm,
                    18 * mm,
                    18 * mm,
                    18 * mm,
                    25 * mm,
                ],
                styles,
            )
        )

    story += [NextPageTemplate("landscape"), PageBreak()]

    # --- END AMR List Summary ---

    # --- START AMR Fleet Summary ---

    amr_df = results["amr_summary"].copy()
    story.section("amr_fleet")

    amr_df_total = {
        "amr": "Total",
        "tasks_total": amr_df["tasks_total"].sum(),
        "tasks_completed": amr_df["tasks_completed"].sum(),
        "tasks_failed": amr_df["tasks_failed"].sum(),
        "routes": amr_df.get("routes", pd.Series(dtype=float)).sum(),
        "total_task_time_s": amr_df["total_task_time_s"].sum(),
        "total_route_time_s": amr_df.get("total_route_time_s", amr_df["total_task_time_s"]).sum(),
        "total_wait_s": amr_df["total_wait_s"].sum(),
        "avg_task_time_s": amr_df["avg_task_time_s"].mean(),
        "total_distance_km": amr_df["total_distance_km"].sum(),
        "recharges": amr_df["recharges"].sum(),
        "recharge_energy_kwh": amr_df["recharge_energy_kwh"].sum(),
    }

    amr_df = pd.concat([amr_df, pd.DataFrame([amr_df_total])], ignore_index=True)
    if "total_route_time_s" not in amr_df.columns:
        amr_df["total_route_time_s"] = amr_df["total_task_time_s"]
    amr_df["total_task_time_s"] = amr_df["total_task_time_s"].map(
        lambda x: fmt_duration(x) if isinstance(x, (int, float)) else x
    )
    amr_df["total_route_time_s"] = amr_df["total_route_time_s"].map(
        lambda x: fmt_duration(x) if isinstance(x, (int, float)) else x
    )
    amr_df["total_wait_s"] = amr_df["total_wait_s"].map(
        lambda x: fmt_duration(x) if isinstance(x, (int, float)) else x
    )
    amr_df["avg_task_time_s"] = amr_df["avg_task_time_s"].map(
        lambda x: fmt_duration(x) if isinstance(x, (int, float)) else x
    )

    amr_df = amr_df.sort_values(by="amr", key=lambda col: col.map(natural_key))
    amr_df = amr_df.rename(
        columns={
            "amr": "AMR ID",
            "tasks_total": "Tasks",
            "tasks_completed": "Completed",
            "tasks_failed": "Failed",
            "routes": "Routes",
            "total_task_time_s": "Route time",
            "total_route_time_s": "Route duration",
            "total_wait_s": "Wait time",
            "avg_task_time_s": "Avg task",
            "total_distance_km": "Distance (km)",
            "recharges": "Recharges",
            "recharge_energy_kwh": "Energy kWh",
        }
    )

    # Keep a stable, compact column order.
    amr_display_cols = [
        c
        for c in [
            "AMR ID",
            "Tasks",
            "Completed",
            "Failed",
            "Routes",
            "Route duration",
            "Wait time",
            "Avg task",
            "Distance (km)",
            "Recharges",
            "Energy kWh",
        ]
        if c in amr_df.columns
    ]
    amr_df = amr_df[amr_display_cols]

    amr_df_table = table_from_df(
        amr_df,
        [25 * mm, 17 * mm, 29 * mm, 17 * mm, 18 * mm, 29 * mm, 26 * mm, 22 * mm, 27 * mm, 29 * mm, 23 * mm][: len(amr_df.columns)],
        styles,
        right_align=list(range(1, len(amr_df.columns))),
    )
    amr_df_table_last_row = len(amr_df)
    amr_df_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, amr_df_table_last_row),
                    (-1, amr_df_table_last_row),
                    colors.HexColor("#d9e2f3"),
                ),
                (
                    "FONTNAME",
                    (0, amr_df_table_last_row),
                    (-1, amr_df_table_last_row),
                    "Helvetica-Bold",
                ),
                (
                    "LINEABOVE",
                    (0, amr_df_table_last_row),
                    (-1, amr_df_table_last_row),
                    1,
                    colors.black,
                ),
            ]
        )
    )

    # Add AMR DF to story
    story += [
        Paragraph("AMR fleet summary", styles["Section"]),
        Paragraph("All times in the format of mm:ss", styles["BodyText"]),
        Spacer(1, 8),
        amr_df_table,
        NextPageTemplate("standard"),
        PageBreak(),
    ]

    # --- END AMR Fleet Summary ---

    # --- START AMR Utilisation Summary ---

    amr_utilisation_df = results["utilisation_summary"].copy()
    story.section("amr_utilisation")
    amr_utilisation_df = amr_utilisation_df.drop(
        columns=["tasks_total", "total_task_time_s", "total_route_time_s", "total_wait_s"],
        errors="ignore",
    )
    amr_utilisation_df = amr_utilisation_df.sort_values(
        by="amr",
        key=lambda col: col.map(natural_key),
    )
    amr_utilisation_df = amr_utilisation_df.rename(
        columns={
            "amr": "AMR ID",
            "routes": "Routes",
            "utilisation_pct": "Util %",
            "idle_pct": "Idle %",
            "wait_share_pct": "Wait %",
        }
    )

    story += [
        Paragraph("AMR Utilisation, Idle and Wait %", styles["Section"]),
        table_from_df(
            amr_utilisation_df,
            [25 * mm, 20 * mm, 25 * mm, 25 * mm, 25 * mm][: len(amr_utilisation_df.columns)],
            styles,
        ),
        Spacer(1, 8),
    ]

    # --- END AMR Utilisation Summary ---

    # --- START AMR Recharge Summary ---
    story += [Spacer(1, 8), Paragraph("Scheduled AMR recharge summary", styles["Section"])]
    story.append(Paragraph('Recharge segments describe scheduled input. The battery balance below uses only energy credited to the model battery.', styles['BodyText']))
    recharge_df = results["recharge_summary"].copy()

    if recharge_df.empty:
        story.append(
            Paragraph(
                "No AMR recharge events were identified in the CSV.",
                styles["BodyText"],
            )
        )
    else:
        recharge_df["recharge_time_s"] = recharge_df["recharge_time_s"].map(
            fmt_duration
        )
        recharge_df["recharge_energy_kwh"] = recharge_df["recharge_energy_kwh"].map(
            lambda value: f'{value:.2f}' if pd.notna(value) else 'Unknown'
        )
        recharge_df = recharge_df.rename(
            columns={
                "amr": "AMR ID",
                "recharges": "Recharges",
                "recharge_energy_kwh": "Recharge kWh",
                "recharge_time_s": "Recharge time",
            }
        )
        story.append(
            table_from_df(
                recharge_df,
                [28 * mm, 22 * mm, 32 * mm, 32 * mm],
                styles,
                right_align=[1, 2],
            )
        )

    story += [PageBreak()]

    # --- END AMR Recharge Summary ---

    battery_df = results.get('battery_balance', pd.DataFrame()).copy()
    story.append(Paragraph('Recorded model battery balance', styles['Section']))
    story.append(Paragraph(
        'Initial + applied charge - planned traction = final model battery. Delivery traction is booked when a route is committed. '
        'In-place route charging is credited during commitment; separate charging is credited on completion. '
        'This verifies model accounting, not measured or continuously interpolated battery state. All energy values are kWh.',
        styles['BodyText']))
    if battery_df.empty:
        story.append(Paragraph('Battery balance is not established by this log.', styles['BodyText']))
    else:
        for column in ('initial_kwh', 'applied_charge_kwh', 'planned_traction_kwh', 'final_kwh', 'residual_kwh'):
            battery_df.loc[~battery_df['known'].astype(bool), column] = float('nan')
            battery_df[column] = battery_df[column].map(
                lambda value: f'{value:.2f}' if pd.notna(value) else 'Unknown')
        battery_df = battery_df[['amr_id', 'initial_kwh', 'applied_charge_kwh', 'planned_traction_kwh',
                                 'final_kwh', 'residual_kwh', 'status']].rename(columns={
            'amr_id': 'AMR', 'initial_kwh': 'Initial', 'applied_charge_kwh': 'Applied charge',
            'planned_traction_kwh': 'Traction', 'final_kwh': 'Final', 'residual_kwh': 'Residual', 'status': 'Evidence'})
        story.append(table_from_df(battery_df, [28 * mm, 24 * mm, 27 * mm, 24 * mm, 24 * mm, 25 * mm, 30 * mm], styles))
    story.append(PageBreak())

    # --- START Lift usage Summary ---

    story.section("lift_usage")
    story += [
        Paragraph("Lift usage summary", styles["Section"]),
        Paragraph("All times in the format of mm:ss", styles["BodyText"]),
        Spacer(1, 8),
    ]

    story += [Spacer(1, 8), Paragraph("Recorded route-plan energy", styles["Section"])]
    story.append(Paragraph(
        "Movement records are counted once, including shared journeys. Values describe "
        "planned energy, not measured execution. Charging input and stationary robot "
        "auxiliaries are excluded. Missing or legacy attribution is not zero consumption.",
        styles['BodyText']))
    energy_df = results.get('energy_summary', pd.DataFrame()).copy()
    if not energy_df.empty:
        energy_df['planned_kwh'] = energy_df['planned_kwh'].map(
            lambda value: f'{value:.2f}' if pd.notna(value) else 'Not established')
        energy_df = energy_df[['metric', 'planned_kwh', 'coverage']].rename(columns={
            'metric': 'Source', 'planned_kwh': 'Plan kWh', 'coverage': 'Evidence'})
        story.append(table_from_df(energy_df, [66 * mm, 44 * mm, 60 * mm], styles))
    story += [Spacer(1, 8), Paragraph("Lift route-plan energy", styles["Section"])]

    lift_df = results["lift_summary"].copy()
    if lift_df.empty:
        story.append(
            Paragraph(
                "No lift_transfer segments were identified in the CSV.",
                styles["BodyText"],
            )
        )
    else:
        lift_df_total = {
            "lift_id": "Total",
            "trips": lift_df["trips"].sum(),
            "total_lift_time_s": lift_df["total_lift_time_s"].sum(),
            "avg_trip_s": lift_df["avg_trip_s"].mean(),
            "lift_energy_kwh": (lift_df["lift_energy_kwh"].sum()
                                if lift_df["lift_energy_kwh"].notna().all() else float('nan')),
            "utilisation_pct": "",
            "idle_pct": "",
        }

        lift_df = pd.concat([lift_df, pd.DataFrame([lift_df_total])], ignore_index=True)
        lift_df['lift_energy_kwh'] = lift_df['lift_energy_kwh'].map(
            lambda value: f'{value:.2f}' if pd.notna(value) else 'Not established')
        lift_df["total_lift_time_s"] = lift_df["total_lift_time_s"].map(
            lambda x: fmt_duration(x) if isinstance(x, (int, float)) else x
        )
        lift_df["avg_trip_s"] = lift_df["avg_trip_s"].map(
            lambda x: fmt_duration(x) if isinstance(x, (int, float)) else x
        )

        lift_df = lift_df.rename(
            columns={
                "lift_id": "Lift",
                "trips": "Trips",
                "total_lift_time_s": "Total lift time",
                "lift_energy_kwh": "Plan kWh",
                "avg_trip_s": "Avg trip",
                "utilisation_pct": "Util %",
                "idle_pct": "Idle %",
            }
        )

        lift_df_table = table_from_df(
            lift_df,
            [28 * mm, 16 * mm, 34 * mm, 26 * mm, 25 * mm, 18 * mm, 18 * mm],
            styles,
            right_align=[1, 4, 5],
        )
        lift_df_table_last_row = len(lift_df)
        lift_df_table.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, lift_df_table_last_row),
                        (-1, lift_df_table_last_row),
                        colors.HexColor("#d9e2f3"),
                    ),
                    (
                        "FONTNAME",
                        (0, lift_df_table_last_row),
                        (-1, lift_df_table_last_row),
                        "Helvetica-Bold",
                    ),
                    (
                        "LINEABOVE",
                        (0, lift_df_table_last_row),
                        (-1, lift_df_table_last_row),
                        1,
                        colors.black,
                    ),
                ]
            )
        )
        story.append(lift_df_table)

    # --- END Lift usage Summary ---

    # --- START Lift usage profile graph ---

    story.section("lift_usage_profile")
    story += [
        Paragraph("Lift usage profile", styles["Section"]),
        Paragraph(
            "Trips are counted in 30-minute time-of-day intervals and broken down by lift. Multi-day simulations are aggregated by clock time so the graph shows the daily demand profile.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
    ]
    lift_profile_df = results.get("lift_usage_profile", pd.DataFrame()).copy()
    if lift_profile_df.empty:
        story.append(
            Paragraph(
                "No lift_transfer or lift_reposition segments were available for a lift usage profile.",
                styles["BodyText"],
            )
        )
    else:
        a3_width, a3_height = landscape(A3)
        chart_width = a3_width - doc.leftMargin - doc.rightMargin
        chart_height = a3_height - doc.topMargin - doc.bottomMargin - 28 * mm
        story.append(LiftUsageProfileChart(lift_profile_df, chart_width, chart_height))

    # --- END Lift usage profile graph ---

    story.section("journey_flows")
    observation = results.get("journey_observation", {})
    story += [
        Paragraph("Journey origins, destinations and returns", styles["Section"]),
        Paragraph(
            f"Source: {escape(csv_path.name)}. Observation: "
            f"{escape(str(observation.get('start', 'Unknown')))} to "
            f"{escape(str(observation.get('finish', 'Unknown')))}.", styles["BodyText"]),
        Paragraph(
            "Each journey is a delivery, collection or recorded empty AMR return task. Origins and destinations use "
            "the recorded request endpoints; no L00 start or finish is assumed. Numeric "
            "floor 0 is shown as L00. Return rows use their own recorded pickup and drop-off, "
            "which may include shared drop-off zones. Department lists describe the endpoint; "
            "the requesting department is recorded separately in the journey CSV.", styles["BodyText"]),
        Paragraph(
            "Counts cover the source simulation and separate completed, failed and incomplete "
            "requests. Task counts are not lift trip counts: multi-stop tasks may share an AMR. "
            "The companion _journeys.csv includes locations, levels, departments, payloads, "
            "assignment/completion times and parent task IDs for recorded returns. "
            "_journey_flows.csv contains this summary. _lift_movements.csv records actual "
            "lift transfers and empty lift repositioning with times, levels and task IDs. "
            "Empty AMR travel can also appear in lift transfers. Unknown metadata remains "
            "explicit; supply the simulation's matching JSON configuration for departments.", styles["BodyText"]),
        Spacer(1, 8),
    ]
    flows = results.get("journey_flow_summary", pd.DataFrame()).copy()
    if flows.empty:
        story.append(Paragraph("No task request endpoints were available in the event log.", styles["BodyText"]))
    else:
        story.append(table_from_df(flows.rename(columns={
            "journey_type": "Journey type", "origin_level": "From level",
            "origin_department": "From department", "destination_level": "To level",
            "destination_department": "To department", "outcome": "Outcome", "journeys": "Journeys",
        }), [34*mm, 22*mm, 120*mm, 22*mm, 120*mm, 32*mm, 25*mm], styles, right_align=[6]))

    # --- START Lift trip cohorts ---

    story.section("lift_trip_cohorts")
    story += [
        Paragraph("Lift trip cohorts", styles["Section"]),
        Paragraph(
            "Lift transfer and reposition trips are grouped into chronological "
            "date-and-time cohorts. Each cell is the total number of trips made "
            "by that lift in the cohort. The tables show cohorts containing at "
            "least one movement; the companion CSV retains the complete timeline, "
            "including zero-movement cohorts, and also separates transfer and "
            "reposition trips and includes travel-time totals.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
    ]

    hourly_matrix = lift_trip_cohort_matrix(
        results.get("lift_trip_cohorts_hourly", pd.DataFrame())
    )
    five_minute_matrix = lift_trip_cohort_matrix(
        results.get("lift_trip_cohorts_5min", pd.DataFrame())
    )
    if hourly_matrix.empty and five_minute_matrix.empty:
        story.append(
            Paragraph(
                "No lift_transfer or lift_reposition segments were available for "
                "lift trip cohorts.",
                styles["BodyText"],
            )
        )
    else:
        if not hourly_matrix.empty:
            story += [
                Paragraph("Hourly trips per lift", styles["Heading3"]),
                table_from_df(
                    hourly_matrix,
                    [28 * mm, 24 * mm]
                    + [20 * mm] * max(0, len(hourly_matrix.columns) - 2),
                    styles,
                    right_align=list(range(1, len(hourly_matrix.columns))),
                ),
            ]
        if not five_minute_matrix.empty:
            if not hourly_matrix.empty:
                story.append(PageBreak())
            story += [
                Paragraph("5-minute trips per lift", styles["Heading3"]),
                Paragraph(
                    "The calendar date is retained so the same clock time on "
                    "different simulation days is never combined.",
                    styles["BodyText"],
                ),
                Spacer(1, 6),
                table_from_df(
                    five_minute_matrix,
                    [28 * mm, 24 * mm]
                    + [20 * mm] * max(0, len(five_minute_matrix.columns) - 2),
                    styles,
                    right_align=list(range(1, len(five_minute_matrix.columns))),
                ),
            ]

    # --- END Lift trip cohorts ---

    # --- START Lift wait time profiles ---

    story.section("lift_wait_profiles")
    story += [
        Paragraph("Lift wait time profiles", styles["Section"]),
        Paragraph(
            "Wait statistics use positive AMR lift-wait events. The profile shows "
            "the mean wait in each 30-minute time-of-day interval, aggregated across "
            "all simulation days. Lifts without a recorded wait remain visible with zero values.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
    ]

    lift_wait_summary_df = results.get(
        "lift_wait_summary", pd.DataFrame()
    ).copy()
    if lift_wait_summary_df.empty:
        story.append(
            Paragraph(
                "No lift usage or lift wait events were available for wait statistics.",
                styles["BodyText"],
            )
        )
    else:
        for column in (
            "minimum_wait_s",
            "mean_wait_s",
            "maximum_wait_s",
            "total_wait_s",
        ):
            lift_wait_summary_df[column] = lift_wait_summary_df[column].map(
                fmt_wait_duration
            )
        lift_wait_summary_df = lift_wait_summary_df.rename(
            columns={
                "lift_id": "Lift",
                "wait_events": "Wait events",
                "minimum_wait_s": "Minimum wait",
                "mean_wait_s": "Mean wait",
                "maximum_wait_s": "Maximum wait",
                "total_wait_s": "Total wait",
            }
        )
        story.append(
            table_from_df(
                lift_wait_summary_df,
                [30 * mm, 25 * mm, 34 * mm, 34 * mm, 34 * mm, 34 * mm],
                styles,
                right_align=[1],
            )
        )
        story.append(Spacer(1, 10))

    lift_wait_profile_df = results.get(
        "lift_wait_profile", pd.DataFrame()
    ).copy()
    if lift_wait_profile_df.empty:
        story.append(
            Paragraph(
                "No lift wait profile data was available.", styles["BodyText"]
            )
        )
    else:
        a3_width, _a3_height = landscape(A3)
        chart_width = a3_width - doc.leftMargin - doc.rightMargin
        story.append(
            LiftUsageProfileChart(
                lift_wait_profile_df,
                chart_width,
                145 * mm,
                value_column="mean_wait_s",
                y_axis_label="Mean lift wait per 30 minute interval",
                empty_message="No lift wait profile data was available.",
                integer_ticks=False,
            )
        )

    # --- END Lift wait time profiles ---

    # --- START Lift wait Summary ---

    schedule_story += [
        NextPageTemplate("landscape"),
        PageBreak(),
        Paragraph("Detailed schedules", styles["Section"]),
        Paragraph("Lift wait schedule", styles["Heading3"]),
    ]

    lift_wait_df = results["lift_wait_schedule"].copy()
    if lift_wait_df.empty:
        schedule_story.append(
            Paragraph(
                "No lift wait events were identified in the CSV.",
                styles["BodyText"],
            )
        )
    else:
        has_dt = pd.api.types.is_datetime64_any_dtype(lift_wait_df["time"]) or any(
            hasattr(v, "strftime") for v in lift_wait_df["time"].dropna().tolist()
        )
        lift_wait_df["time"] = lift_wait_df["time"].map(
            lambda v: fmt_ts(v, has_dt) if not pd.isna(v) else "-"
        )
        lift_wait_df["wait_s"] = lift_wait_df["wait_s"].map(fmt_duration)
        lift_wait_df = lift_wait_df.rename(
            columns={
                "time": "Time",
                "amr": "AMR",
                "task_id": "Task",
                "lift_id": "Lift",
                "from": "From",
                "to": "To",
                "wait_s": "Wait",
            }
        )
        schedule_story.append(
            table_from_df(
                lift_wait_df,
                [32 * mm, 20 * mm, 45 * mm, 16 * mm, 26 * mm, 26 * mm, 16 * mm],
                styles,
            )
        )

    # --- END Lift wait Summary ---

    report_progress(3, 10, "Added summary and method")

    # --- START Payload Summary ---

    story.section("payload_summary")
    story += [
        NextPageTemplate("standard"),
        PageBreak(),
        Paragraph("Payload summary", styles["Section"]),
        Paragraph("Runtime payloads is the peak per payload type, including stored, carried, staged and unconfirmed containers. "
                  "Issued instances includes physical containers later removed; planned-only IDs are excluded. "
                  "A dash means the available log does not establish that value. Older storage-only population summaries are insufficient.", styles["BodyText"]),
    ]

    payload_df = results["payload_schedule"].copy()
    if payload_df.empty:
        story.append(
            Paragraph(
                "No payload schedule data was identified in the CSV.",
                styles["BodyText"],
            )
        )
    else:
        payload_df = payload_df.rename(
            columns={
                "payload": "Payload",
                "total_runtime_payloads": "Runtime payloads",
                "unique_payloads_moved": "Unique transported",
                "tasks": "Tasks using payload",
                "known_payload_instances": "Issued instances",
                "payload_weight_kg": "Payload kg",
            }
        )
        display_cols = [
            c
            for c in ["Payload", "Runtime payloads", "Unique transported", "Tasks using payload", "Issued instances", "Payload kg"]
            if c in payload_df.columns
        ]
        payload_df = payload_df[display_cols]
        story.append(
            table_from_df(
                payload_df,
                [42 * mm, 25 * mm, 27 * mm, 27 * mm, 25 * mm, 22 * mm][: len(payload_df.columns)],
                styles,
                right_align=list(range(1, len(payload_df.columns))),
            )
        )

    # --- END Payload Summary ---

    # --- START Location space utilisation ---

    story.section("location_space")
    story += [
        NextPageTemplate("landscape"),
        PageBreak(),
        Paragraph("Location space utilisation", styles["Section"]),
        Paragraph(
            "Locations are mapped to departments and service categories from the simulator JSON. Area is calculated from each location bounding box; utilisation compares defined inventory-space area with the location area where inventory spaces are present.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
    ]

    location_util_df = results.get("location_space_utilisation", pd.DataFrame()).copy()
    if location_util_df.empty:
        story.append(
            Paragraph(
                "No location space utilisation data was available. Provide --config-json to include location, department and inventory-space analysis.",
                styles["BodyText"],
            )
        )
    else:
        location_util_df = location_util_df.rename(
            columns={
                "department": "Department",
                "category": "Category",
                "location": "Location",
                "floor": "Floor",
                "length_m": "Length m",
                "width_m": "Width m",
                "area_m2": "Area m²",
                "inventory_spaces_current": "Spaces",
                "deliveries_completed": "Completed",
                "failed_delivery_attempts": "Failed",
                "capacity_related_failures": "Capacity failures",
                "utilisation_pct": "Util %",
                "peak_payload_count": "Peak payload count",
                "peak_area_used_m2": "Peak area used m²",
                "peak_volume_m3": "Peak volume m³",
                "peak_utilisation_pct": "Peak utilisation %",
                "recommended_area_m2": "Recommended area m²",
                "recommended_inventory_spaces": "Recommended spaces",
            }
        )
        location_util_display_cols = [
            c for c in [
                "Department",
                "Category",
                "Location",
                "Floor",
                "Area m²",
                "Spaces",
                "Completed",
                "Failed",
                "Capacity failures",
                "Peak payload count",
                "Peak area used m²",
                "Peak utilisation %",
                "Recommended area m²",
                "Recommended spaces",
            ] if c in location_util_df.columns
        ]
        location_util_df = location_util_df[location_util_display_cols]
        width_map = {
            "Department": 25 * mm,
            "Category": 18 * mm,
            "Location": 35 * mm,
            "Floor": 10 * mm,
            "Area m²": 15 * mm,
            "Spaces": 12 * mm,
            "Completed": 14 * mm,
            "Failed": 12 * mm,
            "Capacity failures": 20 * mm,
            "Peak payload count": 18 * mm,
            "Peak area used m²": 20 * mm,
            "Peak utilisation %": 18 * mm,
            "Recommended area m²": 22 * mm,
            "Recommended spaces": 22 * mm,
        }
        story.append(
            table_from_df(
                location_util_df,
                [width_map.get(c, 18 * mm) for c in location_util_df.columns],
                styles,
                right_align=list(range(3, len(location_util_df.columns))),
            )
        )

    # --- END Location space utilisation ---

    # --- START Peak location occupancy ---

    story.section("peak_occupancy")
    story += [
        PageBreak(),
        Paragraph("Peak location occupancy", styles["Section"]),
        Paragraph(
            "Peak occupancy is calculated in the report from simulator location_payload_enter and location_payload_exit rows. It records the maximum simultaneous unique payload instances, footprint and volume seen at each location during operating conditions.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
    ]

    peak_location_df = results.get("location_peak_occupancy", pd.DataFrame()).copy()
    if peak_location_df.empty:
        story.append(
            Paragraph(
                "No payload location movement rows were identified in the simulation event log. Run the simulator with verbose CSV output from the updated simulator to include this section.",
                styles["BodyText"],
            )
        )
    else:
        peak_location_df = peak_location_df.rename(
            columns={
                "department": "Department",
                "category": "Category",
                "location": "Location",
                "inventory_spaces_disabled": "Inventory disabled",
                "configured_inventory_area_m2": "Configured inventory area m²",
                "peak_payload_count": "Peak unique payloads",
                "peak_area_used_m2": "Peak area used m²",
                "peak_volume_m3": "Peak volume m³",
                "recommended_area_m2": "Recommended area m²",
                "recommended_volume_m3": "Recommended volume m³",
            }
        )
        peak_location_df = peak_location_df[
            [
                c for c in [
                    "Department",
                    "Category",
                    "Location",
                    "Inventory disabled",
                    "Configured inventory area m²",
                    "Peak unique payloads",
                    "Peak area used m²",
                    "Peak volume m³",
                    "Recommended area m²",
                    "Recommended volume m³",
                ] if c in peak_location_df.columns
            ]
        ]
        story.append(
            table_from_df(
                peak_location_df,
                [25 * mm, 18 * mm, 35 * mm, 20 * mm, 25 * mm, 18 * mm, 22 * mm, 22 * mm, 23 * mm, 23 * mm][: len(peak_location_df.columns)],
                styles,
                right_align=list(range(3, len(peak_location_df.columns))),
            )
        )

    # --- END Peak location occupancy ---

    # --- START Drop-off zone peak occupancy ---

    story.section("dropoff_zone_occupancy")
    story += [
        PageBreak(),
        Paragraph("Drop-off zone peak occupancy", styles["Section"]),
        Paragraph(
            "This section includes only locations assigned as department drop-off zones. "
            "It reports the maximum number of flexible payload spaces occupied at any "
            "time in each zone and the true simultaneous maximum across all zones. "
            "The simultaneous total is reconstructed from payload enter/exit events; it "
            "does not add together per-zone peaks that occurred at different times.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
    ]

    zone_summary_df = results.get(
        "dropoff_zone_occupancy_summary", pd.DataFrame()
    ).copy()
    zone_peak_df = results.get(
        "dropoff_zone_peak_occupancy", pd.DataFrame()
    ).copy()
    zone_peak_payloads_df = results.get(
        "dropoff_zone_payloads_at_network_peak", pd.DataFrame()
    ).copy()
    if zone_peak_df.empty:
        story.append(
            Paragraph(
                "No configured department drop-off zones were found. Provide the "
                "simulation JSON and assign drop-off-zone locations to department "
                "task categories to populate this section.",
                styles["BodyText"],
            )
        )
    else:
        if not zone_summary_df.empty:
            zone_summary_df = zone_summary_df.rename(
                columns={"metric": "Metric", "value": "Value"}
            )
            story += [
                Paragraph("Drop-off zone network maximum", styles["Heading3"]),
                table_from_df(
                    zone_summary_df,
                    [95 * mm, 55 * mm],
                    styles,
                    right_align=[1],
                ),
                Spacer(1, 10),
            ]

        if not zone_peak_payloads_df.empty:
            maximum_time = str(
                zone_peak_payloads_df.iloc[0].get("time_of_maximum", "") or ""
            )
            zone_peak_payloads_df = zone_peak_payloads_df.rename(
                columns={
                    "department": "Department",
                    "location": "Drop-off zone",
                    "inventory_space": "Inventory space",
                    "payload": "Payload",
                    "payload_instance_id": "Payload instance",
                    "task_id": "Task",
                    "dropped_at": "Dropped into zone",
                }
            )
            zone_peak_payloads_df = zone_peak_payloads_df[
                [
                    column
                    for column in (
                        "Department",
                        "Drop-off zone",
                        "Inventory space",
                        "Payload",
                        "Payload instance",
                        "Task",
                        "Dropped into zone",
                    )
                    if column in zone_peak_payloads_df.columns
                ]
            ]
            story += [
                Paragraph(
                    f"Payloads held at simultaneous maximum ({maximum_time})",
                    styles["Heading3"],
                ),
                Paragraph(
                    "These are the physical payloads occupying drop-off-zone "
                    "inventory spaces at the instant the network-wide maximum occurred.",
                    styles["BodyText"],
                ),
                Spacer(1, 5),
                table_from_df(
                    zone_peak_payloads_df,
                    [
                        34 * mm,
                        38 * mm,
                        38 * mm,
                        38 * mm,
                        42 * mm,
                        34 * mm,
                        42 * mm,
                    ][: len(zone_peak_payloads_df.columns)],
                    styles,
                ),
                Spacer(1, 10),
            ]

        # Keep the heading with at least the table header and first data row.
        story.append(CondPageBreak(35 * mm))
        story.append(Paragraph("Peak by drop-off zone", styles["Heading3"]))

        zone_peak_df = zone_peak_df.rename(
            columns={
                "department": "Department",
                "category": "Assigned categories",
                "location": "Drop-off zone",
                "configured_spaces": "Configured spaces",
                "peak_occupied_spaces": "Max occupied spaces",
                "free_spaces_at_peak": "Free at peak",
                "space_shortfall_at_peak": "Shortfall at peak",
                "peak_occupancy_pct": "Peak occupancy %",
                "peak_area_used_m2": "Peak area used m2",
                "peak_volume_m3": "Peak volume m3",
            }
        )
        zone_peak_df = zone_peak_df[
            [
                column
                for column in (
                    "Department",
                    "Assigned categories",
                    "Drop-off zone",
                    "Configured spaces",
                    "Max occupied spaces",
                    "Free at peak",
                    "Shortfall at peak",
                    "Peak occupancy %",
                    "Peak area used m2",
                    "Peak volume m3",
                )
                if column in zone_peak_df.columns
            ]
        ]
        zone_widths = {
            "Department": 32 * mm,
            "Assigned categories": 38 * mm,
            "Drop-off zone": 40 * mm,
            "Configured spaces": 23 * mm,
            "Max occupied spaces": 27 * mm,
            "Free at peak": 20 * mm,
            "Shortfall at peak": 23 * mm,
            "Peak occupancy %": 23 * mm,
            "Peak area used m2": 23 * mm,
            "Peak volume m3": 23 * mm,
        }
        story.append(
            table_from_df(
                zone_peak_df,
                [zone_widths.get(column, 22 * mm) for column in zone_peak_df.columns],
                styles,
                right_align=list(range(3, len(zone_peak_df.columns))),
            )
        )

    # --- END Drop-off zone peak occupancy ---

    # --- START Failed delivery analysis ---

    story.section("failed_delivery")
    story += [
        PageBreak(),
        Paragraph("Failed delivery analysis", styles["Section"]),
        Paragraph(
            "Failed deliveries are grouped with their logged reason and payload dimensions so capacity failures can be traced back to the attempted load size.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
    ]

    failed_delivery_df = results.get("failed_delivery_summary", pd.DataFrame()).copy()
    if failed_delivery_df.empty:
        story.append(
            Paragraph(
                "No failed deliveries were identified in the simulation event log.",
                styles["BodyText"],
            )
        )
    else:
        failed_delivery_df = failed_delivery_df.rename(
            columns={
                "time": "Time",
                "task_id": "Task",
                "amr": "AMR",
                "department": "Department",
                "category": "Category",
                "location": "Location",
                "payload": "Payload",
                "payload_length_m": "Payload L",
                "payload_width_m": "Payload W",
                "payload_height_m": "Payload H",
                "payload_area_m2": "Payload area",
                "failure_reason": "Failure reason",
            }
        )
        story.append(
            table_from_df(
                failed_delivery_df,
                [
                    26 * mm,
                    25 * mm,
                    14 * mm,
                    25 * mm,
                    18 * mm,
                    30 * mm,
                    24 * mm,
                    13 * mm,
                    13 * mm,
                    13 * mm,
                    16 * mm,
                    45 * mm,
                ],
                styles,
                right_align=[7, 8, 9, 10],
            )
        )

    failed_payload_sizes_df = results.get("failed_payload_sizes", pd.DataFrame()).copy()
    if not failed_payload_sizes_df.empty:
        story += [Spacer(1, 8), Paragraph("Failed payload sizes", styles["Heading3"])]
        failed_payload_sizes_df = failed_payload_sizes_df.rename(
            columns={
                "location": "Location",
                "payload": "Payload",
                "payload_length_m": "Length m",
                "payload_width_m": "Width m",
                "payload_height_m": "Height m",
                "failed_count": "Failed count",
            }
        )
        story.append(
            table_from_df(
                failed_payload_sizes_df,
                [45 * mm, 45 * mm, 22 * mm, 22 * mm, 22 * mm, 24 * mm],
                styles,
                right_align=[2, 3, 4, 5],
            )
        )

    # --- END Failed delivery analysis ---

    # --- START Location recommendations ---

    story.section("location_recommendations")
    story += [
        PageBreak(),
        Paragraph("Location storage recommendations", styles["Section"]),
        Paragraph(
            "Recommended area is based on the greater of capacity-failure demand and the report-calculated peak simultaneous payload storage demand from payload enter/exit events.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
    ]

    location_recommendations_df = results.get(
        "location_recommendations", pd.DataFrame()
    ).copy()
    if location_recommendations_df.empty:
        story.append(
            Paragraph(
                "No location recommendation data was available.",
                styles["BodyText"],
            )
        )
    else:
        location_recommendations_df = location_recommendations_df.rename(
            columns={
                "department": "Department",
                "category": "Category",
                "location": "Location",
                "current_area_m2": "Current area m²",
                "peak_area_used_m2": "Peak area used m²",
                "recommended_area_m2": "Recommended area m²",
                "additional_area_m2": "Additional area m²",
                "current_inventory_spaces": "Current spaces",
                "recommended_inventory_spaces": "Recommended spaces",
                "additional_inventory_spaces": "Additional spaces",
                "reason": "Reason",
            }
        )
        recommendation_display_cols = [
            c for c in [
                "Department",
                "Category",
                "Location",
                "Current area m²",
                "Peak area used m²",
                "Recommended area m²",
                "Additional area m²",
                "Current spaces",
                "Recommended spaces",
                "Additional spaces",
                "Reason",
            ] if c in location_recommendations_df.columns
        ]
        location_recommendations_df = location_recommendations_df[recommendation_display_cols]
        rec_width_map = {
            "Department": 25 * mm,
            "Category": 18 * mm,
            "Location": 35 * mm,
            "Current area m²": 20 * mm,
            "Peak area used m²": 20 * mm,
            "Recommended area m²": 23 * mm,
            "Additional area m²": 20 * mm,
            "Current spaces": 18 * mm,
            "Recommended spaces": 23 * mm,
            "Additional spaces": 18 * mm,
            "Reason": 50 * mm,
        }
        story.append(
            table_from_df(
                location_recommendations_df,
                [rec_width_map.get(c, 18 * mm) for c in location_recommendations_df.columns],
                styles,
                right_align=[i for i, c in enumerate(location_recommendations_df.columns) if c not in {"Department", "Category", "Location", "Reason"}],
            )
        )

    # --- END Location recommendations ---

    # --- START Pending tasks ---

    story.section("pending_tasks")
    story += [
        PageBreak(),
        Paragraph("Pending tasks", styles["Section"]),
        Paragraph(
            "Pending tasks are task records that were generated or seen in the event log but did not reach assignment, completion or failure before the report horizon ended.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
    ]
    pending_tasks_df = results.get("pending_tasks", pd.DataFrame()).copy()
    if pending_tasks_df.empty:
        story.append(
            Paragraph(
                "No pending tasks were identified in the simulation event log.",
                styles["BodyText"],
            )
        )
    else:
        has_dt = pd.api.types.is_datetime64_any_dtype(pending_tasks_df["start"]) or any(
            hasattr(v, "strftime") for v in pending_tasks_df["start"].dropna().tolist()
        )
        for col in ("start", "finish"):
            if col in pending_tasks_df.columns:
                pending_tasks_df[col] = pending_tasks_df[col].map(
                    lambda v: fmt_ts(v, has_dt) if not pd.isna(v) else "-"
                )
        pending_tasks_df = pending_tasks_df.rename(
            columns={
                "task_id": "Task",
                "amr": "AMR",
                "origin": "From",
                "destination": "To",
                "payload": "Payload",
                "start": "First seen",
                "finish": "Last seen",
                "pending_reason": "Reason",
            }
        )
        display_cols = [
            c
            for c in [
                "Task",
                "AMR",
                "From",
                "To",
                "Payload",
                "First seen",
                "Last seen",
                "Reason",
            ]
            if c in pending_tasks_df.columns
        ]
        pending_tasks_df = pending_tasks_df[display_cols]
        story.append(
            table_from_df(
                pending_tasks_df,
                [36 * mm, 18 * mm, 34 * mm, 34 * mm, 26 * mm, 28 * mm, 28 * mm, 60 * mm][
                    : len(pending_tasks_df.columns)
                ],
                styles,
            )
        )

    # --- END Pending tasks ---

    # --- START Task SLA performance ---

    story.section("task_sla")
    story += [
        Paragraph("Task SLA performance", styles["Section"]),
        Paragraph(
            "Only tasks with a positive target_time are included. The SLA clock starts "
            "when the task is released and stops when delivery completes. Compliance is "
            "therefore measured against release time plus the configured target duration. "
            "Failed and still-pending tasks are retained as not delivered.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
    ]

    sla_overview_df = results.get("task_sla_overview", pd.DataFrame()).copy()
    sla_summary_df = results.get("task_sla_summary", pd.DataFrame()).copy()
    sla_detail_df = results.get("task_sla_detail", pd.DataFrame()).copy()

    if sla_overview_df.empty:
        story.append(
            Paragraph(
                "No tasks with a defined positive SLA target were identified in the simulation event log.",
                styles["BodyText"],
            )
        )
    else:
        sla_overview_df["compliance_pct"] = sla_overview_df["compliance_pct"].map(
            lambda value: f"{float(value):.2f}%"
        )
        sla_overview_df = sla_overview_df.rename(
            columns={
                "eligible_tasks": "SLA tasks",
                "met_sla": "Met SLA",
                "delivered_late": "Delivered late",
                "not_delivered": "Not delivered",
                "compliance_pct": "Compliance",
            }
        )
        story.append(
            table_from_df(
                sla_overview_df,
                [28 * mm, 28 * mm, 34 * mm, 34 * mm, 30 * mm],
                styles,
                right_align=[0, 1, 2, 3, 4],
            )
        )

        story += [Spacer(1, 10), Paragraph("SLA bands", styles["Heading3"])]
        for column in ("mean_lateness_s", "maximum_lateness_s"):
            sla_summary_df[column] = sla_summary_df[column].map(
                lambda value: (
                    fmt_wait_duration(value) if not pd.isna(value) else "-"
                )
            )
        sla_summary_df["percentage_pct"] = sla_summary_df["percentage_pct"].map(
            lambda value: f"{float(value):.2f}%"
        )
        sla_summary_df = sla_summary_df.rename(
            columns={
                "sla_band": "SLA band",
                "tasks": "Tasks",
                "percentage_pct": "% of SLA tasks",
                "mean_lateness_s": "Mean lateness",
                "maximum_lateness_s": "Maximum lateness",
            }
        )
        story.append(
            table_from_df(
                sla_summary_df,
                [65 * mm, 20 * mm, 30 * mm, 34 * mm, 38 * mm],
                styles,
                right_align=[1, 2],
            )
        )

        story += [
            Spacer(1, 12),
            Paragraph("Missed and undelivered SLA tasks", styles["Heading3"]),
        ]
        if sla_detail_df.empty:
            story.append(
                Paragraph(
                    "Every task with a defined SLA target met its deadline.",
                    styles["BodyText"],
                )
            )
        else:
            has_dt = pd.api.types.is_datetime64_any_dtype(
                sla_detail_df["release"]
            ) or any(
                hasattr(value, "strftime")
                for value in sla_detail_df["release"].dropna().tolist()
            )
            for column in ("release", "finish"):
                sla_detail_df[column] = sla_detail_df[column].map(
                    lambda value: fmt_ts(value, has_dt) if not pd.isna(value) else "-"
                )
            for column in (
                "target_s",
                "actual_release_to_delivery_s",
                "lateness_s",
            ):
                sla_detail_df[column] = sla_detail_df[column].map(
                    lambda value: (
                        fmt_wait_duration(value) if not pd.isna(value) else "-"
                    )
                )
            sla_detail_df = sla_detail_df.rename(
                columns={
                    "sla_band": "SLA band",
                    "task_id": "Task",
                    "amr": "AMR",
                    "origin": "From",
                    "destination": "To",
                    "release": "Released",
                    "finish": "Delivered / last seen",
                    "target_s": "Target",
                    "actual_release_to_delivery_s": "Actual",
                    "lateness_s": "Late by",
                }
            )
            sla_detail_df = sla_detail_df[
                [
                    "SLA band",
                    "Task",
                    "AMR",
                    "From",
                    "To",
                    "Released",
                    "Delivered / last seen",
                    "Target",
                    "Actual",
                    "Late by",
                ]
            ]
            story.append(
                table_from_df(
                    sla_detail_df,
                    [
                        48 * mm,
                        30 * mm,
                        18 * mm,
                        28 * mm,
                        28 * mm,
                        31 * mm,
                        36 * mm,
                        24 * mm,
                        24 * mm,
                        24 * mm,
                    ],
                    styles,
                )
            )

    # --- END Task SLA performance ---

    report_progress(9, 11, "Adding AMR sections")

    # --- START AMR Task Summary ---

    story.section("task_detail")
    schedule_story += [
        PageBreak(),
        Paragraph("Task detail grouped by AMR", styles["Heading3"]),
    ]

    tasks = results["tasks"].copy()
    for amr, sub in tasks.groupby("amr", sort=False):
        schedule_story.append(Spacer(1, 4))
        schedule_story.append(Paragraph(f"AMR {amr}", styles["Heading3"]))

        has_dt = pd.api.types.is_datetime64_any_dtype(sub["start"]) or any(
            hasattr(v, "strftime") for v in sub["start"].dropna().tolist()
        )
        task_detail_cols = [
            "task_id",
            "outcome",
            "origin",
            "destination",
            "start",
            "finish",
            "duration_s",
            "wait_s",
        ]
        display = sub[task_detail_cols].copy()
        display["start"] = display["start"].map(
            lambda v: fmt_ts(v, has_dt) if not pd.isna(v) else "-"
        )
        display["finish"] = display["finish"].map(
            lambda v: fmt_ts(v, has_dt) if not pd.isna(v) else "-"
        )
        display["duration_s"] = display["duration_s"].map(fmt_duration)
        display["wait_s"] = display["wait_s"].map(fmt_duration)
        display.columns = [
            "Task",
            "Outcome",
            "From",
            "To",
            "Start",
            "Finish",
            "Duration",
            "Wait",
        ]
        schedule_story.append(
            table_from_df(
                display,
                [
                    36 * mm,
                    18 * mm,
                    38 * mm,
                    38 * mm,
                    32 * mm,
                    32 * mm,
                    17 * mm,
                    15 * mm,
                ],
                styles,
            )
        )

    # --- END AMR Task Summary ---

    # --- START Heat map ---
    report_progress(
        9,
        10,
        "Prepared congestion heatmaps"
        if "heatmaps" in selected_section_ids
        else "Skipped congestion heatmaps",
    )

    story += schedule_story

    heatmap_df = (
        results.get("congestion_paths", pd.DataFrame()).copy()
        if "heatmaps" in selected_section_ids
        else pd.DataFrame()
    )

    # TEST FOR SINGLE FLOOR
    # heatmap_df = heatmap_df[heatmap_df["floor"] == 0]

    floor_dxf_map = results.get("floor_dxf_map", {}) or {}
    prepared_heatmaps: Dict[int, dict] = {}

    if not heatmap_df.empty:
        floors = sorted(int(f) for f in heatmap_df["floor"].dropna().unique())

        grouped_floor_dfs = {
            int(floor): heatmap_df[heatmap_df["floor"] == floor].copy()
            for floor in floors
        }

        workers = heatmap_workers or min(
            len(floors),
            max(1, (os.cpu_count() or 2) - 1),
        )

        report_progress(
            0,
            max(len(floors), 1),
            f"Preparing heatmaps using {workers} worker(s)",
        )

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    prepare_heatmap_floor,
                    floor,
                    floor_df,
                    floor_dxf_map,
                    include_drawings,
                ): floor
                for floor, floor_df in grouped_floor_dfs.items()
            }

            for idx, future in enumerate(as_completed(futures), start=1):
                floor = futures[future]

                try:
                    prepared_floor, prepared = future.result()
                    prepared_heatmaps[prepared_floor] = prepared
                except Exception as exc:
                    report_progress(
                        idx,
                        max(len(floors), 1),
                        f"Heatmap floor {floor} failed: {exc}",
                    )
                    continue

                report_progress(
                    idx,
                    max(len(floors), 1),
                    f"Prepared heatmap floor {floor} ({idx}/{len(floors)})",
                )

    heatmap_story: List = []
    story.section("heatmaps")
    if prepared_heatmaps:
        heatmap_story += [NextPageTemplate("a0_landscape"), PageBreak()]

        first_floor = True
        for floor in sorted(prepared_heatmaps):
            if not first_floor:
                heatmap_story.append(PageBreak())
            first_floor = False

            prepared = prepared_heatmaps[floor]
            heatmap_story.append(
                FloorOverlayFlowable(
                    floor_df=prepared["floor_df"],
                    floor_label=str(int(floor)),
                    dxf_drawing=prepared["dxf_drawing"],
                    extents=prepared["extents"],
                    width=landscape(A0)[0] - 30 * mm,
                    height=landscape(A0)[1] - 35 * mm,
                )
            )

        heatmap_story += [NextPageTemplate("standard"), PageBreak()]

    story += heatmap_story

    # --- END Heat map ---

    report_progress(10, 11, "Building PDF")
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle(name=f'TOC{level}', fontName='Helvetica-Bold' if level == 0 else 'Helvetica',
        fontSize=10 if level == 0 else 9, leading=13, leftIndent=level*12, firstLineIndent=0,
        spaceBefore=7 if level == 0 else 3, textColor=colors.HexColor('#17365D')) for level in range(3)]
    front_matter = [Spacer(1, 42*mm), Paragraph(escape(report_title), styles['ReportTitle']),
        Spacer(1, 8*mm), Paragraph('Simulation analysis and operational performance', styles['ReportSub']),
        Paragraph('Source: ' + escape(csv_path.name), styles['BodyText']),
        Paragraph('Generated: ' + datetime.now().strftime('%d %B %Y %H:%M'), styles['BodyText']),
        Spacer(1, 12*mm), Paragraph(f'{len(selected_section_order)} selected report sections', styles['BodyText']),
        PageBreak(), Paragraph('Contents', styles['ReportTitle']), toc,
        NextPageTemplate(first_template_id), PageBreak()]
    doc.multiBuild(front_matter + story.flowables(styles))
    report_progress(11, 11, "PDF complete")
