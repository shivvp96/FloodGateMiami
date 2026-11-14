# FloodGuard Miami — Production deployment

This repository contains two separate Vercel projects. Keep the submitted frontend intact until preview validation is complete.

## 1. Supabase project

1. Create a Supabase project and enable **Auth → Providers → Email**.
2. Use an **asymmetric JWT signing key (ES256 or RS256)**. The FastAPI backend verifies Supabase JWKS and deliberately does not accept unsigned tokens or the legacy HS256 signing secret.
3. Set the redirect/site URLs to the deployed frontend in Supabase Auth.
4. Obtain the project's URL, *publishable/anon* API key, and PostgreSQL **pooler** connection string. The pooler string must have SSL enabled and should be stored only on the backend.

Supabase secret/service_role keys must not be used in the React frontend.

## 2. Backend Vercel project

Import GitHub repo `shivvp96/FloodGateMiami` as a **second** Vercel project.

- Root directory: `backend`
- Framework: Other (Python entrypoint `backend/app.py`, routing in `backend/vercel.json`)
- Production branch: `main`, *after* passing CI and preview checks

Backend environment variables (set in Vercel, never in Git or React):

| Name | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | Supabase PostgreSQL transaction-pooler URI, with `sslmode=require` |
| `CORS_ORIGINS` | `https://flood-gate-miami.vercel.app` |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `LLM_PROVIDER` | `gemini` or `openai` |
| `LLM_API_KEY` | **fresh, unexposed** provider key |
| `LLM_BASE_URL` | Gemini native: `https://generativelanguage.googleapis.com/v1beta`; OpenAI: `https://api.openai.com/v1` |
| `LLM_MODEL` | Gemini verified: `gemini-flash-lite-latest`; OpenAI fallback: `gpt-4o-mini` |

`SAVED_LOCATIONS_API_KEY` is no longer used for browser authentication. Saved locations and Move My Car now require a verified Supabase user bearer token.

Set `APP_ENV=production` to ensure no SQLite fallback. Test `https://<backend>/health` returns `{"status":"ok"}` before connecting the frontend.

**Database note:** The backend's current startup migration adds `user_id` without deleting legacy rows. Old anonymous records remain `NULL` and are invisible to all production users; they must never be automatically assigned to an account. For a production launch, review and adopt managed migrations (e.g. Alembic) before running multiple concurrent migrations.

## 3. Frontend Vercel project

Existing project: `https://flood-gate-miami.vercel.app`.

Set these public **build-time** values and redeploy the frontend:

| Name | Value |
| --- | --- |
| `VITE_API_BASE_URL` | Public HTTPS URL of backend project, no trailing slash |
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase **publishable/anon** key only |

Never add `DATABASE_URL`, `LLM_API_KEY`, a Supabase secret key, or a shared saved-location key to any `VITE_*` variable.

## 4. Acceptance tests

- Verify `/health` (200), then address lookup, FEMA overlay, NWS and NOAA endpoints from the public browser.
- Sign up with a new email; confirm email if required; sign in and refresh browser.
- Save and delete a property and vehicle; verify persistence after reload and server restart.
- Use a **second account** to confirm the first account's locations are not visible; cross-account IDs must not permit delete, vehicle risk assessments, or parking candidate leaks.
- Ask FloodGuard AI a question for a geocoded Miami address and confirm real provider output with government grounding.
- Check FEMA Zone X can be surfaced as a lower mapped hazard alternative to Zone AE, but never OPEN WATER, D, missing, or another user's locations.
- Inspect browser devtools for CORS failures and for absence of backend secrets.
- Run backend pytest and frontend build CI before merging.

## 5. Production safety

- Rotate the Gemini API key previously disclosed in conversation before enabling public use.
- Configure platform-enforced rate limits and request/budget quotas for `/api/v1/ai/ask`, geocoding, and expensive overlays before open launch. In-process counters are not sufficient for globally distributed Vercel functions.
- Add monitoring for 5xx errors, timeouts, database failures, and LLM spend; set database backups and retention.
- Flood hazard map and tide data are **not real-time street inundation forecasts**. Avoid promising a parking route or destination is safe.
- Do not make the existing public frontend dependent on the auth work until the new backend has been verified in preview.
