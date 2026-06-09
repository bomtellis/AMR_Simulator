from pathlib import Path
import json

import pandas as pd

from amr_report_analysis import (
    analyse,
    load_amr_parameters,
    load_floor_dxf_map,
    load_location_catalog,
    load_payload_dimensions,
    load_payload_weights,
)
from amr_report_pdf_report import build_report
from amr_report_cli import parse_args


def export_failed_tasks_csv(source_csv: Path, output_csv: Path) -> None:
    df = pd.read_csv(source_csv, low_memory=False)
    event_col = "event_type" if "event_type" in df.columns else ""
    if not event_col:
        failed = pd.DataFrame()
    else:
        failed = df[df[event_col].astype(str).str.fullmatch("task_failed", case=False, na=False)].copy()

    rows = []
    for _, row in failed.iterrows():
        context = {}
        raw_context = str(row.get("failure_context", "") or "").strip()
        if raw_context:
            try:
                parsed = json.loads(raw_context)
                if isinstance(parsed, dict):
                    context = parsed
            except Exception:
                context = {}
        if context:
            rows.append(context)
            continue
        rows.append(
            {
                "sim_time_sec": row.get("sim_time_sec", ""),
                "sim_datetime": row.get("sim_datetime", ""),
                "task_id": row.get("task_id", ""),
                "reason": row.get("pending_reason", row.get("details", "")),
                "pickup": row.get("from_location", ""),
                "dropoff": row.get("to_location", ""),
                "payload": row.get("payload", ""),
                "payload_instance_id": row.get("payload_instance_id", ""),
                "task_source": row.get("task_source", ""),
                "department_id": row.get("department_id", ""),
                "waste_stream": row.get("waste_stream", ""),
                "container_type": row.get("container_type", ""),
            }
        )

    out_df = pd.DataFrame(rows)
    if out_df.empty:
        out_df = pd.DataFrame(
            columns=[
                "sim_time_sec",
                "sim_datetime",
                "task_id",
                "reason",
                "pickup",
                "dropoff",
                "payload",
                "payload_instance_id",
                "task_source",
                "department_id",
                "waste_stream",
                "container_type",
                "pickup_exists",
                "pickup_floor",
                "pickup_x",
                "pickup_y",
                "pickup_inventory_spaces_total",
                "pickup_inventory_spaces_occupied",
                "pickup_inventory_spaces_reserved",
                "pickup_inventory_spaces_free",
                "pickup_stored_payload_count",
                "pickup_stored_matching_payload_count",
                "pickup_stored_payloads",
                "dropoff_exists",
                "dropoff_floor",
                "dropoff_x",
                "dropoff_y",
                "dropoff_inventory_spaces_total",
                "dropoff_inventory_spaces_occupied",
                "dropoff_inventory_spaces_reserved",
                "dropoff_inventory_spaces_free",
                "dropoff_compatible_spaces_total",
                "dropoff_compatible_spaces_occupied",
                "dropoff_compatible_spaces_reserved",
                "dropoff_compatible_spaces_free",
                "dropoff_stored_payload_count",
                "dropoff_stored_matching_payload_count",
                "dropoff_stored_payloads",
                "pickup_status_json",
                "dropoff_status_json",
            ]
        )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output_csv, index=False)


def print_progress(current: int, total: int, message: str = "") -> None:
    total = max(total, 1)
    current = max(0, min(current, total))
    width = 40
    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    percent = int(100 * current / total)
    print(f"\r[{bar}] {percent:3d}% {message:<40}", end="", flush=True)
    if current >= total:
        print()


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    out_path = (
        Path(args.output)
        if args.output
        else csv_path.with_name(csv_path.stem + "_report.pdf")
    )

    print_progress(0, 100, "Loading configuration")

    payload_weights = (
        load_payload_weights(Path(args.config_json)) if args.config_json else {}
    )
    amr_parameters = (
        load_amr_parameters(Path(args.config_json)) if args.config_json else None
    )
    floor_dxf_map = (
        load_floor_dxf_map(Path(args.config_json))
        if args.config_json and not args.omit_drawings
        else {}
    )
    location_catalog = (
        load_location_catalog(Path(args.config_json)) if args.config_json else None
    )
    payload_dimensions = (
        load_payload_dimensions(Path(args.config_json)) if args.config_json else None
    )

    print_progress(15, 100, "Analysing simulation data")

    results = analyse(
        csv_path,
        args.target_amr_util,
        args.target_lift_util,
        payload_weights,
        amr_parameters,
        floor_dxf_map,
        location_catalog,
        payload_dimensions,
    )

    if args.failed_tasks_csv:
        export_failed_tasks_csv(csv_path, Path(args.failed_tasks_csv))
        print_progress(30, 100, f"Failed-task CSV written to {args.failed_tasks_csv}")

    print_progress(35, 100, "Building PDF report")

    def report_progress(current: int, total: int, message: str = "") -> None:
        # Map report build progress into the 35-100 range
        base = 35
        span = 65
        mapped = base + int(span * current / max(total, 1))
        print_progress(mapped, 100, message)

    build_report(
        results,
        csv_path,
        out_path,
        progress_callback=report_progress,
        heatmap_workers=args.heatmap_workers,
        include_drawings=not args.omit_drawings,
    )

    print_progress(100, 100, f"Report written to {out_path}")


if __name__ == "__main__":
    main()
