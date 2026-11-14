"""Synthetic provenance/quality failures and read-only multi-file integration."""

import csv
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from core import region_data
from core.data_loader import load_data, resolve_original_source
from core.data_cleaning import clean_monthly, annual_mean_temperatures, annual_trend_ready
from core.dataset_audit import inspect_dataset
from core.region_data import COUNTRIES, load_country, read_country_mapping, RegionDataError

ROOT = Path(__file__).resolve().parents[1]
DATA_ID = "M2TMNXSLV_5_12_4_T2M"


@pytest.fixture
def countries(tmp_path):
    """Build confirmed synthetic mappings, not claims about NASA country shapes."""
    directory = tmp_path / "raw"
    directory.mkdir()
    mapping = tmp_path / "mapping.json"
    entries = []

    def add(country="Argentina", *, mutations=None, data_id=DATA_ID, start="2000-01-01", end="2025-12-01", units=None):
        path = directory / f"{country}.csv"
        shape = f"synthetic_shapes/{country}"
        url = ("https://giovanni.gsfc.nasa.gov/giovanni/#service=ArAvTs&"
               f"starttime=2000-01-01T00:00:00Z&endtime=2025-12-31T23:59:59Z&shape={shape}&data={data_id}")
        rows = [[f"{date:%Y-%m-%d} 00:00:00", str(290 + i / 1000)] for i, date in enumerate(pd.date_range(start, end, freq="MS"))]
        if mutations:
            mutations(rows)
        with path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerows([
                ["Title:", "Synthetic monthly 2-meter air temperature"],
                ["User Start Date:", "2000-01-01T00:00:00Z"],
                ["User End Date:", "2025-12-31T23:59:59Z"],
                ["URL to Reproduce Results:", url],
                [f"Fill Value (mean_{DATA_ID}):", "1000000000000000"],
            ])
            if units is not None:
                writer.writerow(["Units:", units])
            writer.writerows([[], ["time", f" mean_{DATA_ID} "], *rows])
        entries.append({"country": country, "filename": path.name,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "shape_identifier": shape, "status": "user_reported",
                        "evidence": "Synthetic fixture's explicit mapping, not actual geographic verification."})
        save()
        return path

    def save():
        mapping.write_text(json.dumps({"schema_version": 1, "countries": entries}))

    return directory, mapping, entries, add, save


def test_multiple_valid_countries_and_shared_pipeline(countries):
    raw, mapping, entries, add, _ = countries
    add("Argentina")
    add("Bolivia")
    for country in ("Argentina", "Bolivia"):
        with patch.object(region_data, "clean_monthly", wraps=clean_monthly) as clean, \
             patch.object(region_data, "annual_mean_temperatures", wraps=annual_mean_temperatures) as aggregate, \
             patch.object(region_data, "annual_trend_ready", wraps=annual_trend_ready) as complete:
            result = load_country(country, mapping_path=mapping, raw_directory=raw)
        clean.assert_called_once()
        aggregate.assert_called_once()
        complete.assert_called_once()
        assert len(result.monthly) == 312 and len(result.complete_annual) == 26
        assert result.monthly.country.eq(country).all()
        assert result.annual.country.eq(country).all()
        assert result.complete_annual.country.eq(country).all()
        assert "URL to Reproduce Results" in result.metadata
        assert result.provenance["status"] == "user_reported"
        expected = clean_monthly(load_data(result.source).observations)
        pd.testing.assert_frame_equal(result.monthly.drop(columns="country"), expected)


def test_unresolved_and_unknown_country(countries):
    raw, mapping, entries, add, save = countries
    add()
    entries[0]["status"] = "pending_confirmation"
    save()
    with pytest.raises(RegionDataError, match="unresolved"):
        load_country("Argentina", mapping_path=mapping, raw_directory=raw)
    with pytest.raises(RegionDataError, match="No country-to-file mapping"):
        load_country("Peru", mapping_path=mapping, raw_directory=raw)


def test_missing_source(countries):
    raw, mapping, _, add, _ = countries
    add().unlink()
    with pytest.raises(RegionDataError, match="Argentina.*csv"):
        load_country("Argentina", mapping_path=mapping, raw_directory=raw)


