from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.address_lookup.service import _esri_geometry_to_geojson
from app.main import create_app


# ---------------------------------------------------------------------------
# Focused unit tests for _esri_geometry_to_geojson
# ---------------------------------------------------------------------------

def test_esri_none_returns_empty_polygon() -> None:
    result = _esri_geometry_to_geojson(None)
    assert result == {"type": "Polygon", "coordinates": []}


def test_esri_empty_dict_returns_empty_polygon() -> None:
    result = _esri_geometry_to_geojson({})
    assert result == {"type": "Polygon", "coordinates": []}


def test_esri_single_ring_polygon() -> None:
    """A single-ring Esri polygon → GeoJSON Polygon with one ring, reversed winding."""
    esri = {"rings": [[[-80.2, 25.77], [-80.19, 25.77], [-80.19, 25.78], [-80.2, 25.78], [-80.2, 25.77]]]}
    result = _esri_geometry_to_geojson(esri)
    assert result["type"] == "Polygon"
    # 1 ring (outer), 5 vertices
    assert len(result["coordinates"]) == 1
    assert len(result["coordinates"][0]) == 5
    # First vertex of reversed ring is the last vertex of original
    assert result["coordinates"][0][0] == [-80.2, 25.77]
    assert result["coordinates"][0][1] == [-80.2, 25.78]


def test_esri_polygon_with_hole() -> None:
    """Esri polygon with 2 rings (outer + hole) → GeoJSON Polygon with 2 rings.

    GeoJSON spec: Polygon.coordinates = [outer_ring, hole1, hole2, ...].
    The outer ring is CCW and the holes are CW after reversal.
    """
    outer = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    hole = [[2, 2], [8, 2], [8, 8], [2, 8], [2, 2]]
    esri = {"rings": [outer, hole]}
    result = _esri_geometry_to_geojson(esri)
    assert result["type"] == "Polygon"
    # 2 rings: outer + hole
    assert len(result["coordinates"]) == 2
    # Outer ring reversed: first vertex is [0, 0] (was last in Esri CW order)
    assert result["coordinates"][0][0] == [0, 0]
    assert result["coordinates"][0][1] == [0, 10]
    # Hole ring reversed similarly
    assert result["coordinates"][1][0] == [2, 2]
    assert result["coordinates"][1][1] == [2, 8]


def test_esri_polygon_with_multiple_holes() -> None:
    """3 rings → Polygon with outer + 2 holes."""
    outer = [[0, 0], [20, 0], [20, 20], [0, 20], [0, 0]]
    hole1 = [[2, 2], [6, 2], [6, 6], [2, 6], [2, 2]]
    hole2 = [[10, 10], [16, 10], [16, 16], [10, 16], [10, 10]]
    esri = {"rings": [outer, hole1, hole2]}
    result = _esri_geometry_to_geojson(esri)
    assert result["type"] == "Polygon"
    assert len(result["coordinates"]) == 3
    assert len(result["coordinates"][0]) == 5  # outer
    assert len(result["coordinates"][1]) == 5  # hole1
    assert len(result["coordinates"][2]) == 5  # hole2


def test_esri_paths_to_multilinestring() -> None:
    esri = {"paths": [[[-80.2, 25.77], [-80.19, 25.78]], [[-80.18, 25.76], [-80.17, 25.75]]]}
    result = _esri_geometry_to_geojson(esri)
    assert result == {"type": "MultiLineString", "coordinates": esri["paths"]}


def test_esri_point() -> None:
    esri = {"x": -80.196, "y": 25.775}
    result = _esri_geometry_to_geojson(esri)
    assert result == {"type": "Point", "coordinates": [-80.196, 25.775]}


def test_esri_multipoint() -> None:
    esri = {"points": [[-80.2, 25.77], [-80.1, 25.78]]}
    result = _esri_geometry_to_geojson(esri)
    assert result == {"type": "MultiPoint", "coordinates": [[-80.2, 25.77], [-80.1, 25.78]]}


def test_esri_rings_take_precedence_over_paths() -> None:
    """When both rings and paths are present, rings win."""
    esri = {"rings": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]], "paths": [[[2, 2], [3, 3]]]}
    result = _esri_geometry_to_geojson(esri)
    assert result["type"] == "Polygon"


# ---------------------------------------------------------------------------
# Integration tests for the overlay endpoint
# ---------------------------------------------------------------------------

