from __future__ import annotations

import copy
import io
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
import re

import ezdxf
from ezdxf.addons.drawing import layout
import pandas as pd
from ezdxf import bbox
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.svg import SVGBackend
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A0, A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
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
from svglib.svglib import svg2rlg

from amr_report_analysis import fmt_duration, fmt_ts


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
    return styles


class NumberedDocTemplate(BaseDocTemplate):
    def __init__(self, filename, **kwargs):
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

        self.addPageTemplates(
            [
                PageTemplate(
                    id="standard",
                    pagesize=A4,
                    frames=[portrait_frame],
                    onPage=self._draw_header_footer,
                ),
                PageTemplate(
                    id="landscape",
                    pagesize=landscape(A4),
                    frames=[landscape_frame],
                    onPage=self._draw_header_footer,
                ),
                PageTemplate(
                    id="a0_standard",
                    pagesize=A0,
                    frames=[a0_portrait_frame],
                    onPage=self._draw_header_footer,
                ),
                PageTemplate(
                    id="a0_landscape",
                    pagesize=landscape(A0),
                    frames=[a0_landscape_frame],
                    onPage=self._draw_header_footer,
                ),
            ]
        )

    def _draw_header_footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))

        page_width, page_height = canvas._pagesize
        canvas.drawString(
            doc.leftMargin,
            page_height - 12 * mm,
            "AMR Simulation Performance Report",
        )
        canvas.drawRightString(
            page_width - doc.rightMargin,
            10 * mm,
            f"Page {canvas.getPageNumber()}",
        )
        canvas.restoreState()


def natural_key(s):
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r"(\d+)", str(s))
    ]


def table_from_df(
    df: pd.DataFrame,
    col_widths: List[float],
    styles,
    right_align: Optional[List[int]] = None,
) -> Table:
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
    for row in df.fillna("-").astype(str).values.tolist():
        rows.append(
            [
                Paragraph(
                    cell.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"),
                    body_style,
                )
                for cell in row
            ]
        )

    data = [header] + rows
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
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


def get_dxf_extents(dxf_path: str) -> tuple[float, float, float, float]:
    import ezdxf
    from ezdxf import bbox

    doc = ezdxf.readfile(dxf_path)
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

    xmin, xmax, ymin, ymax = get_dxf_extents(dxf_path)

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    backend = SVGBackend()
    ctx = RenderContext(doc)

    ctx.set_current_layout(msp)

    # 🔧 Reduce lineweight scaling
    ctx.lineweight_scaling = 0.1  # try 0.1–0.3
    ctx.lineweight_policy = 1  # 0=off, 1=relative (best option)

    # Draw the whole layout so the backend builds its render box properly
    Frontend(ctx, backend).draw_layout(msp, finalize=True)

    data_w = max(xmax - xmin, 1.0)
    data_h = max(ymax - ymin, 1.0)

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
     viewBox="{xmin} {ymin} {data_w} {data_h}">
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
    return xmin, xmax, ymin, ymax


def load_svg_as_drawing(svg_path: str):
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
            f"Congestion heatmap - Floor {self.floor_label}",
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


