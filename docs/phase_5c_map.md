# Phase 5C — interactive South America map

Explore now starts with a Plotly choropleth of all 12 registered countries.
The shared start/end years determine annual OLS trend estimates in °C/decade.
A blue–neutral–red scale has symmetric limits around zero; limits are recalculated
for the selected period and should not be compared visually across periods.
Country selection adds a dark boundary without replacing its trend color.
The annual map does not change when switching temperature charts to monthly.

Calculations live in `core/map_data.py`; presentation lives in
`core/map_charts.py` and `app.py`. All slopes are obtained from the existing
`prepare_period` helper and unchanged annual inference. No scientific values
are hardcoded. Per-country load failures leave unavailable rows; a geographic
validation failure disables the map while existing country details continue.
The main Explore loader retains its existing failure behavior.

Each registry entry has an explicit ISO-3 code. These are not derived from the
manually assigned filename suffixes (BR, CH, PAR, SURI, and URU differ from ISO-3).
The loader requires all 12 countries, unique valid code keys and exactly one
polygon feature per key, rejecting missing, extra and duplicate features.
Bundled Natural Earth geometries preserve upstream coordinates; source, version,
checksums, licensing and extraction are recorded in
[the geography attribution](../data/geography/README.md).
The boundary asset is explicitly allowed by `.gitignore`; NASA data policy is
unchanged. No files have been committed or deployed.

The map requires no runtime geographic download, tile provider, access token or
additional dependency. Plotly's `white-bg` MapLibre style supplies a blank
background for the bundled choropleth features. Data preparation for the 12 real
sources took approximately 0.33 seconds in the development environment, without
caching; this is a local observation, not a performance guarantee.

## Interaction choice and limitations

The supported fallback is implemented: hover for country, estimate and period;
use **Country to explore** in the sidebar to update both the map outline and
existing Explore details. Drag pans; map controls zoom. Scrolling over the map
does not capture page scrolling. Country clicks do not change the selector.

[Streamlit's native API](https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart)
exposes selection events rather than an arbitrary Plotly click callback.
[Plotly distinguishes click and selection events](https://plotly.com/javascript/plotlyjs-events/).
Plotly does have choropleth selection machinery; this implementation does not
claim that country selection is impossible. Reliable end-to-end polygon click
selection was not established across this project's supported Streamlit/Plotly
versions, so the authorized hover-plus-selector fallback is used without an
external event component. AppTest verifies selector synchronization and figure
specifications but does not execute browser JavaScript. Browser-level hover,
pan, zoom, narrow viewport appearance and map controls still warrant manual
review before deployment.

Colors represent trends of country-level average temperatures, not within-country
variation or significance. The generalized Natural Earth display polygons are
not the Giovanni extraction polygons. Small islands can be absent, and territories
outside the 12-country registry are not colored. The map must not be interpreted
as an independent verification of extraction geography or territorial claims.

Unavailable trends are gray and have explicit hover/table labels. The availability
table retains all 12 countries. It distinguishes selected dates from actual
complete years used in a fit. Fewer than three complete consecutive years,
missing observations, internal annual gaps or unavailable sources do not become
zero trends. Short periods warn about sensitivity. Constant zero slopes remain
valid estimates even when statistical uncertainty cannot be assessed. All-zero
maps use ±1 solely as a nondegenerate display range; no-data maps omit the numeric
colorbar. Details and uncertainty remain in the existing Explore view.

## Validation

Automated checks cover explicit country mappings, geographic join failures,
all 12 real-data slopes and selected periods, synthetic warming/cooling/constant
series, unavailable sources, all-missing temperatures, short and empty periods,
invalid dates, incomplete endpoints, internal gaps, source immutability, Plotly
serialization, centered color limits, unavailable fill, hover values, shared
selection/date controls, monthly-view independence and graceful map failure.
Existing dashboard, Compare and Methodology regression tests are included.
The full suite passes: **173 tests in 27.37 seconds**, including the previous
145 tests and 28 new map tests. `git diff --check` also passes.

All three existing validation scripts pass with exit code 0:
`validate_data.py`, `analyze_trends.py`, and `validate_regions.py`.
The regional audit reports 12/12 valid files, zero unresolved countries and zero
country load errors. The original Peru reference trend remains +0.370206 °C/decade.
