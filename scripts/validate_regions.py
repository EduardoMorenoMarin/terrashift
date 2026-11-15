"""Inventory CSVs and report country provenance separately from data validity."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.data_loader import RAW_DIRECTORY
from core.dataset_audit import inspect_dataset
from core.region_data import COUNTRIES, MAPPING_PATH, load_country, read_country_mapping


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-directory", type=Path, default=RAW_DIRECTORY)
    parser.add_argument("--mapping", type=Path, default=MAPPING_PATH)
    parser.add_argument("--report", type=Path, help="Write a JSON inspection snapshot to a new file")
    args = parser.parse_args()
    try:
        mappings = read_country_mapping(args.mapping)
    except ValueError as exc:
        parser.exit(1, f"Invalid country mapping: {exc}\n")
    by_filename = {entry["filename"]: entry for entry in mappings.values()}
    reports = [inspect_dataset(path, coverage=by_filename.get(path.name, {}).get("coverage"))
               for path in sorted(args.raw_directory.glob("*.csv"))]
    by_name = {item["filename"]: item for item in reports}
    rows, errors, pending = [], 0, 0
    for country in COUNTRIES:
        entry = mappings.get(country)
        filename = entry["filename"] if entry else "—"
        report = by_name.get(filename)
        if not entry:
            status = "UNRESOLVED: no mapping"
            pending += 1
        elif report is None:
            status = "INVALID: source file missing"
            errors += 1
        elif report["data_status"] == "INVALID":
            status = "INVALID: " + "; ".join(report["errors"])
            errors += 1
        elif entry["sha256"] != report.get("sha256") or entry["shape_identifier"] != report.get("shape_identifier"):
            status = "INVALID: source checksum or shape differs from mapping"
            errors += 1
        elif entry["status"] == "pending_confirmation":
            status = "UNRESOLVED: filename candidate; data " + report["data_status"]
            pending += 1
        else:
            try:
                load_country(country, mapping_path=args.mapping, raw_directory=args.raw_directory)
                status = report["data_status"] + " / " + entry["status"]
            except ValueError as exc:
                status = "INVALID: " + str(exc)
                errors += 1
        rows.append([country, filename, str(report["monthly_observations"]) if report else "—",
                     f"{report['first_date'][:10]} to {report['last_date'][:10]}" if report and report["first_date"] else "—",
                     str(len(report["missing_months"])) if report else "—",
                     str(report["complete_years"]) if report else "—",
                     f"{report['minimum_c']:.3f} / {report['maximum_c']:.3f}" if report and report["minimum_c"] is not None else "—", status])
    headings = ["Country", "Source filename (candidate if unresolved)", "Months", "Date range", "Missing months", "Complete years", "Min / Max °C", "Status"]
    widths = [max(len(str(row[i])) for row in [headings, *rows]) for i in range(len(headings))]
    for row in [headings, *rows]:
        print(" | ".join(str(value).ljust(widths[i]) for i, value in enumerate(row)))
    assigned = {entry["filename"] for entry in mappings.values()}
    for report in reports:
        if report["filename"] not in assigned:
            print(f"UNMAPPED FILE: {report['filename']} — {report['data_status']}")
        print(f"AUDIT {report['filename']}: {report['data_status']}; sha256={report.get('sha256', 'unavailable')}; "
              f"duplicate timestamps={report['duplicate_timestamps']}; malformed={report['malformed_records']}; "
              f"invalid dates={report['invalid_timestamps']}; invalid numeric={report['invalid_numeric_values']}; "
              f"fill={report['fill_values']}; blank={report['blank_temperatures']}; nonfinite={report['nonfinite_temperatures']}")
        for warning in report.get("warnings", []):
            print(f"COVERAGE NOTE {report['filename']}: {warning}")
    coverage_signatures = {(report["first_date"], report["last_date"], report["monthly_observations"])
                           for report in reports if report["data_status"] != "INVALID"}
    if len(coverage_signatures) > 1:
        print("INVALID: inconsistent observation coverage across countries.")
        errors += 1
    unmapped = sum(report["filename"] not in assigned for report in reports)
    errors += unmapped
    valid = sum(r["data_status"] != "INVALID" for r in reports)
    print(f"\nCSV data validity: {valid}/{len(reports)} valid. Unresolved countries: {pending}. Country load errors: {errors}.")
    print("Provenance status distinguishes user_confirmed selections from independent verification; shape IDs and global filename bounds do not independently identify countries.")
    if args.report:
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump({"files": reports, "country_summary": [dict(zip(headings, row)) for row in rows]}, stream, indent=2, allow_nan=False)
            stream.write("\n")
    return 1 if errors or valid != len(reports) else 2 if pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
