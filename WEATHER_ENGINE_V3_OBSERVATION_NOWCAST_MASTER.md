# WEATHER ENGINE V3 - OBSERVATION & NOWCAST MASTER

Status: SHADOW ARCHITECTURE
Date: 2026-10-01

## 1. Non-negotiable lock

Weather V3 is an additive evidence layer.

It MUST NOT:
- rebuild Weather V2 from scratch
- replace the current ECMWF/marine runtime before shadow verification
- make any new external source a single point of failure
- let browser code fetch external weather sources directly
- coerce missing observations to zero
- count two URLs from the same backend as two independent observations
- relabel radar/satellite/derived products as ground observations
- remove a researched source merely because it is not yet production eligible

The canonical production Weather runtime remains unchanged until a later explicit promotion.

## 2. Source universe stays complete

All discovered sources remain in the V3 registry with:
- role
- evidence class
- acquisition mode
- lifecycle
- rights state
- independence group
- provenance
- health/freshness when collected

A source may be HOLD or REJECTED for production and still remain in the registry.

## 3. Evidence classes

GROUND_OBSERVED
- VVPQ METAR/SPECI
- VRain
- WMO/SYNOP 48917 after identity/source-skill gates

MARINE_GROUND_OBSERVED
- 60018 only if a usable current numeric stream is actually obtained

REMOTE_OBSERVED
- Himawari
- Vietnam radar
- lightning

REMOTE_RENDERED_OBSERVED
- fallback interpretation of a publicly rendered radar/lightning/weather product
- lower confidence than a direct machine-readable observation
- not stored as a ground measurement

DERIVED_OBSERVATION
- radar motion
- ETA
- growth/decay
- radar QPE

OFFICIAL_FORECAST
- official Vietnamese rain/wave products when reuse route is cleared

OFFICIAL_ALERT
- official hazard warnings when reuse route is cleared

MODEL_FORECAST
- ECMWF and the existing model stack

HISTORICAL_VALIDATION
- ISD/HadISD/SYNOP archive and other verified historical observations

## 4. V3 flow

ALL SOURCE REGISTRY
  -> ACCESS / RIGHTS GATE
  -> SOURCE COLLECTORS OR RENDERED INTERPRETER
  -> RAW EVIDENCE / OBSERVATION RECEIPTS
  -> NORMALIZE + QC
  -> STATION / PHYSICAL SITE IDENTITY
  -> INDEPENDENCE / DEDUPE
  -> EVIDENCE RESOLVER
  -> LOCAL NOW
  -> NOWCAST 0-120 MIN
  -> FORECAST CONSENSUS / DISAGREEMENT
  -> DECISION ENGINE
  -> HUMAN WEATHER CONTRACT
  -> Weather + Homepage

## 5. Acquisition priority

For public rendered systems such as radar:

1. numeric/grid data
2. georeferenced raster
3. tile/WMS or timestamped public asset
4. deterministic image parser
5. rendered-product Vision interpretation as fallback

Do not jump to Vision while a stable georeferenced asset is available.

## 6. Vietnam radar rules

Radar is high-value for short-term motion, not a replacement for rain gauges.

Use positive radar evidence strongly:
- echo present
- echo approaching
- growth/decay
- convective intensity class

Use negative radar evidence cautiously around Phu Quoc until empirical coverage skill is measured.

Never infer:
- no echo = no rain
- reflectivity color = exact surface rain rate without calibration

Radar QPE remains DERIVED_OBSERVATION and is checked against VRain.

## 7. Rendered Observation Interpreter

If no stable machine-readable route is available but an official public product remains viewable, V3 may produce an observation receipt from the render.

Rules:
- do not mirror the external viewer
- do not republish source imagery unless reuse rights are explicitly cleared
- fetch/render only at source cadence
- retain provenance and displayed timestamp
- store derived facts, confidence and interpreter version
- keep the source image ephemeral when rights are unresolved
- never upgrade a rendered observation to ground measurement

## 8. Station identity

Identity keys must support:
- namespace
- identifier
- station epoch
- physical_site_id
- platform_id
- independence_group

WMO 48917 identity is resolved on the parent branch from WMO OSCAR as a Dương Đông physical site separate from VVPQ. It remains source-skill gated before directly correcting Local Now.

60018 remains a separate identifier until equipment-level mapping proves otherwise.

## 9. 60018 timebox

Do one public technical probe:
- inspect current public export
- parse whether numeric rows actually exist
- preserve timestamp semantics

If usable numeric rows are absent:
- lifecycle = HOLD
- do not keep digging
- do not block V3

## 10. iWeather technical target

P0 acquisition target:
- COM + CMAX
- timeline frame change
- lightning layer
- radar QPE / accumulated rainfall

The probe should determine whether the public browser receives:
- JSON / GeoJSON
- raster
- tile/WMS
- timestamped image
- rendered-only output

Store request metadata first. Do not archive radar image bodies by default.

## 11. Independence groups

Examples:

iWeather radar + Hymetnet radar
- likely one national radar lineage until proven otherwise
- one independence group

VRain stations
- one source family but distinct physical gauges may still be spatially useful

Multiple frontends or aliases never create extra confidence votes.

## 12. Freshness

Freshness is source-specific.

Track:
- observed_at
- received_at
- median cadence
- p95 cadence
- current age

States:
- FRESH
- DELAYED
- STALE
- DOWN
- UNKNOWN

Fetch time is not observation time.

## 13. Shadow event store

Every meaningful rain/thunderstorm event should eventually preserve:

- radar evidence
- lightning evidence
- Himawari trend
- VRain actual
- VVPQ / 48917 actual where relevant
- model forecast
- V3 ETA / nowcast
- final observed outcome

Evaluation:
- HIT
- MISS
- FALSE_ALARM
- timing error

The purpose is to learn Phu Quoc-specific radar/nowcast skill instead of inventing confidence by hand.

## 14. Promotion stages

DISCOVERED
-> PROBE
-> ARCHIVE_ONLY
-> SHADOW
-> ACTIVE

Promotion requires:
- source identity understood
- timestamps understood
- null semantics understood
- rights/access state acceptable
- freshness measurable
- failure behavior safe
- no double-counting
- shadow verification proves value

## 15. Rollout

V3.0A Acquisition
- source registry
- public probes
- observation receipts
- source health
- no production UI change

V3.0B Evidence
- normalize
- identity
- independence groups
- confidence inputs
- still shadow

V3.0C Nowcast
- 0-120 minute radar motion
- event evaluation against VRain
- no decision promotion until skill is measured

V3.0D Production
- explicit promotion only
- Human Weather and Homepage consume promoted V3 evidence
- rollback remains possible

## 16. Required failure tests

- radar missing for hours -> Weather still runs
- stale radar frame -> not current
- blank radar near coverage edge -> not "dry"
- VRain says rain while radar is blank -> gauge wins rain_now
- radar approaching while gauges are dry -> nowcast only, not "raining now"
- alias/backend duplicates -> no double vote
- source HTML/tile schema changes -> fail closed
- external source starts requiring auth -> disable probe, do not bypass
- UTC/local timestamp mismatch -> reject
- null -> never zero
- source outage -> decision engine does not silently downgrade/upgrade
- every Human Weather conclusion remains traceable to evidence

## 17. Production dependency rule

Core Weather must continue operating with the existing source stack.

New V3 sources increase evidence quality.
They do not become mandatory for availability.
