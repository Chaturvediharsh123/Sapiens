from shop.pricing import get_coupon


def test_culprit_repro():
    assert get_coupon("save10") == 10
