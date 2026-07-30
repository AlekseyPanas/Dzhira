"""Accounts, sessions, boards, and invites — the multi-user stores + the cross-store services."""

import pytest

from backend.db.paths import TASKS_DIR, board_dir
from backend.services import AppServices


@pytest.fixture
def services(tmp_path):
    return AppServices(tmp_path / "db")


# ------------------------------------------------------------------ accounts + sessions
def test_register_authenticate_and_case_insensitive_uniqueness(services):
    user = services.accounts.register("Bob", "hunter2")
    assert services.accounts.public(user) == {"id": user["id"], "username": "Bob", "color": user["color"]}
    assert "password" not in services.accounts.public(user)
    assert services.accounts.authenticate("bob", "hunter2")["id"] == user["id"]   # login case-insensitive
    assert services.accounts.authenticate("bob", "wrong") is None
    with pytest.raises(ValueError):
        services.accounts.register("BOB", "x")             # taken (case-insensitive)


def test_rename_and_change_password(services):
    user = services.accounts.register("Bob", "pw")
    services.accounts.change_password(user["id"], "pw", "pw2")
    assert services.accounts.authenticate("Bob", "pw2") is not None
    with pytest.raises(ValueError):
        services.accounts.change_password(user["id"], "wrong", "pw3")
    services.accounts.rename(user["id"], "Bobby")
    assert services.accounts.get_by_username("bobby")["id"] == user["id"]
    assert services.accounts.get_by_username("bob") is None


def test_sessions_roundtrip(services):
    user = services.accounts.register("Bob", "pw")
    sid = services.sessions.create(user["id"])
    assert services.user_for_session(sid)["id"] == user["id"]
    services.sessions.delete(sid)
    assert services.user_for_session(sid) is None
    assert services.user_for_session("../etc/passwd") is None      # tampered cookie is rejected


# ------------------------------------------------------------------ boards
def test_board_create_seeds_and_enforces_max_owned(services):
    owner = services.accounts.register("Owner", "pw")
    board = services.boards.create_board("Alpha", owner["id"])
    assert services.boards.resolve_by_name("alpha")["id"] == board["id"]   # name unique, case-insensitive
    # seeded content is present
    assert list((board_dir(services.root, board["id"]) / TASKS_DIR).glob("*.json"))
    services.boards.create_board("Beta", owner["id"])
    with pytest.raises(ValueError):
        services.boards.create_board("Gamma", owner["id"])            # max 2 owned
    with pytest.raises(ValueError):
        services.boards.create_board("ALPHA", owner["id"])            # duplicate name


def test_access_membership_transfer_and_kick(services):
    owner = services.accounts.register("Owner", "pw")
    member = services.accounts.register("Member", "pw")
    board = services.boards.create_board("Alpha", owner["id"])
    assert not services.boards.has_access(services.boards.get_board(board["id"]), member["id"])
    services.boards.add_member(board["id"], member["id"])
    assert services.boards.has_access(services.boards.get_board(board["id"]), member["id"])
    assert services.boards.role(services.boards.get_board(board["id"]), member["id"]) == "member"

    # transfer: member becomes owner, old owner becomes a member
    services.transfer(owner, board["id"], member["id"])
    b = services.boards.get_board(board["id"])
    assert b["owner_id"] == member["id"] and owner["id"] in b["members"]

    # kick strips the user from tasks too
    api = services.board_api(board["id"])
    project = "DZH"
    task_id = api.create_task(project, "t", assignees=[owner["id"]])
    services.kick(member, board["id"], owner["id"])         # member is now the owner
    from tests.conftest import load_json
    assert load_json(board_dir(services.root, board["id"]), TASKS_DIR, task_id)["assignees"] == []


def test_delete_board_removes_folder_and_invites(services):
    owner = services.accounts.register("Owner", "pw")
    invitee = services.accounts.register("Guest", "pw")
    board = services.boards.create_board("Alpha", owner["id"])
    services.create_invite(owner, board["id"], "Guest")
    assert services.invites_for_user(invitee)
    services.delete_board(owner, board["id"])
    assert services.boards.get_board(board["id"]) is None
    assert not services.invites_for_user(invitee)          # its invites were purged


# ------------------------------------------------------------------ invites
def test_invite_flow(services):
    owner = services.accounts.register("Owner", "pw")
    guest = services.accounts.register("Guest", "pw")
    board = services.boards.create_board("Alpha", owner["id"])

    services.create_invite(owner, board["id"], "guest")    # case-insensitive target
    with pytest.raises(ValueError):
        services.create_invite(owner, board["id"], "guest")            # already pending
    invites = services.invites_for_user(guest)
    assert len(invites) == 1 and invites[0]["board_name"] == "Alpha"

    services.accept_invite(guest, invites[0]["id"])
    assert services.boards.has_access(services.boards.get_board(board["id"]), guest["id"])
    assert not services.invites_for_user(guest)            # invite consumed


def test_shared_board_mirror_is_refcounted(services):
    owner = services.accounts.register("Owner", "pw")
    board = services.boards.create_board("Alpha", owner["id"])
    bid = board["id"]
    try:
        first = services.acquire_board_mirror(bid)
        second = services.acquire_board_mirror(bid)
        assert first is second                              # both sockets share ONE mirror
        assert services._board_mirrors[bid]["refs"] == 2
        services.release_board_mirror(bid)
        assert services._board_mirrors[bid]["refs"] == 1
        services.release_board_mirror(bid)
        assert bid not in services._board_mirrors           # dropped + watcher stopped on last release
    finally:
        services._board_mirrors.pop(bid, None)


def test_cannot_invite_self_or_existing_member(services):
    owner = services.accounts.register("Owner", "pw")
    board = services.boards.create_board("Alpha", owner["id"])
    with pytest.raises(ValueError):
        services.create_invite(owner, board["id"], "Owner")            # self
    with pytest.raises(ValueError):
        services.create_invite(owner, board["id"], "Ghost")            # no such user
