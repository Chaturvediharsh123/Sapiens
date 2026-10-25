import importlib

import shop.pricing


def test_culprit_repro(monkeypatch):
    monkeypatch.setenv("SHOP_PAYMENT_TOKEN", "from-env")
    pricing = importlib.reload(shop.pricing)
    assert pricing.PAYMENT_API_TOKEN == "from-env"
