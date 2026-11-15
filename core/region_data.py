"""Explicit country provenance and a shared NASA monthly/annual preparation pipeline."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pandas as pd

from core.data_loader import RAW_DIRECTORY, LoadedDataset, load_data
from core.data_cleaning import clean_monthly, annual_mean_temperatures, annual_trend_ready

ROOT = Path(__file__).resolve().parents[1]
MAPPING_PATH = ROOT / "metadata/country_mapping.json"
COUNTRIES = ("Argentina", "Bolivia", "Brazil", "Chile", "Colombia", "Ecuador",
             "Guyana", "Paraguay", "Peru", "Suriname", "Uruguay", "Venezuela")
EXPECTED_DATA_ID = "M2TMNXSLV_5_12_4_T2M"


class RegionDataError(ValueError):
    """Invalid dataset or unsupported/conflicting country provenance."""


def geographic_identifiers(metadata: dict[str, str]) -> dict:
    """Read identifiers from the URL, without interpreting shapes as country names."""
    url = metadata.get("URL to Reproduce Results", "")
    parts = urlsplit(url)
    parameters = parse_qs(parts.fragment or parts.query)
    def single(key):
        values = parameters.get(key, [])
        return values[0] if len(values) == 1 else None
    data_id = single("data")
    match = re.fullmatch(r"([A-Z0-9]+)_(\d+)_(\d+)_(\d+)_(\w+)", data_id or "")
    return {
        "reproduction_url": url, "host": parts.hostname,
        "data_id": data_id, "shape_identifier": single("shape"),
        "collection": match[1] if match else None,
        "version": ".".join(match.group(2, 3, 4)) if match else None,
        "variable": match[5] if match else None,
        "service": single("service"),
        "starttime": single("starttime"), "endtime": single("endtime"),
    }


def expected_observation_months(coverage: dict) -> pd.PeriodIndex:
    """A reviewed release manifest defines availability, independently of requests."""
    try:
        start, end = coverage["start_month"], coverage["end_month"]
        if any(not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value) for value in (start, end)):
            raise ValueError("Expected YYYY-MM")
        months = pd.period_range(start, end, freq="M")
        count = coverage["observations"]
        if months.empty or isinstance(count, bool) or not isinstance(count, int) or count != len(months):
            raise ValueError("Observation count does not match coverage")
        requested_start, requested_end = (pd.Timestamp(coverage[key]) for key in ("requested_start", "requested_end"))
        if pd.isna(requested_start) or pd.isna(requested_end) or requested_start > requested_end:
            raise ValueError("Invalid requested interval")
        requested = pd.period_range(f"{requested_start:%Y-%m}", f"{requested_end:%Y-%m}", freq="M")
        if requested[0] != months[0] or requested[-1] < months[-1]:
            raise ValueError("Available interval conflicts with request")
        unavailable = [str(month) for month in requested.difference(months)]
        if coverage.get("unavailable_requested_months", []) != unavailable:
            raise ValueError("Requested but unavailable months must be listed exactly")
        if unavailable and not str(coverage.get("coverage_note", "")).strip():
            raise ValueError("Requested/available discrepancy requires an explicit review note")
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise RegionDataError(f"Invalid reviewed dataset coverage: {exc}") from exc
    return months


def validate_dataset(loaded: LoadedDataset, *, coverage: dict | None = None) -> dict:
    """Reject source conflicts, internal gaps and unreviewed endpoint shortages.

    With no reviewed manifest, the entire requested interval must be present.
    A manifest can explicitly distinguish the requested interval from audited
    availability; only exactly listed terminal unavailable months are accepted.
    Missing temperature values retain the established NaN/completeness behavior.
    """
    identity = geographic_identifiers(loaded.metadata)
    if identity["host"] != "giovanni.gsfc.nasa.gov" or identity["data_id"] != EXPECTED_DATA_ID:
        raise RegionDataError(f"Expected NASA Giovanni collection/variable {EXPECTED_DATA_ID}; found {identity['data_id']!r}.")
    if identity["service"] != "ArAvTs" or not identity["shape_identifier"]:
        raise RegionDataError("Expected an area-averaged time series with an explicit shape identifier.")
    requested = []
    for url_key, metadata_key, manifest_key in (("starttime", "User Start Date", "requested_start"),
                                               ("endtime", "User End Date", "requested_end")):
        try:
            url_date = pd.Timestamp(identity[url_key])
            metadata_date = pd.Timestamp(loaded.metadata[metadata_key])
            if pd.isna(url_date) or pd.isna(metadata_date) or url_date != metadata_date:
                raise ValueError("URL and metadata dates differ")
            if coverage is not None and url_date != pd.Timestamp(coverage[manifest_key]):
                raise ValueError("Dates differ from reviewed manifest")
            requested.append(url_date)
        except (KeyError, ValueError, TypeError) as exc:
            raise RegionDataError(f"Inconsistent requested metadata / reproduction URL date coverage: {metadata_key}") from exc
    if requested[0] > requested[1]:
        raise RegionDataError("Reversed requested date coverage.")
    if "monthly" not in loaded.metadata.get("Title", "").lower():
        raise RegionDataError("Metadata does not identify monthly resolution.")
    declared_identifiers = {
        "collection": {"M2TMNXSLV", "M2TMNXSLV v5.12.4"},
        "version": {"5.12.4", "v5.12.4"},
        "variable": {"T2M"},
    }
    for key, value in loaded.metadata.items():
        if key.lower() in declared_identifiers and value.strip() not in declared_identifiers[key.lower()]:
            raise RegionDataError(f"Conflicting source {key}: {value!r}.")
        if "unit" in key.lower() and value.strip().lower() not in ("k", "kelvin"):
            raise RegionDataError(f"Inconsistent temperature units: {key}={value!r}; expected Kelvin.")
    dates = loaded.observations.date
    if not dates.dt.is_month_start.all() or not dates.eq(dates.dt.normalize()).all():
        raise RegionDataError("Expected monthly timestamps at midnight on the first day of each month.")
    expected = (expected_observation_months(coverage) if coverage is not None else
                pd.period_range(f"{requested[0]:%Y-%m}", f"{requested[1]:%Y-%m}", freq="M"))
    actual = pd.PeriodIndex(dates.dt.to_period("M"))
    allowed_unavailable = tuple(coverage.get("unavailable_requested_months", [])) if coverage else ()
    if not actual.equals(expected) or loaded.missing_months != allowed_unavailable:
        raise RegionDataError(f"Inconsistent date coverage or missing months: expected every month from {expected[0]} through {expected[-1]} ({len(expected)} observations); only reviewed requested-end shortages are allowed.")
    if loaded.observations.temperature_k.notna().sum() == 0:
        raise RegionDataError("Dataset has no valid temperature observations.")
    return identity


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RegionDataError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_country_mapping(path: str | Path = MAPPING_PATH) -> dict[str, dict]:
    """Read a versioned mapping; reject conflicts even in pending entries.

    Each entry holds country, filename, SHA-256, shape, status and evidence.
    Pending entries are suggestions only and cannot be loaded as countries.
    """
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
        entries = document["countries"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RegionDataError(f"Cannot read country mapping {path}: {exc}") from exc
    if not isinstance(entries, list):
        raise RegionDataError("Country mappings must be a list.")
    if document.get("schema_version") != 1:
        raise RegionDataError("Unsupported country mapping schema_version; expected 1.")
    result, files, hashes, shapes = {}, set(), set(), set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise RegionDataError("Each country mapping must be an object.")
        country = entry.get("country")
        if country not in COUNTRIES or country in result:
            raise RegionDataError(f"Unknown or duplicate country mapping: {country!r}")
        filename = entry.get("filename")
        checksum = entry.get("sha256")
        shape = entry.get("shape_identifier")
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".csv"):
            raise RegionDataError(f"{country}: filename must be a CSV basename.")
        if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise RegionDataError(f"{country}: missing or invalid SHA-256.")
        if not isinstance(shape, str) or not shape:
            raise RegionDataError(f"{country}: missing shape identifier.")
        if filename in files or checksum in hashes or shape in shapes:
            raise RegionDataError(f"Conflicting mappings: repeated file, checksum or shape for {country}.")
        if entry.get("status") not in ("pending_confirmation", "user_reported", "user_confirmed", "independently_verified"):
            raise RegionDataError(f"{country}: invalid provenance status.")
        if not isinstance(entry.get("evidence"), str) or not entry["evidence"].strip():
            raise RegionDataError(f"{country}: provenance evidence is required.")
        if "coverage" in entry:
            expected_observation_months(entry["coverage"])
        result[country] = entry
        files.add(filename)
        hashes.add(checksum)
        shapes.add(shape)
    return result


@dataclass
class CountryDataset:
    country: str
    source: Path
    sha256: str
    metadata: dict[str, str]
    provenance: dict
    monthly: pd.DataFrame
    annual: pd.DataFrame
    complete_annual: pd.DataFrame
    missing_months: tuple[str, ...]
    unavailable_requested_months: tuple[str, ...] = ()


def load_country(country: str, *, mapping_path: str | Path = MAPPING_PATH,
                 raw_directory: str | Path = RAW_DIRECTORY) -> CountryDataset:
    """Load only an explicitly confirmed mapping, validating bytes and NASA identity."""
    mappings = read_country_mapping(mapping_path)
    if country not in mappings:
        raise RegionDataError(f"No country-to-file mapping for {country!r}.")
    entry = mappings[country]
    if entry["status"] == "pending_confirmation":
        raise RegionDataError(f"{country}: country-to-file mapping is unresolved; user confirmation is required.")
    source = Path(raw_directory) / entry["filename"]
    try:
        checksum = hashlib.sha256(source.read_bytes()).hexdigest()
        if checksum != entry["sha256"]:
            raise RegionDataError(f"{country}: checksum differs from the mapping; raw bytes must be reviewed.")
        loaded = load_data(source)
        identity = validate_dataset(loaded, coverage=entry.get("coverage"))
    except (OSError, ValueError) as exc:
        raise RegionDataError(f"{country} ({source.name}): {exc}") from exc
    if identity["shape_identifier"] != entry["shape_identifier"]:
        raise RegionDataError(f"{country}: reproduction URL shape conflicts with the country mapping.")
    monthly = clean_monthly(loaded.observations)
    annual = annual_mean_temperatures(monthly)
    complete = annual_trend_ready(annual)
    for table in (monthly, annual, complete):
        table.insert(0, "country", country)
    return CountryDataset(country, loaded.source, checksum, loaded.metadata.copy(), entry.copy(),
                          monthly, annual, complete,
                          tuple(month for month in loaded.missing_months if month not in entry.get("coverage", {}).get("unavailable_requested_months", [])),
                          tuple(entry.get("coverage", {}).get("unavailable_requested_months", [])))
