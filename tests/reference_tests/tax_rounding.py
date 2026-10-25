from shop.pricing import tax_for_lines


def test_culprit_repro():
    assert tax_for_lines([0.03, 0.03, 0.03]) == 0.02
