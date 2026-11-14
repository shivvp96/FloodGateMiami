import asyncio

from fastapi.testclient import TestClient

from app.main import create_app


async def fetch() -> None:
    with TestClient(create_app()) as client:
        # Coordinates from verified Phase 2.1 address lookup for 111 NW 1st St, Miami, FL 33128
        response = client.get("/api/v1/weather/lookup", params={"lat": 25.7751, "lon": -80.1963})
        print(f"HTTP status: {response.status_code}")
        print(response.json())


if __name__ == "__main__":
    asyncio.run(fetch())
