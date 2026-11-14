import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.data_loader import load_data
from core.data_cleaning import (
    kelvin_to_celsius, clean_monthly, annual_mean_temperatures, annual_trend_ready,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPERATURE = "mean_M2TMNXSLV_5_12_4_T2M"


@pytest.fixture
def export(tmp_path):
    def write(records, start="2000-01-01T00:00:00Z", end="2000-02-29T23:59:59Z"):
        path = tmp_path / "sample.csv"
        path.write_text(
            f'Title:,"Example, monthly"\nUser Start Date:,{start}\n'
            f'User End Date:,{end}\nFill Value ({TEMPERATURE}):, 1000000000000000\n'
            f'\ntime, {TEMPERATURE} \n' + "\n".join(records) + "\n",
            encoding="utf-8",
        )
        return path
    return write


def test_real_csv():
    provenance = json.loads((ROOT / "metadata/dataset_provenance.json").read_text())
    path = ROOT / "data/raw" / provenance["original_csv_filename"]
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    loaded = load_data(path)
    assert before == provenance["original_csv_sha256"]
    assert len(loaded.observations) == 312
    assert loaded.missing_months == ()
    assert loaded.observations.date.min() == pd.Timestamp("2000-01-01")
    assert loaded.observations.date.max() == pd.Timestamp("2025-12-01")
    assert loaded.observations.temperature_k.isna().sum() == 0
    assert loaded.observations.temperature_k.min() == pytest.approx(290.695038)
    assert load_data().source == path.resolve()
    annual = annual_mean_temperatures(clean_monthly(loaded.observations))
    assert len(annual_trend_ready(annual)) == 26
    assert annual.valid_months.eq(12).all()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_metadata_and_whitespace(export):
    loaded = load_data(export(["2000-01-01 00:00:00,273.15", "2000-02-01 00:00:00,274.15"]))
    assert loaded.metadata["Title"] == "Example, monthly"
    assert list(loaded.observations) == ["date", "temperature_k"]
    assert pd.api.types.is_datetime64_any_dtype(loaded.observations.date)
    assert pd.api.types.is_numeric_dtype(loaded.observations.temperature_k)


def test_conversion():
    assert kelvin_to_celsius(273.15) == pytest.approx(0)
    assert kelvin_to_celsius(300) == pytest.approx(26.85)
    result = kelvin_to_celsius(pd.Series([273.15, np.nan]))
    assert result.iloc[0] == pytest.approx(0)
    assert pd.isna(result.iloc[1])


@pytest.mark.parametrize("records,message", [
    (["2000-01-01 00:00:00,290"] * 2, "Duplicate timestamps"),
    (["2000-02-01 00:00:00,290", "2000-01-01 00:00:00,291"], "chronological"),
    (["2000-01-01 00:00:00,broken"], "Invalid numeric"),
    (["2000-01-01 00:00:00,inf"], "Nonfinite"),
    (["2000-01-01 00:00:00,NaN"], "numeric|Nonfinite"),
    (["invalid,290"], "Invalid timestamp"),
    ([",290"], "Missing timestamp|Invalid timestamp"),
    (["2000-01-01 00:00:00,290,extra"], "Malformed record"),
    (["2000-01-01 00:00:00,290", ""], "Malformed record"),
    (["2000-01-01 00:00:00,-1"], "absolute zero"),
    (["2000-01-01 00:00:00,290", "2000-01-15 00:00:00,291"], "same month"),
])
def test_invalid_records(export, records, message):
    with pytest.raises(ValueError, match=message):
        load_data(export(records))


def test_missing_months_are_reported_and_not_fabricated(export):
    loaded = load_data(export(["2000-01-01 00:00:00,290", "2000-03-01 00:00:00,291"], end="2000-04-30"))
    assert loaded.missing_months == ("2000-02", "2000-04")
    assert len(clean_monthly(loaded.observations)) == 2


def test_fill_and_blank_values(export):
    loaded = load_data(export(["2000-01-01 00:00:00,1000000000000000", "2000-02-01 00:00:00, "]))
    monthly = clean_monthly(loaded.observations)
    assert len(monthly) == 2
    assert monthly.temperature_k.isna().all()
    assert monthly.temperature_c.isna().all()
    annual = annual_mean_temperatures(monthly)
    assert annual.valid_months.iloc[0] == 0
    assert annual_trend_ready(annual).empty


def test_annual_aggregation_and_incomplete_years():
    dates = pd.date_range("2000-01-01", periods=36, freq="MS")
    data = pd.DataFrame({"date": dates, "temperature_k": np.arange(36) + 273.15})
    data.loc[12, "temperature_k"] = np.nan
    data = data.drop(index=35)
    original = data.copy(deep=True)
    monthly = clean_monthly(data)
    pd.testing.assert_frame_equal(data, original)
    annual = annual_mean_temperatures(monthly)
    assert annual.valid_months.tolist() == [12, 11, 11]
    assert annual.is_complete.tolist() == [True, False, False]
    assert annual.temperature_c.iloc[0] == pytest.approx(5.5)
    assert annual.temperature_k.iloc[0] == pytest.approx(278.65)
    assert annual_trend_ready(annual).year.tolist() == [2000]
    assert len(monthly) == 35


def test_entire_missing_year_is_flagged():
    data = pd.DataFrame({"date": pd.to_datetime(["2000-01-01", "2002-01-01"]), "temperature_k": [290., 291.]})
    annual = annual_mean_temperatures(clean_monthly(data))
    assert annual.year.tolist() == [2000, 2001, 2002]
    assert annual.valid_months.tolist() == [1, 0, 1]
    assert not annual.is_complete.any()


@pytest.mark.parametrize("content,message", [
    ("x,y\n", "Missing observation header"),
    (f"time,{TEMPERATURE}\n2000-01-01 00:00:00,290\n", "Fill Value"),
    ("time,wrong\n", "unique columns"),
    (f"Fill Value ({TEMPERATURE}):,1e15\ntime,{TEMPERATURE}\n", "empty"),
])
def test_malformed_structure(tmp_path, content, message):
    path = tmp_path / "invalid.csv"
    path.write_text(content)
    with pytest.raises(ValueError, match=message):
        load_data(path)
