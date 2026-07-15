# DAWAL — Deployment guide (Checkpoint 11)

Four deployables: **backend API** (FastAPI + Postgres), **rider PWA** (static),
**driver portal** (static), **admin panel** (Next.js). The two static apps and
the admin talk to the backend API over HTTPS, so CORS + URLs must line up.

## 0. Decisions to make first
| Thing | Options / notes |
|---|---|
| Backend + Postgres host | Railway / Render / Fly.io (all support Docker + managed PG 16) |
| Rider + driver hosting | Netlify (you have `dawal.netlify.app`) — one site per app |
| Admin hosting | Netlify/Vercel (Next.js) or same host as backend |
| Domains | e.g. `api.` (backend), `dawal.netlify.app` (rider), `driver.` , `admin.` |
| SMS | Africa's Talking — sandbox (staging) vs live username+key (prod) |

## 1. Backend API
- Image builds from `backend/Dockerfile` (prod CMD is plain `uvicorn` — **no `--reload`**).
- On the host, set env from `.env.production.example` (real `JWT_SECRET` ≥ 32 bytes,
  `DATABASE_URL` to managed PG, real `CORS_ORIGINS`, `APP_BASE_URL`, `RIDER_APP_URL`).
- Run migrations + seed on deploy (once): `alembic upgrade head && python -m app.seed`.
  Then serve `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- **Scheduler**: keep `SCHEDULER_ENABLED=true` on exactly **one** instance; set it
  `false` on any additional web replicas (the daily job is in-process, per-worker).
- Health check: `GET /health`.

## 2. Rider PWA + Driver portal (Netlify)
- Each has a `netlify.toml` (publish `.`, SPA redirect, headers). Create one Netlify
  site per folder (`rider/`, `driver/`).
- **Set the API base** before deploy — the static apps read it from a meta tag:
  add to each `index.html` `<head>`:
  `<meta name="dawal-api" content="https://api.yourdomain.com">`
  (Without it they fall back to `http://localhost:8000` — dev only.)
- Add each site's origin to the backend `CORS_ORIGINS`.

## 3. Admin panel (Next.js)
- Build: `cd admin && npm ci && npm run build` (output `standalone`) — deploy as a
  Node app, or on Vercel.
- Set `NEXT_PUBLIC_API_URL=https://api.yourdomain.com` at build time.
- Add the admin origin to backend `CORS_ORIGINS`.

## 4. Go-live checklist
- [ ] `JWT_SECRET` ≥ 32 random bytes (not the dev default)
- [ ] `ADMIN_DEFAULT_PASSWORD` changed after first login
- [ ] `DATABASE_URL` → managed Postgres 16; `alembic upgrade head` run
- [ ] `CORS_ORIGINS` lists the real rider/driver/admin origins (no localhost)
- [ ] `APP_BASE_URL` + `RIDER_APP_URL` are the real HTTPS domains
- [ ] Static apps have the `dawal-api` meta tag pointing at the API
- [ ] SMS: real Africa's Talking live credentials (or sandbox for staging)
- [ ] Scheduler enabled on exactly one backend instance
- [ ] Set the pricing_config mobile-money numbers via admin Settings
- [ ] Seed real areas (admin → Areas & Captains) so bookings match

## Known follow-ups (not blockers)
- **Geocoding**: rider uses OpenStreetMap Nominatim (≤ ~1 req/s policy). Fine for
  real riders; swap to a paid/self-hosted geocoder before high traffic.
- **Native apps**: Capacitor wrapper is Checkpoints 12–14.
