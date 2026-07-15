# DAWAL

Ride/delivery booking platform for The Gambia. Human-in-the-loop dispatch (Plan A / v1).

Monorepo:

```
backend/     FastAPI + SQLAlchemy + Alembic API (Postgres)
admin/       Next.js admin panel        (added Checkpoint 5)
rider/       vanilla-JS PWA             (added Checkpoint 9)
capacitor/   native Android/iOS wrapper (added Checkpoint 11)
```

## Local development

Requires Docker Desktop. Postgres is pinned to `postgres:16`.

```bash
cp .env.example .env          # edit secrets as needed
docker compose up --build     # postgres + backend; runs migrations + seed, then serves API
```

- API:            http://localhost:8000
- Health check:   http://localhost:8000/health
- OpenAPI docs:   http://localhost:8000/docs

The backend container runs `alembic upgrade head && python -m app.seed` on start,
so the schema is migrated and config seeded automatically.

### Running backend tooling without Docker

A local venv is set up under `backend/.venv`. With a reachable Postgres
(`DATABASE_URL`), from `backend/`:

```bash
PYTHONPATH=. .venv/Scripts/python -m alembic upgrade head   # apply migrations
PYTHONPATH=. .venv/Scripts/python -m app.seed               # seed config + admin
```

Verification helpers (no database needed):

```bash
PYTHONPATH=. .venv/Scripts/python scripts/dump_ddl.py                       # dump Postgres DDL
ALEMBIC_URL=postgresql+psycopg://x .venv/Scripts/python -m alembic upgrade head --sql   # offline SQL
```

## Build status

- [x] **Checkpoint 0** — 19-table schema, models, initial migration, seed, docker-compose
- [x] **Checkpoint 1** — booking creation + OTP + area matching + consent logging (13 tests, mock SMS)
- [x] **Checkpoint 2** — claim link generation + atomic claim endpoint (race-safe; 25 tests incl. 12-way concurrency, stressed 20×)
- [x] **Checkpoint 3** — driver registration + PIN, admin JWT auth, verification queue, membership (free-trial-on-verify), credit top-up request + approval (45 tests)
- [x] **Checkpoint 4** — rider confirm-pickup + rate, no-show + priority rebook, fake-flag (refund + blacklist), override-assign, stale-unconfirmed sweep, standing recalc, disputes (62 tests)
- [x] **Checkpoint 5** — admin panel (Next.js): login, dashboard, bookings, drivers, credits + supporting GET/list endpoints (67 backend tests; admin builds + serves)
- [x] **Checkpoint 6** — admin panel: disputes, riders (PDPP export/erase), analytics, compliance (consent/retention/audit), settings (config/templates/admin users) (80 backend tests)
- [x] **Checkpoint 7** — areas CRUD, captain assignment, captain payout report (calculation only) + Areas & Captains page (85 backend tests)
- [x] **Checkpoint 8** — daily scheduler (retention scrub + stale-unconfirmed sweep + membership expiry), audit-logged; admin run-now trigger (88 backend tests)
- [x] **Checkpoint 9** — rider PWA built fresh (vanilla JS SPA: booking → OTP → consent → status → claimed → confirm → rate) + rider_access_token for secure in-app confirm (92 backend tests)
- [x] **Checkpoint 10** — driver portal (vanilla JS: register/login/pending/dashboard/top-up/renewal, phone+PIN session) + membership_requests flow + admin-editable mobile-money numbers (99 backend tests)
- [~] **Checkpoint 11** — load/race testing **done** (102 tests; caught + fixed a double-credit approval race); deploy prep done (`DEPLOY.md`, netlify.toml, `.env.production.example`) — actual deploy pending host/secret decisions
- [ ] Checkpoint 12–14 — Capacitor native wrapper (Android + iOS)

See **[DEPLOY.md](DEPLOY.md)** for the production deployment guide and go-live checklist.

## Driver portal

Vanilla HTML/CSS/JS in `driver/`, served by the `driver` compose service at http://localhost:8081
(`DRIVER_PORT` to override). No PWA shell (v1). Self-service registration (sets PIN + licence photo),
phone+PIN login → short-lived (24h) session token, dashboard (membership/credits/standing/jobs),
credit top-up and membership-renewal requests (manual proof-of-payment, admin approves).
The Wave/AfriMoney/QMoney numbers drivers pay to are stored in `pricing_config`
(`payment_wave_number` etc.) and editable from the admin **Settings** page — no redeploy.

## Rider PWA

Vanilla HTML/CSS/JS single-page app in `rider/`, served by the `rider` compose service at http://localhost:8080
(`RIDER_PORT` to override). Calls the API at `http://localhost:8000` (override via a `<meta name="dawal-api">`).
For local dev without Docker: `cd rider && python -m http.server 8080`.

Note: with `SMS_PROVIDER=africastalking_sandbox` the OTP is really sent (sandbox doesn't deliver), so to test
the rider flow end-to-end set `SMS_PROVIDER=mock` — the code prints to the backend logs.

> **Windows dev note:** after adding a new admin route file, restart the admin container
> (`docker compose restart admin`) — Docker Desktop on Windows doesn't reliably forward
> bind-mount file events, so Next's dev watcher may not see brand-new pages.

## Admin panel (Next.js)

Runs as its own compose service at http://localhost:3000 (`admin/`, App Router + TypeScript).

```bash
docker compose up --build          # backend + postgres + admin
# admin: http://localhost:3000  (log in with ADMIN_DEFAULT_EMAIL / ADMIN_DEFAULT_PASSWORD)
```

Local (without Docker): `cd admin && npm install && npm run dev`. The browser calls the API
directly, so the backend must allow the admin origin via `CORS_ORIGINS` (default
`http://localhost:3000`). If host port 3000 is taken, remap it in docker-compose.yml.

## Deferred / flagged items
- **SMS gateway**: still on mock (`SMS_PROVIDER=mock`); pick real Gambian gateway before wiring.
- **`free_trial` → `expired` status flip**: batched into Checkpoint 8 with the PDPP retention scheduler. Claim access is already safe (membership check gates on `period_end`), so this is reporting hygiene only.
- **`JWT_SECRET`**: must be >= 32 bytes in production (see .env.example).

## Tests

Run inside the backend container (host port 5432 may be shadowed by a local Postgres):

```bash
docker exec -e TEST_DATABASE_URL=postgresql+psycopg://dawal:dawal@postgres:5432/dawal_test \
  -e PYTHONPATH=/app dawal_backend sh -c "pip install -q pytest httpx && python -m pytest tests/ -v"
```

The mock SMS sender prints OTP codes to the backend logs (`docker logs dawal_backend | grep "MOCK SMS"`)
so the flow is testable locally without a real gateway.
