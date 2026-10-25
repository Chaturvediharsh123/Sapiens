from shop.db import add_user, check_login, connect


def test_culprit_repro():
    conn = connect()
    add_user(conn, "alice", "s3cret")
    assert not check_login(conn, "alice", "x' OR '1'='1")