# Esri JSON responses (f=json) with rings geometry and attributes.
_MOCK_ESRI_PAGE_1 = {
    "features": [
        {
            "attributes": {"OBJECTID": 1, "FZONE": "AE", "ZONESUBTY": " ", "ELEV": 9.0},
            "geometry": {"rings": [[[-80.2, 25.77], [-80.19, 25.77], [-80.19, 25.78], [-80.2, 25.78], [-80.2, 25.77]]]},
        },
        {
            "attributes": {"OBJECTID": 2, "FZONE": "X", "ZONESUBTY": "0.2 PCT", "ELEV": -9999},
            "geometry": {"rings": [[[-80.18, 25.76], [-80.17, 25.76], [-80.17, 25.77], [-80.18, 25.77], [-80.18, 25.76]]]},
        },
    ],
    "exceededTransferLimit": True,
}

_MOCK_ESRI_PAGE_2 = {
    "features": [
        {
            "attributes": {"OBJECTID": 3, "FZONE": "VE", "ZONESUBTY": " ", "ELEV": 11.0},
            "geometry": {"rings": [[[-80.16, 25.75], [-80.15, 25.75], [-80.15, 25.76], [-80.16, 25.76], [-80.16, 25.75]]]},
        }
    ],
}

_MOCK_ESRI_EMPTY = {"features": []}


def _overlay(client: TestClient):
    return client.get(
        "/api/v1/address/overlay",
        params={"sw_lat": 25.7, "sw_lon": -80.3, "ne_lat": 25.8, "ne_lon": -80.1},
    )


def test_overlay_returns_geojson_features() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                _response(200, _MOCK_ESRI_PAGE_1),
                _response(200, _MOCK_ESRI_PAGE_2),
            ]
            response = _overlay(client)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["total_returned"] == 3
    assert data["exceeded_transfer_limit"] is False
    assert len(data["features"]) == 3
    assert data["features"][0]["properties"]["FZONE"] == "AE"
    # Esri rings converted to GeoJSON polygon coordinates
    assert data["features"][0]["geometry"]["type"] == "Polygon"
    assert len(data["features"][0]["geometry"]["coordinates"][0]) == 5


def test_overlay_marks_incomplete_when_exceeded_transfer_limit() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                _response(200, _MOCK_ESRI_PAGE_1),
                _response(200, _MOCK_ESRI_EMPTY),
            ]
            response = _overlay(client)

    data = response.json()
    assert data["status"] == "incomplete"
    assert data["exceeded_transfer_limit"] is True
    assert data["total_returned"] == 2
    assert "incomplete" in data["message"].lower()


def test_overlay_marks_incomplete_when_later_page_errors() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                _response(200, _MOCK_ESRI_PAGE_1),
                _server_error(),
                _server_error(),
            ]
            response = _overlay(client)

    data = response.json()
    assert data["status"] == "incomplete"
    assert data["total_returned"] == 2


def test_overlay_retries_transient_500() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                _response(200, _MOCK_ESRI_PAGE_1),
                _server_error(),
                _response(200, _MOCK_ESRI_PAGE_2),
            ]
            response = _overlay(client)

    data = response.json()
    assert data["status"] == "ok"
    assert data["total_returned"] == 3


def test_overlay_empty_bounds_returns_ok() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response(200, _MOCK_ESRI_EMPTY)
            response = _overlay(client)

    data = response.json()
    assert data["status"] == "ok"
    assert data["total_returned"] == 0


def test_overlay_rejects_invalid_bounds() -> None:
    with TestClient(create_app()) as client:
        response = client.get(
            "/api/v1/address/overlay",
            params={"sw_lat": 25.8, "sw_lon": -80.1, "ne_lat": 25.7, "ne_lon": -80.3},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_bounds"


def test_overlay_handles_upstream_failure() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("arcgis failed")
            response = _overlay(client)

    assert response.status_code == 503


def _response(status_code: int, json_payload: dict) -> object:
    class _MockResponse:
        def __init__(self) -> None:
            self.status_code = status_code

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("error", request=None, response=self)

        def json(self) -> dict:
            return json_payload

    return _MockResponse()


def _server_error():
    class _ErrorResp:
        status_code = 500

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError("server error", request=None, response=self)

        def json(self) -> dict:
            return {}

    return _ErrorResp()
