# OpenPQ/JoTrip - Cloudflare hosting migration checkpoint
Date: 2026-10-09 (Asia/Ho_Chi_Minh)
Branch: ops/cf-pages-migration-20261009
Intent: migrate public website hosting to Cloudflare while preserving live data pipelines and protecting GitHub source in private repos.
Status: STAGING COMPLETE FOR 5; PRODUCTION DOMAIN CUTOVER NOT AUTHORIZED BY VERIFIED API CAPABILITY; PRIVATE NOT DONE.

## Completed and verified

- `kenzuko/Jotrip-Lab`: dedicated migration branch with staged builds and read-only audit.
- Cloudflare Pages Direct Upload:
  - `openpq-airport-web.pages.dev` : Stage PASS.
  - `openpq-weather-web.pages.dev` : Stage PASS.
  - `openpq-transit-web.pages.dev` : Stage PASS.
  - `openpq-dash-web.pages.dev` : Stage PASS.
  - `openpq-charter-web.pages.dev` : Stage PASS.
- `val.openphuquoc.com` has no working Pages stage. Attempted `openpq-val-web` project; Cloudflare API returned 8000000 and did not create the project. Do not interpret this as a verified monthly quota exhaustion.
- Read-only content SHA parity at workflow `CF parity report`, run `37884292148`:
  - Airport 5/5 exact, Dashboard 4/4, Charter 4/4;
  - Weather root page matches but `weather-live-config.js`, `data/critical.json`, `data/groundtruth.json`, `data/nowcast.json` differ;
  - Transit root/app match but `data/network.json` and `data/health.json` differ.
  - 22 paths tested; 16 exact bytes; 6 differences; all tested paths returned HTTP 200.
- Live-vs-stage snapshot timestamps (read directly Oct 9):
  - Weather `data/critical.json`: live generated_at `2026-10-07T06:41:24.511625+00:00`; stage `2026-10-09T08:42:06.790052+07:00`.
  - Transit `data/network.json`: live `2026-10-07T13:35:15.253510+07:00`; stage `2026-10-09T06:56:22.422758+07:00`.
  - Both original Github Pages snapshots are older. Stage is not yet proven continuously fresh.
- All Pages staging hosts deliberately send `X-Robots-Tag: noindex, nofollow, noarchive`. REMOVE THIS FLAG BEFORE ANY PUBLIC CUSTOM DOMAIN CUTOVER; otherwise the public site may be deindexed. Important: current `phuquoccharter.com` production itself also emitted noindex during baseline HEAD tests; investigate separately, do not assume intentional.

## Confirmed access boundaries

- GitHub connector exposes admin metadata/read/commit, not repository visibility management.
- Prior attempt to PATCH GitHub visibility via Windows GCM returned HTTP 400, followed by tool security blocking further credential-based attempts. DO NOT claim private was changed; do not retry in ways that evade security gates.
- Existing `Jotrip-Lab` GitHub Actions Cloudflare secret allows Cloudflare Pages project listing, project creation, and Pages Direct Upload.
- Same secret cannot read zone DNS records: `GET /zones/{zone_id}/dns_records` returned 403 Cloudflare authentication error code 10000 on both relevant zones.
- Independent deployment tests from source repos:
  - `Jotrip-Weather` CF secrets present but rejected by Cloudflare Pages project API with 403 (token not authorized).
  - `transit-jotrip` repo does not expose configured Cloudflare deployment secrets to the tested workflow.
- Thus neither Weather nor Transit has an independent ongoing Pages publication path after the original GH Pages is disabled.

## Required steps before cutover

1. Establish securely authorized Cloudflare DNS RECORDS READ+EDIT scoped to zones `openphuquoc.com` and `phuquoccharter.com`. Pages Write is required and already available only through Lab's CI. Do not paste tokens into chats or logs.
2. Read and back up *exact* live DNS records, including proxied status, TTL, CNAME/A targets, route rules, redirect rules, and rollback snapshot.
3. Configure and successfully prove source-to-Cloudflare incremental publishing, including private-repo checkout permissions; especially scheduled Weather and Transit revision updates preserving freshness and ground-truth semantics. Do not flatten independent source cadences into one common update tick.
4. Validate browser behavior on staging including FIDS, airport analytics, login/session, transit search/network, weather freshness, charter CMS/editing, mobile and language paths.
5. Build production Pages bundles WITHOUT staging noindex headers; run preflight smoke test.
6. One site at a time: bind Pages custom domain, apply confirmed DNS change with write access, verify cert/domain activation, HTTP path parity, data freshness, status, monitoring; rollback immediately on failure using backed-up DNS.
7. After proven migration and CI credentials for private cross-repo reads, change affected source repositories to Private; verify Github Actions still run and Pages custom domains still serve traffic. GitHub repository visibility is separate from site availability.

## High-risk existing cross-repo dependencies

- Weather `sync-weather-runtime.yml` uses `actions/checkout` for branches `feat/weather-lab-data-engine-v1` and `data-weather` in `kenzuko/Jotrip-Lab` WITHOUT an explicit cross-repo read PAT; if `Jotrip-Lab` is made Private, scheduled Weather mirror can break.
- Weather source/nowcast cadence includes 10-minute jobs; Transit includes 30-minute collection jobs, and some upstream data refresh only every few hours. Preserve native cadences, audit timestamps and stale policies.
- Airport live site `airport.openphuquoc.com` MUST remain functional and not be confused with OpenPQ module `/airport`; no changes to specialized module or original pipeline during hosting migration.

## Current production safety

No real domain DNS changes, GitHub Pages disable actions or repo visibility mutations were performed. Legacy websites remain serving, even when their data snapshots are stale. Staging deployments and CI read-only audits do not imply a completed production migration.

## Evidence

- Airport stage GH run: `37883115086`; verified static paths /, /app.js, /history.html, /fids-board.js.
- Dashboard/Charter stage GH run: `37883435355`.
- Weather/Transit stage GH run: `37883989281`.
- Source repo independent delivery failures: `37884181697` Weather, `37884187786` Transit.
- Parity SHA and noindex checks GH run: `37884292148`.

Next operator must RESUME FROM THIS CHECKPOINT and not repeat migration setup or change production without the missing security and live-data gates.
