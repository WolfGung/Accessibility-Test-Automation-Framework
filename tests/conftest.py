"""Fixtures every test module shares: the shops the browser checks run against, and the steps to their pages.

The HTTP tests make their own shop in-process (`tests.helpers.client_for`). The
browser checks drive Chromium, through pytest-playwright's `page`, against a shop
served by uvicorn in a thread of this process: one per mode, on a free port, up
for the whole session. Every test gets its own browser context, so its own cart.
"""
from __future__ import annotations

import asyncio
import re
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn
from playwright.sync_api import Page, expect

from app.catalog import PRODUCTS
from app.main import create_app

MUG, NOTEBOOK = PRODUCTS[1], PRODUCTS[2]


@pytest.fixture(autouse=True)
def _no_loop_marked_running(request: pytest.FixtureRequest) -> Iterator[None]:
    """An asyncio test starts with no loop marked as running on the thread, and leaves the mark as it found it.

    Playwright's sync API marks its own loop as the thread's running loop after
    every call and leaves the mark between calls, while that loop waits in its
    own greenlet. asyncio refuses to run a second loop on a thread so marked,
    so an asyncio test run after a browser test would fail before it started.
    The browser tests keep the mark: their loop is Playwright's.
    """
    if "anyio_backend" not in request.fixturenames:
        yield
        return
    marked = asyncio._get_running_loop()
    asyncio._set_running_loop(None)
    yield
    asyncio._set_running_loop(marked)

#: The page states the browser checks visit: every page, and the two states that change one (the product page
#: with its dialog open, the checkout after an empty submit).
PAGES = ("list", "product", "dialog", "cart", "checkout", "checkout-errors")

#: The page of the shop each state shows, as the registry of violations names pages.
PAGE_OF = {
    "list": "list",
    "product": "product",
    "dialog": "product",
    "cart": "cart",
    "checkout": "checkout",
    "checkout-errors": "checkout",
}


@pytest.fixture
def anyio_backend() -> str:
    """Async tests run on asyncio, as the shop does under uvicorn."""
    return "asyncio"


# --- the shops -------------------------------------------------------------


def serve(mode: str) -> Iterator[str]:
    """A shop in this mode on a free port, in a thread, for as long as the generator is held; yields its base URL."""
    config = uvicorn.Config(
        create_app(mode), host="127.0.0.1", port=0, log_config=None, log_level="warning", access_log=False
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name=f"shop-{mode}", daemon=True)
    thread.start()
    while not server.started:
        assert thread.is_alive(), f"the {mode} shop did not start"
        time.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="session")
def fixed_shop() -> Iterator[str]:
    """The base URL of a shop in the fixed mode, up for the whole session."""
    yield from serve("fixed")


@pytest.fixture(scope="session")
def broken_shop() -> Iterator[str]:
    """The base URL of a shop in the broken mode, up for the whole session."""
    yield from serve("broken")


# --- the pages -------------------------------------------------------------


class Pages:
    """A browser page, and the steps a shopper takes on it to reach each page state of a shop."""

    names = PAGES

    def __init__(self, page: Page) -> None:
        self.page = page

    @staticmethod
    def showing(shop_page: str) -> tuple[str, ...]:
        """The states that show this page of the shop, by the registry's name for it (`every page`: all of them)."""
        return tuple(state for state in PAGES if shop_page in (PAGE_OF[state], "every page"))

    def add_to_cart(self, shop: str, product_id: int) -> None:
        """On the product's page, use "Add to cart" and wait for the "Added to cart" dialog."""
        self.page.goto(f"{shop}/product/{product_id}")
        self.page.get_by_test_id("add-to-cart").click()
        expect(self.page.get_by_test_id("added-dialog")).to_be_visible()

    def visit(self, shop: str, state: str) -> Page:
        """Take the browser to this state of the shop at `shop`, by the steps a shopper takes; the page, once there."""
        page = self.page
        match state:
            case "list":
                page.goto(f"{shop}/")
            case "product":
                page.goto(f"{shop}/product/{MUG.id}")
            case "dialog":
                self.add_to_cart(shop, MUG.id)
            case "cart":
                self.add_to_cart(shop, NOTEBOOK.id)
                page.goto(f"{shop}/cart")
            case "checkout":
                self.add_to_cart(shop, NOTEBOOK.id)
                page.goto(f"{shop}/checkout")
            case "checkout-errors":
                self.add_to_cart(shop, NOTEBOOK.id)
                page.goto(f"{shop}/checkout")
                page.get_by_test_id("place-order").click()
                # Back with every field marked in error. In the broken mode the border is the one sign, so wait for it.
                field = page.get_by_test_id("checkout-name").locator("..")
                expect(field).to_have_class(re.compile(r"\bfield-with-error\b"))
            case _:
                raise ValueError(f"no such page state: {state!r}")
        return page


@pytest.fixture
def pages(page: Page) -> Pages:
    """The steps a shopper takes on this test's browser page: `pages.visit(shop, state)`."""
    return Pages(page)


@pytest.fixture(params=PAGES)
def state(request: pytest.FixtureRequest) -> str:
    """Each page state in turn, for a test that runs on every page."""
    return request.param
