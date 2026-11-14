# TerraShift AI — Phase 2

Requires Python 3.11 or newer. From the project root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/validate_data.py
```

The validation script also accepts an explicit CSV path. Automatic discovery
requires exactly one CSV in `data/raw/`. Raw data is ignored by Git and is never
written by these modules. Provenance is stored separately in
`metadata/dataset_provenance.json`.

```python
from core.data_loader import load_data
from core.data_cleaning import (
    clean_monthly, annual_mean_temperatures, annual_trend_ready,
)

loaded = load_data()
monthly = clean_monthly(loaded.observations)
annual = annual_mean_temperatures(monthly)
complete_annual = annual_trend_ready(annual)
print(loaded.metadata)
print(loaded.missing_months)
```

The loader reads the actual table header rather than assuming a fixed number
of metadata lines. It preserves metadata separately, validates field counts,
parses timestamps and temperatures strictly, rejects duplicates and unordered
records, and reports missing calendar months without inserting observations.
Requested date metadata, when present, also defines endpoint gap checks.
Blank temperatures and the declared fill value become missing values; invalid
numeric tokens and nonfinite literals raise errors. Temperatures below absolute
zero raise errors; no statistical outlier filtering is performed.

Cleaning copies the validated monthly data and adds Celsius. Annual summaries
use equally weighted arithmetic means of available monthly values, not
day-weighted means. Each year has a valid-month count and `is_complete` flag.
Years with fewer than 12 valid months retain their partial mean but are excluded
by `annual_trend_ready`. Entirely absent years between observed endpoints appear
with zero valid months. Missing requested endpoint months remain visible in
`loaded.missing_months`; annual summaries cover observed calendar years.

No files of cleaned observations are automatically written. No trends,
significance tests, charts, or interface are implemented. Peru is user-reported
provenance: the CSV shape identifier alone does not verify the country name.

Dependencies use bounded compatibility ranges; the exact resolved versions
should be captured after a successful installation for a frozen environment.