@pytest.mark.parametrize("field", ["country", "filename", "sha256", "shape_identifier"])
def test_duplicate_or_conflicting_mappings(countries, field):
    _, mapping, entries, add, save = countries
    add("Argentina")
    add("Bolivia")
    entries[1][field] = entries[0][field]
    save()
    with pytest.raises(RegionDataError, match="duplicate|Conflicting"):
        read_country_mapping(mapping)


@pytest.mark.parametrize("data_id", ["M2TMNXSLV_5_12_4_T10M", "M2TMNXSLV_5_12_3_T2M", "OTHER_5_12_4_T2M"])
def test_incorrect_collection_version_variable(countries, data_id):
    raw, mapping, _, add, _ = countries
    add(data_id=data_id)
    with pytest.raises(RegionDataError, match="collection/variable"):
        load_country("Argentina", mapping_path=mapping, raw_directory=raw)


@pytest.mark.parametrize("mutation,message", [
    (lambda rows: rows.pop(12), "coverage|missing months"),
    (lambda rows: rows.pop(0), "coverage|missing months"),
    (lambda rows: rows.append(rows[-1].copy()), "Duplicate timestamps"),
    (lambda rows: rows[2].__setitem__(1, "bad"), "Invalid numeric"),
    (lambda rows: rows[2].__setitem__(1, "inf"), "Nonfinite"),
    (lambda rows: rows[2].append("extra"), "Malformed record"),
    (lambda rows: rows[2].__setitem__(0, "bad"), "Invalid timestamp"),
])
def test_invalid_records_and_coverage(countries, mutation, message):
    raw, mapping, _, add, _ = countries
    add(mutations=mutation)
    with pytest.raises(RegionDataError, match=message):
        load_country("Argentina", mapping_path=mapping, raw_directory=raw)


@pytest.mark.parametrize("missing", ["", "1000000000000000"])
def test_missing_values_preserved_and_year_excluded(countries, missing):
    raw, mapping, _, add, _ = countries
    add(mutations=lambda rows: rows[0].__setitem__(1, missing))
    result = load_country("Argentina", mapping_path=mapping, raw_directory=raw)
    assert len(result.monthly) == 312
    assert result.monthly.temperature_c.isna().sum() == 1
    assert result.annual.valid_months.iloc[0] == 11
    assert not result.annual.is_complete.iloc[0]
    assert len(result.complete_annual) == 25


def test_all_missing_values_are_invalid(countries):
    raw, mapping, _, add, _ = countries
    add(mutations=lambda rows: [row.__setitem__(1, "") for row in rows])
    with pytest.raises(RegionDataError, match="no valid temperature"):
        load_country("Argentina", mapping_path=mapping, raw_directory=raw)


def test_inconsistent_units(countries):
    raw, mapping, _, add, _ = countries
    add(units="Celsius")
    with pytest.raises(RegionDataError, match="units"):
        load_country("Argentina", mapping_path=mapping, raw_directory=raw)


def test_shape_conflict_and_checksum_integrity(countries):
    raw, mapping, entries, add, save = countries
    path = add()
    entries[0]["shape_identifier"] = "different_shape"
    save()
    with pytest.raises(RegionDataError, match="shape conflicts"):
        load_country("Argentina", mapping_path=mapping, raw_directory=raw)
    path.write_text(path.read_text() + "\n")
    with pytest.raises(RegionDataError, match="checksum differs"):
        load_country("Argentina", mapping_path=mapping, raw_directory=raw)


def test_mapping_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text('{"schema_version":1,"countries":[],"countries":[]}')
    with pytest.raises(RegionDataError, match="Duplicate JSON key"):
        read_country_mapping(path)


def test_raw_audit_reports_independent_defects(countries):
    _, _, _, add, _ = countries
    def corrupt(rows):
        rows[0][1] = "1000000000000000"
        rows[1][1] = "nan"
        rows[2][1] = "broken"
        rows[3][1] = ""
        rows.append(rows[-1].copy())
        rows.append(["malformed"])
        rows.pop(20)
    report = inspect_dataset(add(mutations=corrupt))
    assert report["data_status"] == "INVALID"
    assert report["duplicate_timestamps"] == 1
    assert report["malformed_records"] == 1
    assert report["fill_values"] == 1
    assert report["nonfinite_temperatures"] == 1
    assert report["invalid_numeric_values"] == 1
    assert report["blank_temperatures"] == 1
    assert report["missing_months"] == ["2001-09"]


