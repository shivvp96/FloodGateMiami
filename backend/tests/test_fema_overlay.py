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


def test_esri_single_ccw_ring_is_exterior() -> None:
    """A single CCW ring (positive area) → GeoJSON Polygon with one CW ring."""
    # CCW square: shoelace gives positive area
    ccw = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    esri = {"rings": [ccw]}
    result = _esri_geometry_to_geojson(esri)
    assert result["type"] == "Polygon"
    assert len(result["coordinates"]) == 1
    assert len(result["coordinates"][0]) == 5
    # Reversed to CW for GeoJSON output
    assert result["coordinates"][0][0] == [0, 0]
    assert result["coordinates"][0][1] == [0, 10]


def test_esri_single_cw_ring_fallback_to_containment() -> None:
    """Single CW ring with no mixed sign → containment fallback treats it as exterior."""
    cw = [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]
    esri = {"rings": [cw]}
    result = _esri_geometry_to_geojson(esri)
    # All same sign → containment fallback; largest ring becomes exterior
    assert result["type"] == "Polygon"
    assert len(result["coordinates"]) == 1


def test_esri_ccw_exterior_with_cw_hole() -> None:
    """CCW exterior + CW hole → GeoJSON Polygon[exterior, hole] with reversed winding.

    Esri/OGC convention used by this service: CCW (positive area) = exterior,
    CW (negative area) = hole. After reversal: exterior becomes CW, hole becomes CCW.
    """
    # CCW exterior (square 0..20): positive area
    ext_ccw = [[0, 0], [20, 0], [20, 20], [0, 20], [0, 0]]
    # CW hole (square 4..16): negative area
    hole_cw = [[4, 4], [4, 16], [16, 16], [16, 4], [4, 4]]
    esri = {"rings": [ext_ccw, hole_cw]}
    result = _esri_geometry_to_geojson(esri)
    assert result["type"] == "Polygon"
    assert len(result["coordinates"]) == 2
    # Exterior reversed to CW
    assert result["coordinates"][0][0] == [0, 0]
    assert result["coordinates"][0][1] == [0, 20]
    # Hole reversed to CCW
    assert result["coordinates"][1][0] == [4, 4]
    assert result["coordinates"][1][1] == [16, 4]


def test_esri_hole_before_exterior_in_array() -> None:
    """Rings are not assumed ordered; classification uses winding, not position."""
    ext_ccw = [[0, 0], [30, 0], [30, 30], [0, 30], [0, 0]]
    hole_cw = [[5, 5], [5, 25], [25, 25], [25, 5], [5, 5]]
    # Hole listed first — must still produce Polygon[exterior, hole]
    esri = {"rings": [hole_cw, ext_ccw]}
    result = _esri_geometry_to_geojson(esri)
    assert result["type"] == "Polygon"
    assert len(result["coordinates"]) == 2
    # First coordinate set is always the exterior
    assert len(result["coordinates"][0]) == 5  # exterior
    assert len(result["coordinates"][1]) == 5  # hole


def test_esri_multiple_holes_one_exterior() -> None:
    """One CCW exterior + two CW holes → Polygon with 3 rings."""
    ext_ccw = [[0, 0], [40, 0], [40, 40], [0, 40], [0, 0]]
    h1_cw = [[2, 2], [2, 12], [12, 12], [12, 2], [2, 2]]
    h2_cw = [[20, 20], [20, 35], [35, 35], [35, 20], [20, 20]]
    esri = {"rings": [ext_ccw, h1_cw, h2_cw]}
    result = _esri_geometry_to_geojson(esri)
    assert result["type"] == "Polygon"
    assert len(result["coordinates"]) == 3  # exterior + 2 holes


def test_esri_two_separate_exteriors_produces_multipolygon() -> None:
    """Two CCW rings that do not contain each other → MultiPolygon with 2 polygons."""
    ext1_ccw = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    ext2_ccw = [[20, 20], [30, 20], [30, 30], [20, 30], [20, 20]]
    esri = {"rings": [ext1_ccw, ext2_ccw]}
    result = _esri_geometry_to_geojson(esri)
    assert result["type"] == "MultiPolygon"
    assert len(result["coordinates"]) == 2
    # Each polygon has exactly one ring (no holes)
    assert len(result["coordinates"][0]) == 1
    assert len(result["coordinates"][1]) == 1


def test_esri_two_exteriors_each_with_own_hole() -> None:
    """Two CCW exteriors each containing a CW hole → MultiPolygon[[ext,h],[ext,h]]."""
    e1_ccw = [[0, 0], [15, 0], [15, 15], [0, 15], [0, 0]]
    h1_cw = [[3, 3], [3, 12], [12, 12], [12, 3], [3, 3]]
    e2_ccw = [[25, 25], [40, 25], [40, 40], [25, 40], [25, 25]]
    h2_cw = [[28, 28], [28, 37], [37, 37], [37, 28], [28, 28]]
    esri = {"rings": [e1_ccw, h1_cw, e2_ccw, h2_cw]}
    result = _esri_geometry_to_geojson(esri)
    assert result["type"] == "MultiPolygon"
    assert len(result["coordinates"]) == 2
    # Each polygon: exterior + its assigned hole
    assert len(result["coordinates"][0]) == 2  # e1 + h1
    assert len(result["coordinates"][1]) == 2  # e2 + h2


def test_esri_hole_assigned_by_containment_not_position() -> None:
    """A hole inside exterior B but listed after exterior A goes to B via containment."""
    e1_ccw = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    e2_ccw = [[50, 50], [70, 50], [70, 70], [50, 70], [50, 50]]
    # This hole is inside e2 despite being listed last
    h_cw = [[55, 55], [55, 65], [65, 65], [65, 55], [55, 55]]
    esri = {"rings": [e1_ccw, e2_ccw, h_cw]}
    result = _esri_geometry_to_geojson(esri)
    assert result["type"] == "MultiPolygon"
    # e1 has no holes
    assert len(result["coordinates"][0]) == 1
    # e2 gets the hole
    assert len(result["coordinates"][1]) == 2


def test_esri_all_same_sign_uses_containment() -> None:
    """All rings same sign → containment fallback; non-overlapping rings become separate exteriors."""
    r1_cw = [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]
    r2_cw = [[20, 20], [20, 30], [30, 30], [30, 20], [20, 20]]
    esri = {"rings": [r1_cw, r2_cw]}
    result = _esri_geometry_to_geojson(esri)
    # Neither contains the other → both classified as exteriors → MultiPolygon
    assert result["type"] == "MultiPolygon"
    assert len(result["coordinates"]) == 2


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
    ccw = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    esri = {"rings": [ccw], "paths": [[[2, 2], [3, 3]]]}
    result = _esri_geometry_to_geojson(esri)
    assert result["type"] == "Polygon"


# ---------------------------------------------------------------------------
# Integration tests for the overlay endpoint
# ---------------------------------------------------------------------------

_MOCK_ESRI_PAGE_1 = {
    "features": [
        {
            "attributes": {"OBJECTID": 1, "FZONE": "AE", "ZONESUBTY": " ", "ELEV": 9.0},
            # CCW ring (exterior, positive area)
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
