"""The demo repo: a tiny Python shop app with 30 commits and 7 planted bugs.

Used by `culprit demo` and by the benchmark. Commit dates, authors and contents are
fixed, so the commit shas are identical on every machine.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path


AUTHORS = {
    "Rahul": "rahul@demo.shop",
    "Priya": "priya@demo.shop",
    "Aman": "aman@demo.shop",
    "Sneha": "sneha@demo.shop",
    "Karan": "karan@demo.shop",
}

# ---------------------------------------------------------------- file versions

README_V1 = """# demo-shop

A tiny shop backend used to demo Culprit.
"""

INIT_V1 = '"""Tiny shop app used as the Culprit demo repo."""\n'

STRINGS_V1 = '''def normalize(text):
    """Trim and collapse inner whitespace."""
    return " ".join(text.split())
'''

USERS_V1 = '''import re

from shop.strings import normalize


def validate_email(email):
    """Return True if the email address looks valid."""
    pattern = r"^[\\w.+-]+@[\\w-]+\\.[\\w.-]+$"
    return bool(re.match(pattern, normalize(email)))


def register(email, name):
    """Create a user record after validating the email."""
    if not validate_email(email):
        raise ValueError(f"invalid email: {email}")
    return {"email": normalize(email).lower(), "name": normalize(name)}
'''

PRICING_V1 = '''import os

TAX_RATE = 0.18
COUPONS = {"SAVE10": 10, "FEST20": 20}
PAYMENT_API_TOKEN = os.environ.get("SHOP_PAYMENT_TOKEN", "")


def apply_discount(amount, percent):
    """Return amount after a percentage discount."""
    return round(amount * (100 - percent) / 100, 2)


def get_coupon(code):
    """Return the discount percent for a coupon code, or 0."""
    return COUPONS.get(code.strip().upper(), 0)


def tax_for_lines(line_totals):
    """Tax on a list of line totals, rounded once on the total."""
    return round(sum(line_totals) * TAX_RATE, 2)
'''

CART_V1 = '''from shop.pricing import apply_discount, get_coupon


class Cart:
    def __init__(self):
        self.lines = []
        self.coupon_percent = 0

    def add(self, name, price, qty=1):
        self.lines.append({"name": name, "price": price, "qty": qty})

    def line_totals(self):
        return [line["price"] * line["qty"] for line in self.lines]

    def subtotal(self):
        return round(sum(self.line_totals()), 2)

    def apply_coupon(self, code):
        self.coupon_percent = get_coupon(code)

    def total(self):
        """Subtotal after the coupon discount (before tax)."""
        return apply_discount(self.subtotal(), self.coupon_percent)
'''

CHECKOUT_V1 = '''from shop.pricing import TAX_RATE


def checkout(cart):
    """Final amount to charge: discounted total plus tax."""
    amount = cart.total()
    tax = round(amount * TAX_RATE, 2)
    return round(amount + tax, 2)
'''

ORDERS_V1 = '''def paginate(items, page, per_page=10):
    """Return the items on a 1-based page."""
    start = (page - 1) * per_page
    return items[start:start + per_page]
'''

DB_V1 = '''import sqlite3


def connect(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)"
    )
    return conn


def add_user(conn, username, password):
    conn.execute("INSERT INTO users VALUES (?, ?)", (username, password))


def check_login(conn, username, password):
    """True only if the username and password match a stored user."""
    row = conn.execute(
        "SELECT 1 FROM users WHERE username = ? AND password = ?",
        (username, password),
    ).fetchone()
    return row is not None
'''

TESTS_V1 = '''from shop.cart import Cart
from shop.checkout import checkout
from shop.db import add_user, check_login, connect
from shop.orders import paginate
from shop.pricing import get_coupon, tax_for_lines
from shop.users import validate_email


def test_valid_email():
    assert validate_email("asha@example.com")
    assert not validate_email("not-an-email")


def test_checkout_without_coupon():
    cart = Cart()
    cart.add("tea", 100)
    assert checkout(cart) == 118.0


def test_first_page():
    assert paginate(list(range(25)), 1, 10) == list(range(10))


def test_coupon_lookup():
    assert get_coupon("SAVE10") == 10
    assert get_coupon("NOPE") == 0


def test_tax_single_line():
    assert tax_for_lines([100]) == 18.0


def test_login():
    conn = connect()
    add_user(conn, "alice", "s3cret")
    assert check_login(conn, "alice", "s3cret")
    assert not check_login(conn, "alice", "wrong")
'''


def edit(old: str, new: str):
    """Return a function that replaces `old` with `new` exactly once."""

    def apply(text: str) -> str:
        if text.count(old) != 1:
            raise SystemExit(f"demo edit failed, expected one match for:\n{old}")
        return text.replace(old, new)

    return apply


def append(extra: str):
    return lambda text: text + extra


# Each commit: (author, message, {path: new content or edit function}, bug id or None)
COMMITS = [
    ("Rahul", "Initial project skeleton",
     {"README.md": README_V1, "shop/__init__.py": INIT_V1, "shop/strings.py": STRINGS_V1}, None),
    ("Priya", "Add user registration with email validation", {"shop/users.py": USERS_V1}, None),
    ("Aman", "Add pricing helpers and coupons", {"shop/pricing.py": PRICING_V1}, None),
    ("Sneha", "Add shopping cart", {"shop/cart.py": CART_V1}, None),
    ("Karan", "Add checkout", {"shop/checkout.py": CHECKOUT_V1}, None),
    ("Rahul", "Add order pagination", {"shop/orders.py": ORDERS_V1}, None),
    ("Priya", "Add sqlite user store and login", {"shop/db.py": DB_V1}, None),
    ("Aman", "Add basic tests", {"tests/test_basic.py": TESTS_V1}, None),
    ("Sneha", "Docs: explain coupons in README",
     {"README.md": append("\n## Coupons\n\nSAVE10 gives 10% off, FEST20 gives 20% off.\n")}, None),
    ("Karan", "Add slugify helper", {"shop/strings.py": append('''

def slugify(text):
    """Lowercase words joined by hyphens."""
    return "-".join(normalize(text).lower().split())
''')}, None),
    # BUG 1: '+' removed from the allowed characters
    ("Rahul", "Clean up email validation pattern", {"shop/users.py": edit(
        'pattern = r"^[\\w.+-]+@[\\w-]+\\.[\\w.-]+$"',
        'pattern = r"^[\\w.-]+@[\\w-]+\\.[\\w.-]+$"')}, "email_plus"),
    ("Priya", "Add requirements file", {"requirements.txt": "pytest\n"}, None),
    ("Aman", "Add order summary helper", {"shop/orders.py": append('''

def summarize(items):
    """Short text summary of an order list."""
    return f"{len(items)} orders"
''')}, None),
    # BUG 3: off-by-one in the page start
    ("Sneha", "Fix pagination edge case for first page", {"shop/orders.py": edit(
        "start = (page - 1) * per_page\n",
        "start = max((page - 1) * per_page - 1, 0)\n")}, "pagination_repeat"),
    ("Karan", "Add test for slugify", {"tests/test_strings.py": '''from shop.strings import slugify


def test_slugify():
    assert slugify("  Masala  Chai ") == "masala-chai"
'''}, None),
    ("Rahul", "Document normalize behaviour", {"shop/strings.py": edit(
        '"""Trim and collapse inner whitespace."""',
        '"""Trim the text and collapse runs of inner whitespace to one space."""')}, None),
    # BUG 2: discount applied again on an already-discounted total
    ("Priya", "Apply coupon discount at checkout", {"shop/checkout.py": edit(
        "from shop.pricing import TAX_RATE\n",
        "from shop.pricing import TAX_RATE, apply_discount\n"), }, None),
    ("Aman", "Add CONTRIBUTING.md", {"CONTRIBUTING.md": "# Contributing\n\nRun `pytest` before opening a PR.\n"}, None),
    ("Sneha", "Add invoice builder", {"shop/checkout.py": append('''

def invoice(cart):
    """Line totals and tax for printing an invoice."""
    lines = cart.line_totals()
    return {"lines": lines, "tax": tax_for_lines(lines)}
'''), }, None),
    # BUG 4: tax rounded per line instead of once on the total
    ("Karan", "Round tax per line so invoices match line items", {"shop/pricing.py": edit(
        "    return round(sum(line_totals) * TAX_RATE, 2)\n",
        "    return round(sum(round(t * TAX_RATE, 2) for t in line_totals), 2)\n")}, "tax_rounding"),
    ("Rahul", "Add .gitignore", {".gitignore": "__pycache__/\n*.pyc\n.pytest_cache/\n"}, None),
    ("Priya", "Add display name helper", {"shop/users.py": append('''

def display_name(user):
    """Name to show in the header."""
    return user["name"] or user["email"].split("@")[0]
''')}, None),
    # BUG 5: coupon lookup became case-sensitive
    ("Aman", "Simplify coupon lookup", {"shop/pricing.py": edit(
        "return COUPONS.get(code.strip().upper(), 0)",
        "return COUPONS.get(code.strip(), 0)")}, "coupon_case"),
    ("Sneha", "README: setup steps", {"README.md": append("\n## Setup\n\n```\npip install -r requirements.txt\npytest\n```\n")}, None),
    # BUG 6 (security): SQL built with an f-string -> login bypass
    ("Karan", "Inline login query for readability", {"shop/db.py": edit(
        '''    row = conn.execute(
        "SELECT 1 FROM users WHERE username = ? AND password = ?",
        (username, password),
    ).fetchone()
''',
        '''    query = f"SELECT 1 FROM users WHERE username = '{username}' AND password = '{password}'"
    row = conn.execute(query).fetchone()
''')}, "sql_login_bypass"),
    ("Rahul", "Add delete_user to db", {"shop/db.py": append('''

def delete_user(conn, username):
    conn.execute("DELETE FROM users WHERE username = ?", (username,))
''')}, None),
    ("Priya", "Add test for order summary", {"tests/test_orders.py": '''from shop.orders import summarize


def test_summarize():
    assert summarize([1, 2, 3]) == "3 orders"
'''}, None),
    # BUG 7 (security): token hardcoded instead of read from the environment
    ("Aman", "Hardcode payment token for local testing", {"shop/pricing.py": edit(
        'PAYMENT_API_TOKEN = os.environ.get("SHOP_PAYMENT_TOKEN", "")',
        'PAYMENT_API_TOKEN = "demo-token-not-real-1234"')}, "hardcoded_token"),
    ("Sneha", "Bump version to 0.3.0", {"shop/__init__.py": append('\n__version__ = "0.3.0"\n')}, None),
    ("Karan", "README: troubleshooting section",
     {"README.md": append("\n## Troubleshooting\n\nIf tests fail, check your Python version (3.10+).\n")}, None),
]

# The checkout bug needs two edits in one commit; patch it in here to keep the table readable.
_bug2_files = COMMITS[16][2]
_import_edit = _bug2_files["shop/checkout.py"]
_body_edit = edit("    amount = cart.total()\n",
                  "    amount = cart.total()\n    amount = apply_discount(amount, cart.coupon_percent)\n")
COMMITS[16] = (COMMITS[16][0], COMMITS[16][1],
               {"shop/checkout.py": lambda t: _body_edit(_import_edit(t))}, "discount_twice")
# invoice() needs tax_for_lines imported
_inv_files = COMMITS[18][2]
_inv_append = _inv_files["shop/checkout.py"]
_inv_import = edit("from shop.pricing import TAX_RATE, apply_discount\n",
                   "from shop.pricing import TAX_RATE, apply_discount, tax_for_lines\n")
COMMITS[18] = (COMMITS[18][0], COMMITS[18][1],
               {"shop/checkout.py": lambda t: _inv_append(_inv_import(t))}, None)

BUGS = {
    "email_plus": {
        "mode": "normal",
        "report": "Signup rejects valid emails that contain a + sign, for example asha+shop@example.com",
    },
    "discount_twice": {
        "mode": "normal",
        "report": "Coupon discount is applied twice at checkout: a 100 rupee cart with SAVE10 should cost 106.2 with tax",
    },
    "pagination_repeat": {
        "mode": "normal",
        "report": "Order list pagination is broken: page 2 repeats the last item of page 1",
    },
    "tax_rounding": {
        "mode": "normal",
        "report": "Tax total is off by 1 paisa on invoices with many small items, e.g. three items of 0.03 should have tax 0.02",
    },
    "coupon_case": {
        "mode": "normal",
        "report": "Coupon code SAVE10 stops working when the customer types it in lowercase (save10)",
    },
    "sql_login_bypass": {
        "mode": "security",
        "report": "Login succeeds with a wrong password that contains a quote, like x' OR '1'='1",
    },
    "hardcoded_token": {
        "mode": "security",
        "report": "The payment API token is hardcoded in the source code instead of being read from the SHOP_PAYMENT_TOKEN environment variable",
    },
}

ALIASES = {
    "email": "email_plus", "discount": "discount_twice", "pagination": "pagination_repeat",
    "tax": "tax_rounding", "coupon": "coupon_case", "login": "sql_login_bypass", "token": "hardcoded_token",
}
SHORT = {v: k for k, v in ALIASES.items()}

GOOD_COMMIT_INDEX = 7  # "Add basic tests": every feature exists, no bug planted yet


def git(repo: Path, *args: str, env: dict | None = None) -> str:
    out = subprocess.run(["git", *args], cwd=repo, env=env, check=True,
                         capture_output=True, text=True)
    return out.stdout.strip()


def _force_remove(func, path, _exc):
    """Windows: git object files are read-only; clear the flag and retry."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def build(target: Path) -> dict:
    if target.exists():
        shutil.rmtree(target, onerror=_force_remove)
    target.mkdir(parents=True)
    git(target, "init", "-q", "-b", "main")
    git(target, "config", "user.name", "demo")
    git(target, "config", "user.email", "demo@demo.shop")
    git(target, "config", "commit.gpgsign", "false")

    files: dict[str, str] = {}
    shas: list[str] = []
    culprits: dict[str, dict] = {}
    for i, (author, message, changes, bug) in enumerate(COMMITS):
        for path, change in changes.items():
            new = change(files.get(path, "")) if callable(change) else change
            files[path] = new
            p = target / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(new, newline="\n")   # same bytes (and shas) on Windows
        git(target, "add", "-A")
        date = f"2026-10-{1 + i // 3:02d}T{10 + (i % 3) * 3:02d}:00:00+05:30"
        env = {**os.environ,
               "GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": AUTHORS[author],
               "GIT_COMMITTER_NAME": author, "GIT_COMMITTER_EMAIL": AUTHORS[author],
               "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        git(target, "commit", "-q", "-m", message, env=env)
        sha = git(target, "rev-parse", "HEAD")
        shas.append(sha)
        if bug:
            culprits[bug] = {"sha": sha, "message": message, "author": author}
    return {"shas": shas, "culprits": culprits}


def write_bugs_yaml(info: dict, path: Path) -> None:
    good = info["shas"][GOOD_COMMIT_INDEX]
    lines = ["# Generated by demo/make_demo_repo.py - shas are deterministic.", "bugs:"]
    for bug_id, meta in BUGS.items():
        c = info["culprits"][bug_id]
        report = meta["report"].replace('"', '\\"')
        lines += [
            f"  - id: {bug_id}",
            f"    mode: {meta['mode']}",
            f'    report: "{report}"',
            f"    good: {good}",
            f"    culprit: {c['sha']}",
            f'    culprit_message: "{c["message"]}"',
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", newline="\n")
