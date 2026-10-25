from shop.orders import paginate


def test_culprit_repro():
    items = list(range(25))
    assert paginate(items, 2, 10) == list(range(10, 20))
