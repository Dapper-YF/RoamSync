# RoamSync

RoamSync is a budget-aware personal travel assistant. The current development
slice includes a persisted Web planning workbench, a FastAPI/PostgreSQL backend,
and the existing native Android client.

## Prerequisites

- Docker Desktop
- Docker Compose
- Android Platform Tools for later USB device integration

## Start the full stack

Copy `.env.example` to `.env`, then:

```powershell
docker compose up -d --build
docker compose ps
```

Local PostgreSQL uses one shared development database. Connect from Navicat
Premium with these values:

| Setting | Value |
| --- | --- |
| Connection type | PostgreSQL |
| Host | `127.0.0.1` |
| Port | `54329` |
| Initial database | `roamsync` |
| User name | `roamsync` |
| Password | `123123` |

The host port is intentionally bound only to `127.0.0.1`. This password is for
local development and must be replaced before any public deployment.

The persisted Web travel directory is available at
`http://127.0.0.1:3000/trips`. Create a trip by selecting a real AMap city,
then the browser opens `/trips/{trip-uuid}/planner`. The API is available at
`http://127.0.0.1:8000`, with interactive documentation at
`http://127.0.0.1:8000/docs`.

The seed command is idempotent and does not overwrite an existing demo trip.
To restore only the fixed Hangzhou demo data, run:

```powershell
docker compose exec api uv run --no-sync python -m app.seed_demo --reset
```

The containers use `restart: "no"`; start and stop them manually:

```powershell
docker compose start
docker compose stop
```

## Run integration tests

Tests run against an isolated PostgreSQL instance, never the development
database:

```powershell
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from api-test
docker compose -f compose.test.yaml down -v
```

## Android USB access

Open the `android` directory in Android Studio. The debug build connects to
`http://127.0.0.1:8000`; cleartext HTTP is enabled only for debug builds.

On this workstation Android Studio is installed on the D drive. Open the
project without starting an emulator:

```powershell
& 'D:\Android Studio\bin\studio64.exe' 'E:\Study\RoamSync\android'
```

With a USB-debuggable device connected, expose the Docker API to the device:

```powershell
adb reverse tcp:8000 tcp:8000
```

The debug Android app can then use `http://127.0.0.1:8000` as its API base URL.

Build and test from PowerShell with JDK 17:

```powershell
$env:JAVA_HOME = 'D:\Java\jdk-17'
Set-Location E:\Study\RoamSync\android
.\gradlew.bat testDebugUnitTest assembleDebug
```

The first client flow uses the real backend:

1. Check backend readiness.
2. Create a trip with total and daily budgets.
3. Record an expense with an idempotency key.
4. Refresh and display today's and total remaining budget.

## Web planning workbench

The Web app lists and creates real trips through FastAPI. A selected city is
stored with its AMap adcode, citycode and center coordinates; one `DayPlan` is
created for each trip date. Accommodation can be selected from a real AMap POI
search and is stored with its provider ID, address, district and coordinates.
Activities, ordering, candidates, sources, routes, and planning budgets are persisted in PostgreSQL. Refreshing the page or
restarting the API and Web containers does not discard changes.

The trip directory supports lifecycle filters, text search, editing with
optimistic version checks, deep duplication, archive, and deletion with an
impact preview. Changing a trip's dates synchronizes its day plans; shortening
a trip across days that contain activities requires a second explicit
confirmation.

Activities also use optimistic versions. `PUT /api/v1/activities/{activity_id}`
can update a custom display name, start time, duration, estimated cost, status,
note, and the explicit-time lock. A stale version returns HTTP 409 instead of
overwriting newer data. Time and duration edits reschedule later unlocked
activities from persisted route legs and therefore do not make an additional
AMap request. Activities marked `skipped` remain visible in the itinerary but
are excluded from the planning-budget total.

`POST /api/v1/activities/{activity_id}/move` moves or repositions an activity
with the same optimistic version guard. Cross-day moves lock both day plans,
renumber both timelines, recalculate their persisted routes, and commit as one
transaction. Invalid target positions, cross-trip moves, duplicate places, and
route-provider failures leave the original itinerary unchanged. The Web
inspector exposes full activity editing plus accessible move-to-start/end
controls; desktop users can also drag a timeline activity onto another date
tab to append it to that day.

The workbench can also search POIs through the server, switch between walking,
public-transit, and driving routes, persist route legs, and recalculate later
activity times after an add, delete, or reorder. POI search results are
transient: searching does not write planning rows. A provider snapshot and its
source record are persisted transactionally only when the user confirms
"加入行程". Existing saved candidates remain compatible with the same add
endpoint. Route responses are cached in PostgreSQL for 24 hours by default.

AMap failures use a stable error payload with a machine-readable code. Quota
errors return HTTP 429; invalid credentials, missing configuration, provider
rejections, and network failures are distinguished without exposing API keys.

For frontend-only development, keep the Docker API running and start Vite:

```powershell
Set-Location E:\Study\RoamSync\web
pnpm install --frozen-lockfile
pnpm dev
```

Open `http://127.0.0.1:5173/trips`. Playwright starts Vite in test mode and uses
an isolated repository fixture only for automated visual tests. Its 1440×900 and 1024×768 visual
baselines live beside `web/e2e/planner.spec.ts`.

To use the real AMap base map, copy `web/.env.example` to `web/.env.local` and
set both values below:

```dotenv
VITE_AMAP_WEB_KEY=your_web_js_api_key
VITE_AMAP_SECURITY_CODE=your_security_js_code
```

For server-side POI and route requests, set the Web Service REST key in the
root `.env` before rebuilding the API:

```dotenv
AMAP_REST_KEY=your_web_service_rest_key
ROUTE_CACHE_TTL_SECONDS=86400
ALLOW_MAP_ESTIMATES=false
```

The browser never receives `AMAP_REST_KEY`. When it is absent, POI search is
rejected and route writes return a service error; production data is never
silently replaced with an estimate. Tests explicitly enable estimates only in
their isolated environment.

Product-reference decisions and license boundaries are documented in
`docs/REFERENCE_RESEARCH.md` and `THIRD_PARTY_NOTICES.md`. TREK is an
AGPL-3.0 interaction reference only; none of its source code or assets are
included.

Without those values the workbench deliberately shows a styled map fallback
and configuration guidance instead of a blank canvas. The security code is
front-end visible in this local prototype; a production phase must move it
behind a server-side proxy.

Quality checks:

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm e2e
```

The prototype supports desktop and landscape tablet layouts (1440×900 and
1024×768 acceptance sizes). Mobile Web, Android redesign, authentication,
hotel inventory, agent workflows, and automatic opening-hours validation remain
outside this phase. Planning data is persisted; the existing expense ledger and
planning budget intentionally remain separate concepts.