def build_report(
    results: Dict[str, pd.DataFrame],
    csv_path: Path,
    pdf_path: Path,
    progress_callback=None,
) -> None:
    styles = make_styles()
    doc = NumberedDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=18 * mm,
        bottomMargin=15 * mm,
        title="AMR Simulation Performance Report",
        author="",
    )

    def report_progress(current: int, total: int, message: str) -> None:
        if progress_callback:
            progress_callback(current, total, message)

    report_progress(0, 10, "Preparing report")

    story = []

    # --- START front page ---
    story += [
        Paragraph("AMR Simulation Performance Report", styles["ReportTitle"]),
        Paragraph(f"Source CSV: {csv_path.name}", styles["ReportSub"]),
        Paragraph(
            "This report summarises task completion, wait time, lift usage, and resource recommendations derived from the simulation event log.",
            styles["BodyText"],
        ),
        Spacer(1, 6),
        Paragraph("Executive summary", styles["Section"]),
        table_from_df(results["summary"], [70 * mm, 100 * mm], styles),
        Spacer(1, 8),
        Paragraph("Method", styles["Section"]),
        table_from_df(results["methodology"], [38 * mm, 132 * mm], styles),
        PageBreak(),
    ]

    # --- END front page ---

    # --- START AMR List Summary ---

    amr_list_df = results["amr_list"].copy()
    amr_list_df = amr_list_df.drop(columns=["payload_capacity_size_units"])
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

    amr_df_total = {
        "amr": "Total",
        "tasks_total": amr_df["tasks_total"].sum(),
        "tasks_completed": amr_df["tasks_completed"].sum(),
        "tasks_failed": amr_df["tasks_failed"].sum(),
        "total_task_time_s": amr_df["total_task_time_s"].sum(),
        "total_wait_s": amr_df["total_wait_s"].sum(),
        "avg_task_time_s": amr_df["avg_task_time_s"].mean(),
        "total_distance_km": amr_df["total_distance_km"].sum(),
        "recharges": amr_df["recharges"].sum(),
        "recharge_energy_kwh": amr_df["recharge_energy_kwh"].sum(),
    }

    amr_df = pd.concat([amr_df, pd.DataFrame([amr_df_total])], ignore_index=True)
    amr_df["total_task_time_s"] = amr_df["total_task_time_s"].map(
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
            "total_task_time_s": "Task time",
            "total_wait_s": "Wait time",
            "avg_task_time_s": "Avg task",
            "total_distance_km": "Distance (km)",
            "recharges": "Recharges",
            "recharge_energy_kwh": "Energy kWh",
        }
    )

    amr_df_table = table_from_df(
        amr_df,
        [
            20 * mm,
            15 * mm,
            25 * mm,
            20 * mm,
            20 * mm,
            20 * mm,
            18 * mm,
            25 * mm,
        ],
        styles,
        right_align=[1, 2, 3, 7, 8, 9, 10, 11],
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
    amr_utilisation_df = amr_utilisation_df.drop(
        columns=["tasks_total", "total_task_time_s", "total_wait_s"],
        errors="ignore",
    )
    amr_utilisation_df = amr_utilisation_df.sort_values(
        by="amr",
        key=lambda col: col.map(natural_key),
    )
    amr_utilisation_df = amr_utilisation_df.rename(
        columns={
            "amr": "AMR ID",
            "utilisation_pct": "Util %",
            "idle_pct": "Idle %",
            "wait_share_pct": "Wait %",
        }
    )

    story += [
        Paragraph("AMR Utilisation, Idle and Wait %", styles["Section"]),
        table_from_df(
            amr_utilisation_df,
            [25 * mm, 25 * mm, 25 * mm, 25 * mm],
            styles,
        ),
        Spacer(1, 8),
    ]

    # --- END AMR Utilisation Summary ---

    # --- START AMR Recharge Summary ---
    story += [Spacer(1, 8), Paragraph("AMR recharge summary", styles["Section"])]
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

    # --- START Lift usage Summary ---

    story += [
        Paragraph("Lift usage summary", styles["Section"]),
        Paragraph("All times in the format of mm:ss", styles["BodyText"]),
        Spacer(1, 8),
    ]

    story += [Spacer(1, 8), Paragraph("Lift energy consumption", styles["Section"])]

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
            "lift_energy_kwh": lift_df["lift_energy_kwh"].sum(),
            "utilisation_pct": "",
            "idle_pct": "",
        }

        lift_df = pd.concat([lift_df, pd.DataFrame([lift_df_total])], ignore_index=True)
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
                "lift_energy_kwh": "kWh Consumed",
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

    # --- START Lift wait Summary ---

    story += [
        NextPageTemplate("landscape"),
        PageBreak(),
        Paragraph("Lift wait schedule", styles["Section"]),
    ]

    lift_wait_df = results["lift_wait_schedule"].copy()
    if lift_wait_df.empty:
        story.append(
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
        story.append(
            table_from_df(
                lift_wait_df,
                [35 * mm, 25 * mm, 50 * mm, 18 * mm, 28 * mm, 28 * mm, 18 * mm],
                styles,
            )
        )

    # --- END Lift wait Summary ---

    report_progress(3, 10, "Added summary and method")

    # --- START Payload Summary ---

    story += [
        NextPageTemplate("standard"),
        PageBreak(),
        Paragraph("Payload schedule", styles["Section"]),
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
                "tasks": "No. transported",
                "payload_weight_kg": "Payload kg",
            }
        )
        story.append(
            table_from_df(
                payload_df,
                [48 * mm, 30 * mm, 28 * mm],
                styles,
                right_align=[2, 3],
            )
        )

    # --- END Payload Summary ---

    report_progress(9, 11, "Adding AMR sections")

    # --- START AMR Task Summary ---

    story += [
        NextPageTemplate("landscape"),
        PageBreak(),
        Paragraph("Task detail grouped by AMR", styles["Section"]),
    ]

    tasks = results["tasks"].copy()
    for amr, sub in tasks.groupby("amr", sort=False):
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"AMR {amr}", styles["Heading3"]))

        has_dt = pd.api.types.is_datetime64_any_dtype(sub["start"]) or any(
            hasattr(v, "strftime") for v in sub["start"].dropna().tolist()
        )
        display = sub[
            [
                "task_id",
                "outcome",
                "origin",
                "destination",
                "start",
                "finish",
                "duration_s",
                "wait_s",
            ]
        ].copy()
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
        story.append(
            table_from_df(
                display,
                [
                    45 * mm,
                    20 * mm,
                    50 * mm,
                    50 * mm,
                    35 * mm,
                    35 * mm,
                    18 * mm,
                    16 * mm,
                ],
                styles,
            )
        )

    # --- END AMR Task Summary ---

    # --- START Heat map ---
    report_progress(9, 10, "Prepared congestion heatmaps")

    heatmap_df = results.get("congestion_paths", pd.DataFrame()).copy()

    # TEST FOR SINGLE FLOOR
    # heatmap_df = heatmap_df[heatmap_df["floor"] == 0]

    floor_dxf_map = results.get("floor_dxf_map", {}) or {}
    prepared_heatmaps: Dict[int, dict] = {}

    if not heatmap_df.empty:
        floors = sorted(heatmap_df["floor"].dropna().unique())
        for idx, floor in enumerate(floors, start=1):
            report_progress(
                idx,
                max(len(floors), 1),
                f"Preparing heatmap floor {int(floor)} ({idx}/{len(floors)})",
            )

            floor_df = (
                heatmap_df[heatmap_df["floor"] == floor]
                .sort_values("congestion_score", ascending=False)
                .reset_index(drop=True)
            )

            dxf_path = floor_dxf_map.get(int(floor))
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

            prepared_heatmaps[int(floor)] = {
                "floor_df": floor_df,
                "dxf_drawing": dxf_drawing,
                "extents": extents,
            }

    heatmap_story: List = []
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
    doc.build(story)
    report_progress(11, 11, "PDF complete")
