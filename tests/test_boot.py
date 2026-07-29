"""End-to-end boot: the app builds, seeds a starter board, streams it over the websocket, and writes
land through the HTTP router. Uses the in-process FastAPI TestClient (lifespan runs the watchdog)."""

from fastapi.testclient import TestClient

from backend.app import create_app


def _client(tmp_path):
    app = create_app(db_folder=tmp_path / "db", serve_frontend_dist=False)
    return TestClient(app)


def test_websocket_snapshot_has_seeded_board(tmp_path):
    with _client(tmp_path) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"op": "subscribe", "sub_id": "s1", "derived_dict": "DB", "key_path": ""})
            frame = ws.receive_json()
            assert frame["op"] == "subscribed"
            board = frame["value"]
            assert set(board) >= {"meta", "projects", "tags", "columns", "tasks"}
            assert len(board["columns"]) >= 1                # the app mandates >= 1 column
            assert board["meta"]["assignee.json"]["name"]   # the single user is seeded


def test_http_write_acks_and_rejects(tmp_path):
    with _client(tmp_path) as client:
        assert client.post("/api/project/create", json={"code": "ENG"}).json() == {"ok": True}
        bad = client.post("/api/project/create", json={"code": "toolong"})
        assert bad.status_code == 400
        assert "valid project code" in bad.json()["detail"]


def test_unknown_derived_dict_errors_on_socket(tmp_path):
    with _client(tmp_path) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"op": "subscribe", "sub_id": "s1", "derived_dict": "NOPE", "key_path": ""})
            frame = ws.receive_json()
            assert frame["op"] == "error"
