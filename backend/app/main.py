from contextlib import asynccontextmanager

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .saved_locations.routes import router as saved_locations_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="FloodGuard Miami API", version="0.1.0", lifespan=lifespan)
    cors_origins_raw = os.environ.get("CORS_ORIGINS")
    if cors_origins_raw:
        allow_origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]
    else:
        # Local development defaults (preserved)
        allow_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(saved_locations_router, prefix="/api/v1/saved-locations", tags=["saved locations"])
    return app


app = create_app()
