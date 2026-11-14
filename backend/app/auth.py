"""Validate Supabase user access tokens for all private FloodGuard resources.

Never accept a browser-supplied user ID, a shared browser API key, or an unsigned JWT.
"""
import os
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)
LOCAL_USER_ID = "local-dev"


def _is_production() -> bool:
    return os.getenv("APP_ENV", "development").lower() in {"production", "staging"} or bool(os.getenv("VERCEL"))


@lru_cache(maxsize=4)
def _jwk_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_jwk_set=True, lifespan=300)


def get_current_user_id(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    """Return the *verified* subject of a Supabase JWT.

    Existing local development flows remain usable without Supabase credentials.
    In production, every protected request must carry a valid Supabase user JWT.
    """
    if not _is_production() and credentials is None:
        return LOCAL_USER_ID

    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not supabase_url:
        raise HTTPException(status_code=503, detail="Supabase authentication not configured")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Sign in to access your saved locations", headers={"WWW-Authenticate": "Bearer"})

    issuer = f"{supabase_url}/auth/v1"
    try:
        signing_key = _jwk_client(f"{issuer}/.well-known/jwks.json").get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience="authenticated",
            issuer=issuer,
            options={"require": ["sub", "iss", "aud", "exp", "iat"]},
            leeway=30,
        )
        user_id = str(UUID(str(claims["sub"])))
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session", headers={"WWW-Authenticate": "Bearer"}) from exc
    return user_id
