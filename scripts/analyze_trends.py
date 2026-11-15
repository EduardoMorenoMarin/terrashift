"""Print annual temperature trends and conditional uncertainty; no charts."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.data_loader import load_data, resolve_reference_source
from core.data_cleaning import clean_monthly, annual_mean_temperatures, annual_trend_ready
from core.trend_analysis import analyze_annual_trend
from core.region_data import geographic_identifiers, read_country_mapping, validate_dataset


def _format_optional(value, precision=4):
    return "unavailable" if value is None else f"{value:.{precision}g}"


def _print_inference(label, inference):
    interval = inference.confidence_interval_per_decade
    if interval is None:
        print(f"{label}: 95% CI and p-value unavailable (degenerate residual variance)")
        return
    significance = "significant" if inference.significant else "not significant"
    print(f"{label} 95% CI: [{interval[0]:.6f}, {interval[1]:.6f}] C/decade; "
          f"two-sided p={inference.p_value:.6g}; {significance} at alpha=0.05")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, help="NASA Giovanni CSV; otherwise load the active Peru release through the registry")
    parser.add_argument("--hac-lags", type=int, default=None, help="Override automatic Newey–West bandwidth")
    args = parser.parse_args()
    try:
        provenance = json.loads((ROOT / "metadata/dataset_provenance.json").read_text())
        loaded = load_data(args.path if args.path is not None else resolve_reference_source())
        registry = read_country_mapping()
        checksum = hashlib.sha256(loaded.source.read_bytes()).hexdigest()
        matches = [entry for entry in registry.values() if entry["sha256"] == checksum]
        coverage = matches[0].get("coverage") if matches else None
        validate_dataset(loaded, coverage=coverage)
        monthly = clean_monthly(loaded.observations)
        annual = annual_mean_temperatures(monthly)
        complete = annual_trend_ready(annual)
        result = analyze_annual_trend(complete, hac_lags=args.hac_lags)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Analysis failed: {exc}\n")
    print(f"Source: {provenance['source']}; {provenance['collection']} v{provenance['version']}; {provenance['variable']}")
    print(f"CSV: {loaded.source.name}")
    matches = [entry for entry in registry.values() if entry["sha256"] == checksum
               and entry["status"] != "pending_confirmation"]
    if matches:
        geography = matches[0]
        status = geography["status"].replace("_", "-")
        print(f"Geographic selection: {geography['country']} ({status}); shape {geography['shape_identifier']}")
    else:
        identity = geographic_identifiers(loaded.metadata)
        print(f"Geographic selection: unresolved for this explicit source; shape {identity['shape_identifier']}. Use the country mapping for provenance.")
    print("The CSV does not independently verify the shape's country identity.")
    print(f"Analysis period: {result.years[0]}–{result.years[-1]}")
    print(f"Annual observations: {len(result.years)}; incomplete years excluded: {len(annual) - len(complete)}")
    print(f"Monthly observation coverage: {loaded.observations.date.min():%Y-%m}–{loaded.observations.date.max():%Y-%m}; {len(loaded.observations)} observations")
    print(f"Missing months within reviewed observation coverage: {len(set(loaded.missing_months) - set((coverage or {}).get('unavailable_requested_months', [])))}")
    if loaded.missing_months:
        print("Requested but unavailable months (explicitly reviewed): " + ", ".join(loaded.missing_months))
    print("Annual means give equal weight to each of 12 valid monthly observations.")
    print(f"First annual mean ({result.years[0]}): {result.temperatures_c[0]:.6f} C")
    print(f"Last annual mean ({result.years[-1]}): {result.temperatures_c[-1]:.6f} C")
    print(f"First-to-last difference: {result.first_to_last_difference:+.6f} C")
    print(f"Linear trend: {result.slope_per_year:+.6f} C/year; {result.slope_per_decade:+.6f} C/decade")
    print(f"Regression intercept (calendar year 0): {result.intercept:.6f} C (not a physical extrapolation)")
    _print_inference("OLS", result.ols)
    print(f"HAC: Bartlett weights; lags={result.hac_lags}; n/(n-2) correction; Student-t reference, df={len(result.years)-2}")
    if args.hac_lags is None:
        print("HAC lag rule: floor(4*(n/100)^(2/9)), capped at n-1.")
    if result.hac_lags == 0:
        print("WARNING: HAC lag 0 adjusts for heteroskedasticity only, not serial dependence.")
    _print_inference("HAC-adjusted", result.hac)
    print(f"R-squared: {_format_optional(result.r_squared, 6)}")
    d = result.diagnostics
    print(f"Residual lag-1 Pearson correlation: {_format_optional(d.lag1_correlation)}")
    print(f"Durbin–Watson: {_format_optional(d.durbin_watson)} (near 2 suggests little lag-1 dependence; not a formal test here)")
    print(f"Exploratory Ljung–Box ({d.ljung_box_lags} lags): Q={_format_optional(d.ljung_box_statistic)}, p={_format_optional(d.ljung_box_p_value)}")
    print(f"Residual mean: {d.residual_mean:.6g} C; SD: {d.residual_standard_deviation:.6f} C; RMSE: {d.rmse:.6f} C; max absolute: {d.max_absolute_residual:.6f} C")
    print(f"Potential outlier years (|internally standardized residual| > 2): {list(d.potential_outlier_years)}")
    print(f"Potential influential years (Cook's D > 4/n): {list(d.influential_years)}")
    direction = "warming" if result.slope_per_year > 0 else "cooling" if result.slope_per_year < 0 else "no change"
    print(f"Interpretation: the fitted linear trend indicates {direction} at {result.slope_per_decade:+.4f} C per decade during this period.")
    for label, inference in (("OLS", result.ols), ("HAC", result.hac)):
        if inference.significant is None:
            print(f"{label} significance cannot be assessed for this degenerate fit.")
        elif inference.significant:
            print(f"{label} inference provides evidence of a nonzero linear slope at alpha=0.05, conditional on its assumptions.")
        else:
            print(f"{label} inference does not reject a zero linear slope at alpha=0.05; this does not establish no change.")
    if d.autocorrelation_detected is False:
        print("The residual autocorrelation screen did not flag dependence; independence is not established by this result.")
    print("OLS and HAC fit the same slope. Their uncertainty estimates can differ because HAC accounts for estimated residual variance patterns and dependence within the selected bandwidth; HAC intervals can be narrower or wider.")
    print("First-to-last difference compares two observed annual means and is distinct from the regression trend across all years.")
    print("Practical importance requires environmental context beyond statistical significance. This regional reanalysis aggregate cannot establish causation or describe within-country variation.")
    for warning in result.warnings:
        print(f"Caution: {warning}")


if __name__ == "__main__":
    main()
