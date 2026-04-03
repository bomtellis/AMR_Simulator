from pathlib import Path

from amr_report_analysis import analyse, load_payload_weights
from amr_report_pdf_report import build_report
from amr_report_cli import parse_args


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

    payload_weights = (
        load_payload_weights(Path(args.config_json)) if args.config_json else {}
    )

    results = analyse(
        csv_path, args.target_amr_util, args.target_lift_util, payload_weights
    )
    build_report(results, csv_path, out_path)
    print(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
