"""End-to-end boot over HTTP + websocket: register → create board → list → stream the board; auth is
enforced on the socket. Uses the in-process FastAPI TestClient."""

from fastapi.testclient import TestClient

from backend.app import create_app


def _client(tmp_path):
    return TestClient(create_app(db_folder=tmp_path / "db", serve_frontend_dist=False))


def _cookie_header(client):
    return {"cookie": f"dzhira_session={client.cookies.get('dzhira_session')}"}


def test_register_login_and_me(tmp_path):
    with _client(tmp_path) as client:
        assert client.get("/api/auth/me").json() == {"user": None}
        registered = client.post("/api/auth/register", json={"username": "Bob", "password": "pw"})
        assert registered.status_code == 200
        assert registered.json()["user"]["username"] == "Bob"
        assert client.get("/api/auth/me").json()["user"]["username"] == "Bob"   # cookie persists
        assert client.post("/api/auth/register", json={"username": "bob", "password": "x"}).status_code == 400


def test_create_board_and_stream_it_over_ws(tmp_path):
    with _client(tmp_path) as client:
        client.post("/api/auth/register", json={"username": "Bob", "password": "pw"})
        assert client.post("/api/boards/create", json={"name": "MyBoard"}).json() == {"name": "MyBoard"}
        boards = client.get("/api/boards").json()["boards"]
        assert boards[0]["name"] == "MyBoard" and boards[0]["role"] == "owner"

        with client.websocket_connect("/ws?board=MyBoard", headers=_cookie_header(client)) as ws:
            ws.send_json({"op": "subscribe", "sub_id": "s1", "key_path": ""})
            frame = ws.receive_json()
            assert frame["op"] == "subscribed"
            assert "columns" in frame["value"] and len(frame["value"]["columns"]) >= 1
            assert frame["value"]["board.json"]["name"] == "MyBoard"


def test_http_write_pushes_update_over_ws(tmp_path):
    # The crux of the production fix: an HTTP write must push over the websocket in-process, without
    # depending on the filesystem watcher firing.
    with _client(tmp_path) as client:
        client.post("/api/auth/register", json={"username": "Bob", "password": "pw"})
        client.post("/api/boards/create", json={"name": "MyBoard"})
        board_id = client.get("/api/boards").json()["boards"][0]["id"]
        with client.websocket_connect("/ws?board=MyBoard", headers=_cookie_header(client)) as ws:
            ws.send_json({"op": "subscribe", "sub_id": "s1", "key_path": "columns"})
            assert ws.receive_json()["op"] == "subscribed"
            assert client.post("/api/column/create",
                               json={"board_id": board_id, "name": "Later"}).json() == {"ok": True}
            frame = ws.receive_json()                        # arrives via the write-time poke
            assert frame["op"] == "update" and frame["key_path"].startswith("columns/")


def test_two_sockets_on_one_board_both_get_the_update(tmp_path):
    # The shared-mirror refactor: two connections to the same board share one mirror, and a single
    # write broadcasts to both.
    with _client(tmp_path) as client:
        client.post("/api/auth/register", json={"username": "Bob", "password": "pw"})
        client.post("/api/boards/create", json={"name": "MyBoard"})
        board_id = client.get("/api/boards").json()["boards"][0]["id"]
        headers = _cookie_header(client)
        with client.websocket_connect("/ws?board=MyBoard", headers=headers) as ws1, \
                client.websocket_connect("/ws?board=MyBoard", headers=headers) as ws2:
            for ws in (ws1, ws2):
                ws.send_json({"op": "subscribe", "sub_id": "s", "key_path": "columns"})
                assert ws.receive_json()["op"] == "subscribed"
            client.post("/api/column/create", json={"board_id": board_id, "name": "Shared"})
            assert ws1.receive_json()["op"] == "update"
            assert ws2.receive_json()["op"] == "update"


def test_ws_requires_auth_and_access(tmp_path):
    with _client(tmp_path) as client:
        # no cookie at all -> unauthorized
        with client.websocket_connect("/ws?board=Nope") as ws:
            assert ws.receive_json() == {"op": "error", "message": "unauthorized"}
        # logged in but board doesn't exist / no access -> no-access
        client.post("/api/auth/register", json={"username": "Bob", "password": "pw"})
        with client.websocket_connect("/ws?board=Ghost", headers=_cookie_header(client)) as ws:
            assert ws.receive_json() == {"op": "error", "message": "no-access"}


def test_board_content_write_requires_login_and_access(tmp_path):
    with _client(tmp_path) as client:
        # not logged in
        assert client.post("/api/column/create", json={"board_id": "brd_00000000", "name": "X"}).status_code == 401
        client.post("/api/auth/register", json={"username": "Bob", "password": "pw"})
        client.post("/api/boards/create", json={"name": "MyBoard"})
        board_id = client.get("/api/boards").json()["boards"][0]["id"]
        assert client.post("/api/column/create", json={"board_id": board_id, "name": "Later"}).json() == {"ok": True}
        # a board id we don't have access to -> 404 (no such board) / 403
        assert client.post("/api/column/create", json={"board_id": "brd_deadbeef", "name": "X"}).status_code == 404
