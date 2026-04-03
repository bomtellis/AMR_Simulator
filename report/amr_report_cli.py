import argparse


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyse AMR simulation CSV data and create a PDF report."
    )
    parser.add_argument("csv", help="Path to the simulation CSV")
    parser.add_argument("-o", "--output", help="Path to the PDF report", default=None)
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
        help="Path to simulator JSON config for payload weights",
        default=None,
    )
    return parser.parse_args()
