"""Read Giovanni exports without changing or silently dropping records."""

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

RAW_DIRECTORY = Path(__file__).resolve().parents[1] / "data" / "raw"


def resolve_original_source(directory: str | Path = RAW_DIRECTORY) -> Path:
    """Locate the original Peru bytes, allowing a rename without changing provenance.

    This is an explicit legacy-source resolver, not multi-country discovery.
    The saved checksum must match exactly one CSV, even if the old name exists.
    """
    provenance_path = Path(__file__).resolve().parents[1] / "metadata/dataset_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    checksum = provenance["original_csv_sha256"]
    matches = [p for p in Path(directory).glob("*.csv") if hashlib.sha256(p.read_bytes()).hexdigest() == checksum]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one CSV matching original Peru checksum; found {len(matches)} in {directory}.")
    return matches[0].resolve()


def resolve_reference_source() -> Path:
    """Resolve the active Peru release through its reviewed registry, not history."""
    from core.region_data import load_country
    return load_country("Peru").source


@dataclass
class LoadedDataset:
    observations: pd.DataFrame
    metadata: dict[str, str]
    source: Path
    missing_months: tuple[str, ...]


def load_data(path: str | Path | None = None) -> LoadedDataset:
    """Load monthly T2M and report calendar gaps without filling them.

    Duplicate timestamps, multiple records per month, reversed ordering,
    malformed rows, and invalid values raise ValueError. Missing months remain
    absent and are listed in missing_months (including requested endpoints).
    Blank temperatures and the declared fill value become NaN.
    """
    if path is None:
        candidates = sorted(RAW_DIRECTORY.glob("*.csv"))
        if len(candidates) != 1:
            raise ValueError(f"Expected one CSV in {RAW_DIRECTORY}; found {len(candidates)}. Supply a path.")
        path = candidates[0]
    source = Path(path).resolve()
    try:
        with source.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream, strict=True))
    except (csv.Error, UnicodeError) as exc:
        raise ValueError(f"Malformed CSV {source}: {exc}") from exc
    header_index = next((i for i, row in enumerate(rows) if row and row[0].strip() == "time"), None)
    if header_index is None:
        raise ValueError("Missing observation header containing time.")
    metadata = {}
    for row in rows[:header_index]:
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) != 2:
            raise ValueError(f"Malformed metadata record: {row!r}")
        key = row[0].strip().rstrip(":")
        if key in metadata:
            raise ValueError(f"Duplicate metadata key: {key}")
        metadata[key] = row[1].strip()
    columns = [cell.strip() for cell in rows[header_index]]
    temperatures = [name for name in columns if name == "mean_M2TMNXSLV_5_12_4_T2M"]
    if len(set(columns)) != len(columns) or len(temperatures) != 1:
        raise ValueError("Expected unique columns including mean_M2TMNXSLV_5_12_4_T2M.")
    temperature = temperatures[0]
    fill_key = f"Fill Value ({temperature})"
    try:
        fill = float(metadata[fill_key])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Missing or invalid metadata: {fill_key}") from exc
    if not np.isfinite(fill):
        raise ValueError("Fill value must be finite.")
    records = rows[header_index + 1:]
    if not records:
        raise ValueError("Observation table is empty.")
    for number, row in enumerate(records, header_index + 2):
        if len(row) != len(columns):
            raise ValueError(f"Malformed record {number}: expected {len(columns)} fields, got {len(row)}.")
    table = pd.DataFrame(records, columns=columns)
    try:
        dates = pd.to_datetime(table["time"].str.strip(), format="%Y-%m-%d %H:%M:%S", errors="raise")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid timestamp: {exc}") from exc
    if dates.isna().any():
        raise ValueError("Missing timestamp.")
    if dates.duplicated().any():
        raise ValueError("Duplicate timestamps in observation table.")
    if not dates.is_monotonic_increasing:
        raise ValueError("Timestamps are not in chronological order.")
    months = dates.dt.to_period("M")
    if months.duplicated().any():
        raise ValueError("Multiple observations in the same month.")
    text = table[temperature].str.strip()
    try:
        values = pd.to_numeric(text.mask(text.eq("")), errors="raise").astype(float)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid numeric temperature: {exc}") from exc
    if ((text.ne("")) & ~np.isfinite(values)).any():
        raise ValueError("Nonfinite temperature value in observation table.")
    values = values.mask(values.eq(fill))
    if values.lt(0).any():
        raise ValueError("Temperature below absolute zero Kelvin.")
    first, last = months.min(), months.max()
    for key, endpoint in (("User Start Date", "start"), ("User End Date", "end")):
        if key in metadata:
            try:
                boundary = pd.Timestamp(metadata[key])
                if pd.isna(boundary):
                    raise ValueError("Missing date")
                month = pd.Period(year=boundary.year, month=boundary.month, freq="M")
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid metadata date: {key}") from exc
            if endpoint == "start":
                first = month
            else:
                last = month
    if first > last or months.min() < first or months.max() > last:
        raise ValueError("Observations conflict with requested metadata date range.")
    missing = tuple(str(m) for m in pd.period_range(first, last, freq="M").difference(pd.PeriodIndex(months)))
    observations = pd.DataFrame({"date": dates, "temperature_k": values})
    return LoadedDataset(observations, metadata, source, missing)
