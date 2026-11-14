from fastapi.testclient import TestClient

from app.main import create_app


def main() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/tides/lookup")
        print(f"HTTP status: {response.status_code}")
        print(response.json())


if __name__ == "__main__":
    main()
