# South America display boundaries

Made with Natural Earth. `south_america.geojson` contains the 12 registered
sovereign countries, extracted from Natural Earth **v5.1.2**, **1:110 million
Admin 0 countries**. Coordinates are longitude/latitude (WGS84 / CRS84).

- Source: https://github.com/nvkelso/natural-earth-vector/blob/v5.1.2/geojson/ne_110m_admin_0_countries.geojson
- Download: https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_admin_0_countries.geojson
- License: **public domain**, https://www.naturalearthdata.com/about/terms-of-use/
- Upstream file SHA-256: `6866c877d39cba9c357620878839b336d569f8c662d3cfab4cb1dbe2d39c977f`
- Bundled subset SHA-256: `224c8c9dfbba2097d63bedebbb8001e4a6e5125e5a153308085df1125ca8223b`

Extraction: retain features whose `ISO_A3` matches the 12 `iso3` values in
`metadata/country_mapping.json`. Keep geometries unchanged, including polygon
rings and multipolygon parts. Retain only properties `ISO_A3` → `iso3` and
`ADMIN` → `name`; omit upstream bbox and other metadata. Serialize a GeoJSON
FeatureCollection as compact JSON followed by one newline. No geometry is
simplified further or invented. All 12 countries must match exactly once.
No external geographic package or runtime download is required.

These generalized cartographic boundaries are for display. They are not the
Giovanni `state_dept_countries_2017` extraction polygons and do not independently
verify those selections or reproduce their spatial averaging. Small islands
may be absent at this scale. Territories such as French Guiana and the Falkland
Islands are outside the 12-country registry and are not colored. Natural Earth
boundary conventions do not imply a position on territorial disputes.
