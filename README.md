# FloodGuard Miami

FloodGuard Miami is a Phase 1 foundation for a flood-preparedness dashboard. It contains a React + Vite + TypeScript + Tailwind frontend and a FastAPI + SQLite backend.

## Phase 1 capabilities

- Responsive dark-mode dashboard with 10 accessible sections: Dashboard, My Property, My Vehicle, Tide & Weather, Report Flooding, Ask FloodGuard AI, Flood Insurance, King Tide Watch, Family Flood Plan, and Flood Memory.
- Saved property and vehicle locations with create, list/filter, and delete functionality backed by SQLite.
- Placeholder views clearly identify capabilities planned for later phases; no external flood intelligence, AI, voice, or mapping integrations are included.

## Local setup

### Backend

```cmd
py -3.12 -m venv backend\venv
backend\venv\Scripts\python -m pip install -r backend\requirements.txt
backend\venv\Scripts\python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Backend URL: http://127.0.0.1:8000
Health check: http://127.0.0.1:8000/health
API docs: http://127.0.0.1:8000/docs

### Frontend

If Node is not already on PATH in this terminal, prefix Node commands as below:

```cmd
set "PATH=C:\Program Files\nodejs;%PATH%" && npm --prefix frontend install
set "PATH=C:\Program Files\nodejs;%PATH%" && npm --prefix frontend run dev
```

Frontend URL: http://127.0.0.1:5173

The Vite proxy forwards `/api` calls to the FastAPI server at port 8000.

## Checks

```cmd
set "PATH=C:\Program Files\nodejs;%PATH%" && npm --prefix frontend run build
backend\venv\Scripts\python -m pytest backend\tests
```
