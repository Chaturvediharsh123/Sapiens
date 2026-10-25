from shop.users import validate_email


def test_culprit_repro():
    assert validate_email("asha+shop@example.com")
