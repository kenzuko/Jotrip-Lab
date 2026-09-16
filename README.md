# JoTrip Airport Live

Airport operations dashboard for Phu Quoc International Airport (PQC).

## Product rule

Open the page and understand the airport in about three seconds.

## Current data plane

The UI does not scrape Sun Airport. It reads normalized snapshots produced by JoTrip-Lab:

- `data-sunairport/data/sunairport/latest.json`
- `data-sunairport/data/sunairport/health.json`

The collector is Playwright on GitHub Actions. Normalization and QA happen before the snapshot is published.

## Data truth rules

- `GOOD`: snapshot age <= 30 minutes and QA passes.
- `WATCH`: snapshot age > 30 and <= 90 minutes.
- `STALE`: snapshot age > 90 minutes.
- Fetch failure is shown as a data failure. The UI must not present cached/old data as live.
- Aircraft position is not inferred from scheduled time or airport status. Until an independent aircraft-tracking source is added, the flight detail only displays verified board status.

## UI modes

### LIVE

- Today at PQC
- Arrivals / Departures / All flights
- Search and operational filters
- Next 3 hours
- Operations Watch
- Next Arrivals
- Data Health

### ANALYTICS

- Domestic / international split
- Top origin/destination stations
- Arrival time-bank distribution
- Board status summary

## Deployment

Static page files live under `/airport-live/`. It can be served from the existing JoTrip-Lab web deployment without changing the root game route.
