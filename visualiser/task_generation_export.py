"""User-facing service reports for task generation settings."""

import csv
from itertools import groupby
from pathlib import Path
from xml.sax.saxutils import escape


HEADERS = ("Category", "Group", "Departments", "Setting", "Details")

MODES = {
    "scheduled": "At scheduled times", "threshold": "When the volume threshold is reached",
    "continuous": "Continuous demand", "sporadic": "Occasional demand",
    "hybrid": "Scheduled times and volume threshold", "scheduled_threshold": "Scheduled times and volume threshold",
    "scheduled_sporadic": "Scheduled times and occasional demand", "timeframe": "Within a time window",
}


def _list(value):
    return value if isinstance(value, list) else [value] if value else []


def _days(days):
    days = _list(days)
    if set(days) == {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}:
        return "Every day"
    if days == ["mon", "tue", "wed", "thu", "fri"]:
        return "Monday to Friday"
    names = dict(zip(("mon", "tue", "wed", "thu", "fri", "sat", "sun"),
                     ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")))
    return ", ".join(names.get(day, str(day)) for day in days) or "No active days"


def _hours(hours):
    grouped = {}
    for day, period in hours.items():
        if isinstance(period, dict) and period.get("enabled"):
            window = f"{period.get('start_time', '')} - {period.get('end_time', '')}"
            grouped.setdefault(window, []).append(day)
    return "; ".join(f"{_days(days)}: {window}" for window, days in grouped.items()) or "No working hours"


def _service_details(settings):
    """Only show operating information, with related controls combined."""
    result = [("Status", "Enabled" if settings.get("enabled", False) else "Disabled")]
    mode = settings.get("generation_mode", "scheduled")
    result.append(("Task timing", MODES.get(mode, str(mode).replace("_", " ").capitalize())))
    if "days_active" in settings:
        result.append(("Service days", _days(settings["days_active"]) + (" (every other week)" if settings.get("run_every_fortnight") else "")))
    if mode in {"scheduled", "hybrid", "scheduled_threshold", "scheduled_sporadic"}:
        times = settings.get("scheduled_times", settings.get("schedule_times", []))
        if times:
            result.append(("Scheduled times", ", ".join(map(str, _list(times)))))
    if mode == "timeframe":
        result.append(("Service window", f"{settings.get('timeframe_start', '')} - {settings.get('timeframe_end', '')}"))
        result.append(("Loads per window", str(settings.get("timeframe_payload_multiple", 1))))
    for key, label in (("priority", "Priority"), ("payload", "Load carried"), ("notes", "Notes")):
        if settings.get(key) not in (None, ""):
            result.append((label, str(settings[key])))
    for plural, singular, label in (("pickup_locations", "pickup_location", "Collection point"), ("dropoff_locations", "dropoff_location", "Delivery points")):
        value = settings.get(plural) or settings.get(singular)
        if value:
            result.append((label, ", ".join(map(str, _list(value)))))
    if mode != "scheduled":
        for key, label, unit in (("frequency_per_day", "Demand frequency", "events/day"), ("volume_per_event_m3", "Volume per event", "m³"), ("base_daily_volume_m3", "Daily volume", "m³/day"), ("threshold_volume_m3", "Trigger volume", "m³")):
            if settings.get(key):
                result.append((label, f"{settings[key]:g} {unit}" if isinstance(settings[key], (int, float)) else f"{settings[key]} {unit}"))
    if settings.get("return_enabled"):
        result.append(("Return collection", str(settings.get("return_payload") or "Enabled")))
        delay = settings.get("return_delay_minutes")
        if delay not in (None, ""):
            delay_text = f"{delay:g}" if isinstance(delay, (int, float)) else str(delay)
            result.append(("Return trip timing", f"Configured return delay: {delay_text} minutes"))
    if settings.get("tracked_item_exchange"):
        exchange = {"full_exchange": "Full exchange", "top_up_only": "Top up existing stock", "replace_empty": "Replace empty containers"}
        result.append(("Replenishment", exchange.get(settings.get("exchange_mode"), "Full exchange")))
    if settings.get("requires_staff"):
        result.append(("Staff team", f"{settings.get('staff_resource_name') or 'Category team'}; {settings.get('staff_initial_count', 1)} staff"))
        if settings.get("staff_use_custom_working_hours"):
            result.append(("Staff hours", _hours(settings.get("staff_working_hours", {}))))
        else:
            result.append(("Staff hours", "Use shared staff working hours"))
        if settings.get("staff_shift_pattern") == "four_on_four_off_12h":
            result.append(("Staff shifts", "4 days on, 4 days off; 12-hour shifts"))
        result.append(("Handling time", "Immediate handoff" if settings.get("staff_handoff_only") else f"{settings.get('staff_handling_minutes', 0):g} minutes"))
        if settings.get("staff_collection_delay_minutes"):
            result.append(("Staff collection delay", f"{settings['staff_collection_delay_minutes']:g} minutes"))
        if settings.get("staff_department_fallback_enabled"):
            result.append(("Outside staff hours", f"Handled by {settings.get('staff_department_fallback_resource_name') or 'department staff'}"))
    return result


def configuration_rows(config, departments):
    """Category report with each shared run shown once, using department names."""
    rows = [("Overview", "", "", "Automatic task generation", "Enabled" if config.get("enabled", True) else "Disabled")]
    for pattern in config.get("staff_config", {}).get("shift_patterns", {}).values():
        rows.append(("Overview", "Shared staff hours", "", pattern.get("display_name", "Staff hours"),
                     f"{_days(pattern.get('days_active', []))}; {pattern.get('start_time', '')} - {pattern.get('end_time', '')}"))
    by_id = {str(d.get("id") or d.get("name", "")): d for d in departments}
    names = {key: str(d.get("name") or "Unnamed department") for key, d in by_id.items()}
    for key, category in config.get("categories", {}).items():
        service = str(category.get("display_name") or str(key).replace("_", " ").title())
        covered = set()
        runs = []
        for group in category.get("department_groups", []):
            members = list(dict.fromkeys(map(str, group.get("departments", []))))
            if members and isinstance(group.get("payload"), dict):
                runs.append((members, group["payload"]))
                covered.update(members)
        for dept_id, payload in category.get("departments", {}).items():
            if str(dept_id) not in covered:
                runs.append(([str(dept_id)], payload))
        if not runs:
            runs = [([], {})]
        included = set()
        for number, (members, payload) in enumerate(runs, 1):
            included.update(members)
            settings = {**category, **payload}
            # Department assignments replace the saved sample destination/source.
            # Refer readers to the department table instead of implying that all
            # members use the first department's location.
            assigned = []
            for member in members:
                locations = by_id.get(member, {}).get("task_generation_locations", {}).get(key, {})
                assigned.append(isinstance(locations, dict) and bool(locations.get("pickup_dropoff_locations") or locations.get("locations")))
            if assigned and all(assigned):
                role = "pickup" if settings.get("department_location_role") == "pickup" else "dropoff"
                settings[f"{role}_locations"] = ["Department service locations (see operating details)"]
            label = f"Service group {number}" if len(runs) > 1 else "Service settings"
            department_names = ", ".join(names.get(member, "Unknown department") for member in members)
            rows.extend((service, label, department_names, field, value) for field, value in _service_details(settings))
        # Department information appears once per category, not once per run.
        for dept_id in sorted(included, key=lambda item: names.get(item, "")):
            dept = by_id.get(dept_id)
            if not dept:
                continue
            detail = ["Open" if dept.get("enabled", True) else "Disabled"]
            if "days_active" in dept:
                detail.append(_days(dept["days_active"]))
            if dept.get("operating_start_time") and dept.get("operating_end_time"):
                detail.append(f"{dept['operating_start_time']} - {dept['operating_end_time']}")
            locations = dept.get("task_generation_locations", {}).get(key, {})
            if isinstance(locations, dict):
                for field, title in (("pickup_dropoff_locations", "Service locations"), ("dropoff_zone_locations", "Drop-off zones")):
                    value = locations.get(field) or (locations.get("locations") if field == "pickup_dropoff_locations" else [])
                    if value:
                        detail.append(f"{title}: {', '.join(map(str, _list(value)))}")
            rows.append((service, "Department operating details", "", names[dept_id], "; ".join(detail)))
            if key == "waste":
                for stream in dept.get("waste_streams", []):
                    if isinstance(stream, str):
                        rows.append((service, "Waste streams", names[dept_id], stream, "Assigned"))
                    elif isinstance(stream, dict):
                        summary = _service_details(stream)
                        rows.append((service, "Waste streams", names[dept_id], stream.get("name", "Waste stream"), "; ".join(f"{field}: {value}" for field, value in summary if field != "Status" or "enabled" in stream)))
    return rows


def write_configuration_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADERS)
        writer.writerows(rows)


def write_configuration_pdf(path, rows):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, LongTable, TableStyle, Spacer, PageBreak

    # Use a Unicode font on Windows, with ReportLab's bundled Vera elsewhere.
    import reportlab
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    if not font_path.exists():
        font_path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
    if "TaskConfig" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("TaskConfig", str(font_path)))
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("ConfigCell", fontName="TaskConfig", fontSize=8, leading=11, alignment=TA_LEFT, splitLongWords=True)

    def paragraph(text):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), cell)

    story = [Paragraph("Service configuration report", styles["Title"]), paragraph("Service arrangements by category. Shared settings are shown once for the departments listed. Disabled services remain visible for reference."), Spacer(1, 14)]
    previous_category = None
    for context, entries in groupby(rows, key=lambda row: row[:3]):
        service, group, departments = context
        if service != previous_category:
            if previous_category not in (None, "Overview"):
                story.append(PageBreak())
            story.append(Paragraph(escape(service), styles["Heading1"]))
            previous_category = service
        context_row = [paragraph(" / ".join(part for part in (service, group) if part)),
                       paragraph("Departments: " + departments if departments else "")]
        if group == "Department operating details":
            data = [context_row, [paragraph("Department"), paragraph("Operating details")]]
        else:
            data = [context_row, [paragraph("Service detail"), paragraph("Arrangement")]]
        data.extend([paragraph(row[3]), paragraph(row[4])] for row in entries)
        table = LongTable(data, colWidths=[170, 353], repeatRows=2, splitInRow=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#e6edf4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#f7f9fb")]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([table, Spacer(1, 12)])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("TaskConfig", 8)
        canvas.drawRightString(A4[0] - 36, 20, f"Page {doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(str(path), pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36, title="Task generation configuration").build(story, onFirstPage=footer, onLaterPages=footer)
