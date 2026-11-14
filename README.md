# FloodGuard Miami

**FloodGuard Miami** is a Miami-Dade flood-awareness and preparedness web application. It combines government flood-hazard data with a personal, private preparedness workspace.

## Functionality

- Real address geocoding from the US Census and mapped Miami-Dade ArcGIS FEMA flood zones.
- Interactive Leaflet map with live FEMA flood-zone polygons, including multipart geometries.
- National Weather Service forecasts and official active alerts.
- NOAA tides and planning thresholds from Virginia Key CO-OPS station 8723214.
- Ask FloodGuard AI: Gemini or OpenAI answers grounded in live FEMA/NWS/NOAA observations, with source attribution and safety caveats.
- Move My Car: authenticated owner-only saved-vehicle risk checks and optional lower mapped hazard comparisons (Zone X only; no guarantee of safe parking or routes).
- Private saved property and vehicle locations, backed by PostgreSQL in production.
- Supabase email sign-in, account-scoped saved locations and vehicles, persistent session refresh and sign-out.
- Family Flood Plan: personal meeting location, emergency contact, checklist and notes.
- Report Flooding: private, timestamped personal flood observations (unverified, not emergency reports or public flood alerts).
- Flood Memory: private browsing of your recorded past incidents.
- Flood Insurance: mapped FEMA zone for a selected property, links to FloodSmart/NFIP and FEMA Flood Map Service Center.

## Technology

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, Leaflet.
- **Backend:** FastAPI, SQLModel, PostgreSQL (SQLite only for local development).
- **Authentication:** Supabase Auth JWTs verified server-side using asymmetric JWKS; user-owned records cannot be queried by other accounts.
- **AI:** Google Gemini native generateContent or OpenAI-compatible Chat Completions, with provider credentials held exclusively server-side.
- **Hosting:** Vercel static frontend + separate Python FastAPI project.

## Local development

Install backend dependencies using Python 3.12:

```cmd
py -3.12 -m venv backend\venv
backend\venv\Scripts\python -m pip install -r backend\requirements.txt
backend\venv\Scripts\python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Install and run the frontend:

```cmd
npm ci --prefix frontend
npm run dev --prefix frontend
```

Frontend at http://127.0.0.1:5173; backend at http://127.0.0.1:8000; FastAPI OpenAPI documentation at http://127.0.0.1:8000/docs.

For local account testing, provide `SUPABASE_URL` to the backend and `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` to the frontend. Without Supabase, local development intentionally uses a special unowned local test identity when no access token is provided. This fallback is **never active in Vercel or production**.

## Testing

```cmd
backend\venv\Scripts\python -m pytest backend\tests -q
npm run build --prefix frontend
```

GitHub CI also runs both checks on pull requests.

## Deploy

See [DEPLOYMENT.md](DEPLOYMENT.md) for the Vercel projects, Supabase Postgres/Auth environment variables, release checklist, and security restrictions. Do not put any database connection string, provider credential or Supabase service-role key into a `VITE_*` frontend variable.

## Safety

This application is **not an emergency service** and cannot verify whether a street, parking spot or route is safe during flooding. FEMA flood zones and NOAA tide levels are planning information, not a real-time inundation map. Follow official NWS, local emergency management and evacuation instructions. User-submitted incident reports are private and unverified.
