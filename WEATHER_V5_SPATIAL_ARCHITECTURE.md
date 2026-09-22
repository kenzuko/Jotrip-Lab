# PHU QUOC WEATHER & MARINE LAB V5.0
## Spatial Field Engine - Architecture Lock

Updated: 2026-09-18

## 1. Product rule

Weather Lab V5 is a spatial weather instrument, not a point-card dashboard.

The public map must answer:
- What is happening now?
- Where is it happening?
- How is it moving?
- What is most likely next?
- What could go wrong?
- How uncertain is the forecast?

The seven named Phu Quoc points remain operational anchors. They are not the map grid.

## 2. Data classes must remain separate

### ACTUAL / OBSERVED
Machine-readable measurements with timestamps only.
Examples:
- VVPQ METAR/SPECI
- VRain gauges
- future verified in-situ marine observations

Never interpolate a single observation into a fake island-wide actual field.

### OBSERVED REMOTE SENSING
- JMA Himawari-9 via NOAA Open Data
- radar source when available

Himawari cloud-top data is observed satellite data.
It is not rainfall observation and it is not lightning observation.

### ESTIMATED NOW
Observation-anchored local estimates from Weather Lab.
Must retain the ESTIMATED_NOW label.

### FORECAST FIELD
Spatial model grids.
Primary V5 sources:
- ECMWF Open Data direct field
- GEFS ensemble spatial field
- later ICON spatial field
- marine field sources

### JOTRIP INTELLIGENCE
Derived products:
- most-likely view
- ensemble q50/q90/q95
- exceedance probability
- spread / variability
- confidence
- hazard / risk
- local exposure logic

## 3. Spatial engine

### ECMWF
Purpose: deterministic / most-likely spatial base.

V5 preserves a renderer grid around Phu Quoc from the direct ECMWF fields already downloaded by the existing collector.

Fields:
- temperature
- U10 / V10
- wind speed / direction
- gust
- precipitation increment
- significant wave height
- wave direction
- wave period

D0-D3 uses the freshest operational cycle.
D4-D10 uses the latest 00/12 UTC cycle exposing step 240.
Accumulated precipitation must never be differenced across the short/medium cycle boundary.

### GEFS
Purpose: uncertainty and probability.

Source:
NOAA NOMADS GEFS 0.5 degree, up to 31 members.

Native ensemble field is preserved at 0.5 degree.
Renderer interpolation does not increase model resolution.

Per spatial cell:
- temperature q50/q90/q95/spread
- wind q50/q90/q95/spread
- U10 q50 / V10 q50
- wind direction from q50 vector
- P(wind >= 30 km/h)
- rain q50/q90/q95/spread
- P(rain >= 5 mm)

Horizon:
- +6h to +240h
- 6-hour native public ensemble cadence

### Himawari
Purpose: observed cloud / convection spatial context.

Source:
JMA Himawari-9 AHI L2 Full Disk Clouds via NOAA Open Data.

V5 preserves a regular lat/lon render sampling grid around Phu Quoc instead of only reducing the satellite field to seven anchor statistics.

Spatial values:
- cold cloud-top temperature
- median cloud-top temperature
- high cloud-top height
- median cloud-top height
- scan-to-scan cooling
- transparent convective proxy score

The render grid is not a statement of satellite native resolution.
Source resolution remains approximately 2 km at nadir and coarser away from nadir.

## 4. Seven operational anchors

Keep:
- Dương Đông
- Cửa Cạn
- Gành Dầu
- Bãi Thơm
- Hàm Ninh
- Bãi Sao
- Biển An Thới

Use them for:
- ground-truth anchoring
- local exposure logic
- operational marine interpretation
- tide / AQI / current / Hmax context
- field feedback
- calibration
- point-specific risk

Do not use them as substitutes for the spatial model field.

## 5. Renderer rules

Default:
Wind spatial field with motion visible immediately.

Base field:
ECMWF when available.
GEFS q50 is the fallback, not Open-Meteo.

Uncertainty overlay:
GEFS probability / spread.

Observed cloud layer:
Himawari spatial frames. Persistent archive keeps a compact rolling ring of up to 12 recent observed spatial frames for animation.

Actual overlay:
station markers only.

Risk overlay:
JoTrip operational anchors / regional D4-D10 risk.

Movement:
- wind particles use U/V vectors
- rain field may retain wind advection particles
- wave particles use wave direction
- radar animates observed frames
- satellite animates observed scan frames

