import argparse


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyse AMR simulation CSV data and create a PDF report."
    )
    parser.add_argument("csv", nargs="?", help="Path to the simulation CSV")
    parser.add_argument("-o", "--output", help="Path to the PDF report", default=None)
    parser.add_argument('--existing-pdf', help='Insert selected sections into this PDF; original pages are preserved.')
    parser.add_argument('--insert-after-page', type=int, default=None,
                        help='Insert after this existing page (0 = before first page); default appends.')
    parser.add_argument('--insert-pdf', help='Insert an already prepared PDF, skipping analysis. Requires --existing-pdf and --output.')
    parser.add_argument('--report-title', help='Title on the cover, headers and PDF metadata.')
    parser.add_argument(
        "--target-amr-util",
        type=float,
        default=0.85,
        help="Target AMR utilisation for recommendation calculations",
    )
    parser.add_argument(
        "--target-lift-util",
        type=float,
        default=0.70,
        help="Target lift utilisation for recommendation calculations",
    )
    parser.add_argument(
        "--config-json",
        help="Path to matching simulator JSON for levels, departments, payloads and resource parameters",
        default=None,
    )
    parser.add_argument(
        "--heatmap-workers",
        type=int,
        default=None,
        help="Number of worker threads used to prepare heatmap floors",
    )
    parser.add_argument(
        "--omit-drawings",
        "--no-drawings",
        action="store_true",
        help=(
            "Do not render DXF drawings behind congestion heatmaps. "
            "Heatmaps will still be included using the simulation path extents."
        ),
    )
    parser.add_argument(
        "--failed-tasks-csv",
        help=(
            "Optional path for a separate failed-task CSV extracted from the "
            "simulation event log. Use this with verbose simulator output."
        ),
        default=None,
    )
    parser.add_argument(
        "--lift-cohorts-csv",
        help=(
            "Path for the 5-minute and hourly per-lift cohort CSV. "
            "Defaults to <output PDF stem>_lift_cohorts.csv."
        ),
        default=None,
    )
    parser.add_argument(
        "--report-sections",
        help=(
            "Comma-separated report section IDs to include, in output order. "
            "Use --list-report-sections to print available IDs."
        ),
        default=None,
    )
    parser.add_argument(
        "--lift-movements-csv", "--lift-travel-csv",
        help="Lift travel/destinations CSV path; defaults to <output PDF stem>_lift_movements.csv.",
        default=None,
    )
    parser.add_argument(
        "--lift-csv-only", action="store_true",
        help="Export only lift travel/destinations CSV, without generating a PDF or other tables.",
    )
    parser.add_argument('--department-review-dir', help='Export separate department review files per category into this folder.')
    parser.add_argument('--department-review-formats', choices=['both', 'pdf', 'xlsx'], default='both',
                        help='Department review formats: PDF and Excel by default.')
    parser.add_argument('--department-review-only', action='store_true',
                        help='Export department reviews only, without the main report or lift CSVs.')
    parser.add_argument(
        "--select-report-sections",
        action="store_true",
        help="Open a dialog to select and order PDF report sections before building.",
    )
    parser.add_argument(
        "--report-dialog",
        action="store_true",
        help="Open a dialog to select input files, output path and PDF report sections.",
    )
    parser.add_argument(
        "--list-report-sections",
        action="store_true",
        help="Print available report section IDs and exit.",
    )
    return parser.parse_args()
