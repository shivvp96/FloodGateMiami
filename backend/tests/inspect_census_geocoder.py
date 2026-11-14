import asyncio
from typing import Any

import httpx

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
ADDRESSES = (
    "4600 Silver Hill Rd, Washington, DC 20233",
    "111 NW 1st St, Miami, FL 33128",
)


async def inspect_address(client: httpx.AsyncClient, address: str) -> None:
    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "format": "json",
    }
    print(f"\nADDRESS: {address}")
    try:
        response = await client.get(CENSUS_URL, params=params)
        print(f"HTTP status: {response.status_code}")
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        print(f"REQUEST_OR_JSON_ERROR: {type(exc).__name__}: {exc}")
        return

    print(f"response keys: {sorted(payload.keys())}")
    result = payload.get("result")
    print(f"result keys: {sorted(result.keys()) if isinstance(result, dict) else result}")
    matches = result.get("addressMatches") if isinstance(result, dict) else None
    print(f"result.addressMatches type: {type(matches).__name__}")
    print(f"result.addressMatches count: {len(matches) if isinstance(matches, list) else 'not-a-list'}")
    if not isinstance(matches, list) or not matches:
        print("VALID_ZERO_MATCH_RESULT: true")
        return

    best = matches[0]
    print(f"matchedAddress: {best.get('matchedAddress')}")
    print(f"coordinates: {best.get('coordinates')}")
    print(f"match keys: {sorted(best.keys())}")


async def main() -> None:
    async with httpx.AsyncClient(timeout=20.0) as client:
        for address in ADDRESSES:
            await inspect_address(client, address)


if __name__ == "__main__":
    asyncio.run(main())