def test_real_inventory_and_existing_peru_provenance():
    mappings = read_country_mapping()
    assert set(mappings) == set(COUNTRIES)
    for entry in mappings.values():
        source = ROOT / "data/raw" / entry["filename"]
        report = inspect_dataset(source)
        assert report["sha256"] == entry["sha256"]
        assert report["data_status"] == "VALID"
        assert report["monthly_observations"] == 312
        assert not report["missing_months"]
        assert report["complete_years"] == 26
        assert report["shape_identifier"] == entry["shape_identifier"]
    peru = load_country("Peru")
    old = json.loads((ROOT / "metadata/dataset_provenance.json").read_text())
    assert peru.sha256 == old["original_csv_sha256"]
    assert peru.source == resolve_original_source()
    assert peru.provenance["csv_independently_verifies_country_identity"] is False


def test_legacy_resolver_refuses_absent_or_ambiguous_checksum(tmp_path):
    with pytest.raises(ValueError, match="found 0"):
        resolve_original_source(tmp_path)
    raw = resolve_original_source().read_bytes()
    (tmp_path / "one.csv").write_bytes(raw)
    assert resolve_original_source(tmp_path).name == "one.csv"
    (tmp_path / "two.csv").write_bytes(raw)
    with pytest.raises(ValueError, match="found 2"):
        resolve_original_source(tmp_path)


def test_validator_displays_unresolved_without_assigning_country(countries, monkeypatch, capsys):
    from scripts.validate_regions import main
    raw, mapping, entries, add, save = countries
    add()
    entries[0]["status"] = "pending_confirmation"
    save()
    monkeypatch.setattr("sys.argv", ["validate_regions.py", "--raw-directory", str(raw), "--mapping", str(mapping)])
    assert main() == 2
    output = capsys.readouterr().out
    assert "UNRESOLVED" in output
    assert "1/1 valid" in output


def test_validator_all_confirmed_synthetic_countries(countries, monkeypatch, capsys):
    from scripts.validate_regions import main
    raw, mapping, _, add, _ = countries
    for country in COUNTRIES:
        add(country)
    monkeypatch.setattr("sys.argv", ["validate_regions.py", "--raw-directory", str(raw), "--mapping", str(mapping)])
    assert main() == 0
    assert "12/12 valid" in capsys.readouterr().out


def test_explicit_analysis_does_not_mislabel_another_source_as_peru(countries, monkeypatch, capsys):
    from scripts.analyze_trends import main
    _, _, _, add, _ = countries
    path = add()
    monkeypatch.setattr("sys.argv", ["analyze_trends.py", str(path)])
    main()
    output = capsys.readouterr().out
    assert "Geographic selection: unresolved" in output
    assert "Geographic selection: Peru" not in output


def test_user_confirmed_provenance_is_supported(countries):
    raw, mapping, entries, add, save = countries
    add()
    entries[0]["status"] = "user_confirmed"
    entries[0]["evidence"] = "User explicitly confirms this synthetic country-to-file association."
    save()
    dataset = load_country("Argentina", mapping_path=mapping, raw_directory=raw)
    assert dataset.provenance["status"] == "user_confirmed"


def test_all_real_country_mappings_are_confirmed_and_one_to_one():
    mappings = read_country_mapping()
    assert set(mappings) == set(COUNTRIES)
    sources = {entry["filename"] for entry in mappings.values()}
    assert sources == {path.name for path in (ROOT / "data/raw").glob("*.csv")}
    assert len(sources) == len({entry["sha256"] for entry in mappings.values()}) == 12
    snapshot = json.loads((ROOT / "metadata/region_inventory.json").read_text())
    previous_shapes = {file["filename"]: file["shape_identifier"] for file in snapshot["files"]}
    for country, entry in mappings.items():
        assert entry["status"] == "user_confirmed"
        assert entry["csv_independently_verifies_country_identity"] is False
        assert entry["shape_identifier"] == previous_shapes[entry["filename"]]
        assert entry["filename"].endswith(f"_{entry['filename_suffix']}.csv")
        dataset = load_country(country)
        assert dataset.monthly.country.eq(country).all()
        assert len(dataset.monthly) == 312 and len(dataset.complete_annual) == 26
