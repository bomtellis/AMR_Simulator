from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

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
        frame = Frame(
            self.leftMargin, self.bottomMargin, self.width, self.height, id="normal"
        )
        self.addPageTemplates(
            [
                PageTemplate(
                    id="standard", frames=[frame], onPage=self._draw_header_footer
                )
            ]
        )

    def _draw_header_footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(
            doc.leftMargin, A4[1] - 12 * mm, "AMR Simulation Performance Report"
        )
        canvas.drawRightString(
            A4[0] - doc.rightMargin, 10 * mm, f"Page {canvas.getPageNumber()}"
        )
        canvas.restoreState()


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


def build_report(
    results: Dict[str, pd.DataFrame], csv_path: Path, pdf_path: Path
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

    story = [
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

    amr_df = results["amr_summary"].copy()
    for col in ["total_task_time_s", "total_wait_s", "avg_task_time_s"]:
        amr_df[col] = amr_df[col].map(fmt_duration)
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
        }
    )
    story += [
        Paragraph("AMR fleet summary", styles["Section"]),
        Paragraph("All times in the format of mm:ss", styles["BodyText"]),
        Spacer(1, 8),
        table_from_df(
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
        ),
        Spacer(1, 8),
    ]

    # Utilisation

    amr_utilisation_df = results["utilisation_summary"].copy()
    amr_utilisation_df = amr_utilisation_df.drop(
        columns=["tasks_total", "total_task_time_s", "total_wait_s"], errors="ignore"
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
            [
                25 * mm,
                25 * mm,
                25 * mm,
                25 * mm,
            ],
            styles,
        ),
        Spacer(1, 8),
    ]

    story += [
        PageBreak(),
        Paragraph("Lift usage summary", styles["Section"]),
        Paragraph("All times in the format of mm:ss", styles["BodyText"]),
        Spacer(1, 8),
    ]

    lift_df = results["lift_summary"].copy()
    if lift_df.empty:
        story.append(
            Paragraph(
                "No lift_transfer segments were identified in the CSV.",
                styles["BodyText"],
            )
        )
    else:
        lift_df["total_lift_time_s"] = lift_df["total_lift_time_s"].map(fmt_duration)
        lift_df["avg_trip_s"] = lift_df["avg_trip_s"].map(fmt_duration)
        lift_df = lift_df.rename(
            columns={
                "lift_id": "Lift",
                "trips": "Trips",
                "total_lift_time_s": "Total lift time",
                "avg_trip_s": "Avg trip",
                "utilisation_pct": "Util %",
                "idle_pct": "Idle %",
            }
        )
        story.append(
            table_from_df(
                lift_df,
                [28 * mm, 16 * mm, 34 * mm, 26 * mm, 18 * mm, 18 * mm],
                styles,
                right_align=[1, 4, 5],
            )
        )

    # Lift waiting times

    story += [
        Spacer(1, 8),
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
                [28 * mm, 16 * mm, 18 * mm, 18 * mm, 28 * mm, 28 * mm, 18 * mm],
                styles,
            )
        )

    story += [
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
                "total_payload_weight_kg": "Payload kg",
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

    story += [PageBreak(), Paragraph("Task detail grouped by AMR", styles["Section"])]
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
                    20 * mm,
                    20 * mm,
                    22 * mm,
                    22 * mm,
                    28 * mm,
                    28 * mm,
                    18 * mm,
                    16 * mm,
                ],
                styles,
            )
        )
        story.append(Spacer(1, 6))
        story.append(PageBreak())

    doc.build(story)
