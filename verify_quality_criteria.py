"""Validate a published release with the exact contract used by Airflow."""
import argparse
import json
from pathlib import Path

from src.quality import QualityError, validate_csv
from src.io_utils import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--silver-dir", type=Path, default=Path("include/output/silver"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.csv is not None:
        path = args.csv
    else:
        from src.release import current_release
        path = current_release(args.silver_dir) / "f1_silver_dataset.csv"
    try:
        report = validate_csv(path)
    except QualityError as error:
        if args.report:
            atomic_json(args.report, error.report)
        print(json.dumps(error.report, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    if args.report:
        atomic_json(args.report, report)
    print(json.dumps({key: report[key] for key in ("status", "total_rows", "total_cols", "duplicate_key_count", "empty_columns", "target_classes", "eligible_labeled_rows", "unit_of_analysis")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