## 6. Timeline

The map timeline must retain the full forecast horizon.

D0-D3:
higher temporal detail from the deterministic field.

D4-D10:
trend view. Visual confidence must reduce with lead time.

JoTrip regional ensemble forecast:
- D0-D3: 6-hour public cadence
- D4-D10: 12-hour public cadence

Never reuse a +72h risk value for D4-D10.
Beyond 72h, use the regional D10 ensemble product.

## 7. Public data retained from V2

V5 must not silently remove:
- ensemble completion
- q50/q90/q95
- probability
- spread
- variability
- confidence
- risk driver
- D0-D10 forecast
- model cycles
- source health
- Actual rain state and amount
- Hs / Hmax / period
- current
- tide
- AQI
- calibration state

These do not all need to occupy the main map.
They may appear in probe / detail / Lab mode.

## 8. Fallback order

Wind / rain:
1. ECMWF spatial direct
2. GEFS spatial q50
3. no fake field

Uncertainty:
1. GEFS spatial ensemble
2. unavailable

Cloud / convection:
1. Himawari observed spatial
2. point-level Himawari proxy
3. unavailable

Actual:
1. valid fresh observation
2. do not substitute model

Marine:
1. Copernicus Marine spatial near-now current/wave grid
2. ECMWF wave field for forecast timeline
3. point model context clearly labeled

## 9. Scientific integrity

- Smooth rendering is not higher model resolution.
- No point observation becomes a fake spatial actual field.
- No model value is labeled observed.
- No satellite convection proxy is labeled lightning.
- No satellite cloud field is labeled measured rainfall.
- Stale inputs must display stale status.
- D4-D10 is trend, not operational go/no-go.
- Confidence is not probability of correctness unless calibrated as such.

## 10. Storage and delivery

Current test path:
GitHub Actions compute -> data-weather / feature snapshot -> GitHub Pages renderer.

Production target:
GitHub Actions compute -> compact spatial products -> CDN/object storage -> weather.openphuquoc.com renderer.

Browser must never download raw GRIB or 31 ensemble members.
Heavy calculations are server-side / CI-side.
Frontend receives compact spatial summaries only.

## 11. V5 release gates

A V5 build is spatial-ready only when:
- GEFS spatial product reports READY
- GEFS horizon is 240h
- GEFS member matrix meets completeness gate
- Himawari spatial product reports READY
- ECMWF spatial product reports READY or GEFS fallback is explicitly active
- renderer identifies model/source
- interpolation is marked render-only in metadata
- Actual remains point-only
- D4-D10 uses the regional 240h ensemble product


## 12. V5.3 renderer rules

- Header embeds the original JoTrip wordmark with transparent background.
- CARTO Dark Matter-style raster basemap is used for higher weather-field contrast.
- Physical color scales remain fixed. Do not auto-stretch weak weather into severe colors.
- Rain / cloud alpha is reduced near zero values so no-event areas expose the basemap.
- Waves / surface current use a spatial-support mask. No field or particle motion should be extrapolated far beyond valid marine cells.
- Copernicus Marine is the near-now source for Waves and Current.
- ECMWF remains the forecast Waves source beyond near-now.
- Himawari rolling observed frames may be visually tweened between scans, but intermediate frames are display interpolation only and must not be labelled as new observations.
- ICON step-000 U/V spatial wind is a model cross-check only.
- Model disagreement overlay is available only at Wind near-now and only when both ECMWF and ICON spatial fields are valid.
- MapLibre/WebGL is the next renderer generation after V5.3 stability, not an in-place live migration.


## 13. V5.4 wide spatial envelope

The live map must never show a weather layer ending as an obvious rectangle
inside the normal Phu Quoc viewport.

Shared processing/display envelope:
- south: 9.00°N
- north: 11.00°N
- west: 102.75°E
- east: 105.50°E

Rules:
- The camera remains Phu Quoc-first. A wider data domain does not mean the map
  should zoom out by default.
- Himawari uses a 0.075° render sampling grid across the wide envelope. This is
  display sampling only and does not change the native satellite resolution.
- ECMWF D0-D3 uses the full wide envelope at 0.25° for the interactive map.
- ECMWF D4-D10 keeps the compact core grid because it is a trend product.
- Copernicus Marine near-now wave/current uses the same wide envelope.
- Layer edges should normally remain outside the visible camera. When a source
  genuinely has no support, the renderer must become transparent rather than
  inventing values.
