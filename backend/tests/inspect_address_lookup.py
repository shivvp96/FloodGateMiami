import asyncio
import os

from fastapi.testclient import TestClient

from app.main import create_app


ADDRESS = "111 NW 1st St, Miami, FL 33128"


def main() -> None:
    os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/address/lookup", params={"address": ADDRESS})
        print(f"HTTP status: {response.status_code}")
        print(f"response JSON: {response.json()}")


if __name__ == "__main__":
    main()
