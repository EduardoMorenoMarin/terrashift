"""Run with: python scripts/validate_data.py [path/to/export.csv]."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data_loader import load_data, resolve_original_source
from core.data_cleaning import clean_monthly, annual_mean_temperatures, annual_trend_ready


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path)
    args = parser.parse_args()
    try:
        loaded = load_data(args.path if args.path is not None else resolve_original_source())
        monthly = clean_monthly(loaded.observations)
        annual = annual_mean_temperatures(monthly)
        complete = annual_trend_ready(annual)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Validation failed: {exc}\n")
    valid = monthly.temperature_k.count()
    print(f"Source: {loaded.source.name}")
    print(f"Monthly observations: {len(monthly)}")
    print(f"Valid observations: {valid}")
    print(f"Missing temperature observations: {len(monthly) - valid}")
    print(f"Missing calendar months: {len(loaded.missing_months)}")
    if loaded.missing_months:
        print("Missing months: " + ", ".join(loaded.missing_months))
    print(f"Actual date range: {monthly.date.min():%Y-%m-%d} to {monthly.date.max():%Y-%m-%d}")
    if valid:
        print(f"Temperature range (Celsius): {monthly.temperature_c.min():.6f} to {monthly.temperature_c.max():.6f}")
    else:
        print("Temperature range (Celsius): unavailable")
    print(f"Complete years: {len(complete)}")
    print(f"Incomplete years: {len(annual) - len(complete)}")
    for label, row in (("First", annual.iloc[0]), ("Last", annual.iloc[-1])):
        status = "complete" if row.is_complete else "incomplete; excluded from trend-ready data"
        print(f"{label} annual mean: {int(row.year)}: {row.temperature_c:.6f} Celsius ({int(row.valid_months)} valid months; {status})")


if __name__ == "__main__":
    main()
