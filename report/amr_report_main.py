from pathlib import Path

from amr_report_analysis import (
    analyse,
    load_amr_parameters,
    load_floor_dxf_map,
    load_payload_weights,
)
from amr_report_pdf_report import build_report
from amr_report_cli import parse_args


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
        load_floor_dxf_map(Path(args.config_json)) if args.config_json else {}
    )

    print_progress(15, 100, "Analysing simulation data")

    results = analyse(
        csv_path,
        args.target_amr_util,
        args.target_lift_util,
        payload_weights,
        amr_parameters,
        floor_dxf_map,
    )

    print_progress(35, 100, "Building PDF report")

    def report_progress(current: int, total: int, message: str = "") -> None:
        # Map report build progress into the 35-100 range
        base = 35
        span = 65
        mapped = base + int(span * current / max(total, 1))
        print_progress(mapped, 100, message)

    build_report(results, csv_path, out_path, progress_callback=report_progress)

    print_progress(100, 100, f"Report written to {out_path}")


if __name__ == "__main__":
    main()
