"""Read-only inventory of all exports, including files the strict loader rejects."""

import csv
import hashlib
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

from core.data_loader import load_data
from core.data_cleaning import clean_monthly, annual_mean_temperatures, annual_trend_ready
from core.region_data import EXPECTED_MONTHS, geographic_identifiers, validate_dataset


def inspect_dataset(path: str | Path) -> dict:
    """Audit raw fields without repairing, deleting or assigning a country.

    The raw-field pass counts independent defects even when strict loading
    fails. All standardized values and annual summaries use existing modules.
    """
    path = Path(path)
    report = {"filename": path.name, "errors": [], "monthly_observations": 0,
              "malformed_records": 0, "invalid_timestamps": 0, "invalid_numeric_values": 0,
              "blank_temperatures": 0, "fill_values": 0, "nonfinite_temperatures": 0,
              "duplicate_timestamps": 0, "metadata": {}, "first_date": None, "last_date": None,
              "missing_months": [], "complete_years": None, "minimum_c": None, "maximum_c": None}
    try:
        raw = path.read_bytes()
        report["sha256"] = hashlib.sha256(raw).hexdigest()
        rows = list(csv.reader(raw.decode("utf-8-sig").splitlines(), strict=True))
        header_index = next(i for i, row in enumerate(rows) if row and row[0].strip() == "time")
    except (OSError, UnicodeError, csv.Error, StopIteration) as exc:
        report["errors"].append(f"Cannot inspect CSV/header: {exc}")
        report["data_status"] = "INVALID"
        return report
    report["header_line"] = header_index + 1
    report["metadata_records"] = rows[:header_index]
    for row in rows[:header_index]:
        if len(row) == 2:
            report["metadata"][row[0].strip().rstrip(":")] = row[1].strip()
    report.update(geographic_identifiers(report["metadata"]))
    report["units"] = "K (NASA T2M documentation; not explicit in export)"
    report["units_evidence"] = "Same collection/variable as original Peru provenance; metadata/dataset_provenance.json units_reference"
    columns = [cell.strip() for cell in rows[header_index]]
    report["columns"] = columns
    raw_columns = rows[header_index]
    report["raw_columns"] = raw_columns
    records = rows[header_index + 1:]
    report["monthly_observations"] = len(records)
    temperature_columns = [i for i, name in enumerate(columns) if name.startswith("mean_")]
    dates = []
    fill = None
    if len(temperature_columns) == 1:
        index = temperature_columns[0]
        try:
            fill = float(report["metadata"][f"Fill Value ({columns[index]})"])
        except (KeyError, ValueError):
            pass
        for row in records:
            if len(row) != len(columns):
                report["malformed_records"] += 1
                continue
            try:
                dates.append(datetime.strptime(row[0].strip(), "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                report["invalid_timestamps"] += 1
            text = row[index].strip()
            if not text:
                report["blank_temperatures"] += 1
                continue
            try:
                value = float(text)
            except ValueError:
                report["invalid_numeric_values"] += 1
                continue
            if not math.isfinite(value):
                report["nonfinite_temperatures"] += 1
            elif value == fill:
                report["fill_values"] += 1
    else:
        report["errors"].append("Expected exactly one area-mean temperature column.")
    report["declared_fill_value"] = fill
    if dates:
        report["first_date"] = min(dates).isoformat(sep=" ")
        report["last_date"] = max(dates).isoformat(sep=" ")
        report["duplicate_timestamps"] = sum(count - 1 for count in Counter(dates).values())
        report["chronological"] = dates == sorted(dates)
    present = {f"{d.year:04d}-{d.month:02d}" for d in dates}
    report["missing_months"] = [str(m) for m in EXPECTED_MONTHS if str(m) not in present]
    report["unexpected_months"] = sorted(present - {str(m) for m in EXPECTED_MONTHS})
    try:
        loaded = load_data(path)
        monthly = clean_monthly(loaded.observations)
        annual = annual_mean_temperatures(monthly)
        report["valid_temperatures"] = int(monthly.temperature_k.count())
        report["missing_temperatures"] = int(monthly.temperature_k.isna().sum())
        report["complete_years"] = len(annual_trend_ready(annual))
        if monthly.temperature_c.notna().any():
            report["minimum_c"] = float(monthly.temperature_c.min())
            report["maximum_c"] = float(monthly.temperature_c.max())
        validate_dataset(loaded)
    except (ValueError, OSError) as exc:
        report["errors"].append(str(exc))
    if report["data_id"] != "M2TMNXSLV_5_12_4_T2M":
        report["units"] = "Unverified for this collection/variable"
    report["data_status"] = ("INVALID" if report["errors"] else
                             "VALID_WITH_MISSING_VALUES" if report.get("missing_temperatures") else "VALID")
    return report
