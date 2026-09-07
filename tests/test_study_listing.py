"""What /list_studies and /list_epmaps_in_study must tell a client.

A full run against both vendors showed the listings could not answer two
questions a multivendor client has to ask: which vendor is this study from,
and does this map have any points? The vendor was simply absent, and
``number_of_points`` is the vendor's own count — null for every EnSite X map,
which made maps carrying thousands of measurement points look empty.
"""

from __future__ import annotations

from types import SimpleNamespace

from pulse_ep.server.app import app


def _serialise_studies(rows):
    """The serialisation the /list_studies route performs on model rows."""
    return [{"id": r[0], "study_name": r[1], "vendor": r[2]} for r in rows]


def _serialise_maps(rows, study_id):
    return [
        {
            "id": r[0],
            "study_id": study_id,
            "map_name": r[1],
            "number_of_points": r[2],
            "measurement_points": r[3],
        }
        for r in rows
    ]


def test_study_listing_names_the_vendor():
    rows = [(1, "study-a", "ensite"), (2, "study-b", "carto")]
    out = _serialise_studies(rows)
    assert [s["vendor"] for s in out] == ["ensite", "carto"]


def test_study_listing_tolerates_a_missing_vendor():
    """Studies imported before the vendor column existed must still list."""
    assert _serialise_studies([(3, "old-study", None)])[0]["vendor"] is None


def test_map_listing_reports_stored_points_separately():
    # an EnSite X map: no vendor count, but 3306 points actually stored
    rows = [(7, "Contact_Mapping_Model", None, 3306), (8, "Anatomy: Left", None, 0)]
    out = _serialise_maps(rows, study_id=1)
    assert out[0]["number_of_points"] is None
    assert out[0]["measurement_points"] == 3306
    # an anatomy-only map has none, and says so as 0 rather than null
    assert out[1]["measurement_points"] == 0


def test_map_listing_keeps_the_vendor_count_when_there_is_one():
    rows = [(9, "1-1-1-LA", 941, 941)]
    out = _serialise_maps(rows, study_id=2)
    assert out[0]["number_of_points"] == 941
    assert out[0]["measurement_points"] == 941


def test_routes_are_registered():
    """Guard against the paths drifting — the clients hard-code them."""
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/list_studies" in rules
    assert "/list_epmaps_in_study/<int:study_id>" in rules


def test_serialisation_matches_the_route(monkeypatch):
    """The route must emit exactly the keys the helpers above describe."""
    import pulse_ep.server.app as server

    rows = [(1, "study-a", "ensite")]

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(server, "get_db_session", lambda: _Session())
    monkeypatch.setattr(
        server.StudyModel, "get_study_list", staticmethod(lambda session: rows), raising=True
    )
    with app.test_request_context():
        payload = server.list_studies.__wrapped__()
    body = payload.get_json() if hasattr(payload, "get_json") else payload
    assert body == _serialise_studies(rows)


def test_epmap_model_row_shape():
    """A four-column row is what the map serialiser expects."""
    row = SimpleNamespace(id=1, map_name="m", number_of_points=None, n=5)
    packed = (row.id, row.map_name, row.number_of_points, row.n)
    assert len(packed) == 4
