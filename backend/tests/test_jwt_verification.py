"""JWT verification must validate signature, issuer, audience and expiration."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.db import engine
from app.main import create_app

USER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def test_verified_supabase_jwt_and_rejected_forgery(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = {
        "sub": USER, "iss": "https://test-project.supabase.co/auth/v1",
        "aud": "authenticated",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
    }

    def token(data, *, key=private_key):
        return jwt.encode(data, key, algorithm="RS256", headers={"kid": "test"})

    jwks = SimpleNamespace(get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=private_key.public_key()))
    app = create_app()
    with patch("app.auth._jwk_client", return_value=jwks), TestClient(app) as client:
        good = client.get("/api/v1/saved-locations/", headers={"Authorization": f"Bearer {token(claims)}"})
        assert good.status_code == 200, good.text
        forged = client.get("/api/v1/saved-locations/", headers={"Authorization": f"Bearer {token(claims, key=other_private_key)}"})
        assert forged.status_code == 401
        wrong_iss = client.get("/api/v1/saved-locations/", headers={"Authorization": f"Bearer {token({**claims, 'iss': 'https://evil.example/auth/v1'})}"})
        assert wrong_iss.status_code == 401
        expired = client.get("/api/v1/saved-locations/", headers={"Authorization": f"Bearer {token({**claims, 'exp': int((datetime.now(UTC) - timedelta(hours=1)).timestamp())})}"})
        assert expired.status_code == 401
        wrong_aud = client.get("/api/v1/saved-locations/", headers={"Authorization": f"Bearer {token({**claims, 'aud': 'anon'})}"})
        assert wrong_aud.status_code == 401
