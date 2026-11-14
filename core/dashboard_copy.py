"""Public table labels; source fields and CSV downloads remain unchanged."""

import pandas as pd

from core.dashboard_data import DashboardPeriod


def display_temperature_data(period: DashboardPeriod, frequency: str) -> pd.DataFrame:
    if frequency not in ("Annual", "Monthly"):
        raise ValueError("Choose annual or monthly temperatures.")
    table = (period.annual if frequency == "Annual" else period.monthly).copy()
    if "is_complete" in table:
        table["is_complete"] = table["is_complete"].map({True: "Yes", False: "No"})
    return table.rename(columns={
        "country": "Country", "date": "Date", "year": "Year",
        "temperature_k": "Temperature (K)", "temperature_c": "Temperature (°C)",
        "valid_months": "Months available", "is_complete": "Complete year",
    })
