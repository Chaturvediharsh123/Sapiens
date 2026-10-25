from shop.cart import Cart
from shop.checkout import checkout


def test_culprit_repro():
    cart = Cart()
    cart.add("tea", 100)
    cart.apply_coupon("SAVE10")
    assert checkout(cart) == 106.2
