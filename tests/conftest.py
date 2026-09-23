"""Fixtures every test module shares: the running shops, the mode under test, and the steps to the pages; and the
results file, written at the end of a complete run.

One shop per mode runs for the whole session, served by uvicorn in a thread of
this process on a free port, and every test layer talks to it over HTTP: the
HTTP tests through a client of their own (`tests.helpers.client_for`), the
browser checks through Chromium, by way of pytest-playwright's `page`. A fresh
client or browser context per test means a cart of its own.
"""
from __future__ import annotations

import re
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
import uvicorn
from playwright.sync_api import Page, expect

from app.catalog import PRODUCTS
from app.main import MODES, create_app
from tests.helpers import FINDINGS, PAGE_OF, PAGES
from tools.report import COLUMNS, LAYERS, RESULTS, ROOT, Key, summarize, total_findings, write

MUG, NOTEBOOK = PRODUCTS[1], PRODUCTS[2]


# --- the shops -------------------------------------------------------------


def serve(mode: str) -> Iterator[str]:
    """A shop in this mode on a free port, in a thread, for as long as the generator is held; yields its base URL."""
    config = uvicorn.Config(
        create_app(mode), host="127.0.0.1", port=0, log_config=None, log_level="warning", access_log=False
    )
    listener = config.bind_socket()  # bound now, so the port is known before the thread starts; the server closes it
    port = listener.getsockname()[1]
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, name=f"shop-{mode}", daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        alive = thread.is_alive()
        if alive and time.monotonic() < deadline:
            time.sleep(0.01)
            continue
        server.should_exit = True  # should the thread still be on its way up
        listener.close()
        what = "did not start within 10 s" if alive else "exited before it was up"
        raise AssertionError(f"the {mode} shop on port {port} {what}")
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive(), f"the {mode} shop on port {port} did not stop"


@pytest.fixture(scope="session")
def fixed_shop() -> Iterator[str]:
    """The base URL of a shop in the fixed mode, up for the whole session."""
    yield from serve("fixed")


@pytest.fixture(scope="session")
def broken_shop() -> Iterator[str]:
    """The base URL of a shop in the broken mode, up for the whole session."""
    yield from serve("broken")


@pytest.fixture(params=MODES)
def mode(request: pytest.FixtureRequest) -> str:
    """Each mode in turn, for a test that runs against both shops."""
    return request.param


@pytest.fixture
def shop(mode: str, fixed_shop: str, broken_shop: str) -> str:
    """The base URL of the running shop in the mode under test."""
    return {"fixed": fixed_shop, "broken": broken_shop}[mode]


# --- the pages -------------------------------------------------------------


class Pages:
    """A browser page, and the steps a shopper takes on it to reach each page state of a shop."""

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


# --- the results file ------------------------------------------------------

#: Under this name a test module says what a complete run of it records (a set of `tools.report.Key`): every check
#: of its layer on every page state, for both shops. `tests/test_axe.py` and `tests/test_keyboard.py` do.
EXPECTED_RECORDS = "EXPECTED_RECORDS"


@dataclass
class Collector:
    """The session's view of the results file: what a complete run records, which tests record it, and the outcome.

    The file is written only from a complete run: every collected module that
    records findings has every one of its records in the ledger and nothing
    else is in it, both layers were collected, and none of the recording tests
    failed. A partial run — one module, a `-k` selection, a stop on a failure —
    writes nothing, and the last complete run's file stays; so does a run with a
    record no module declared (a module that attaches findings without
    `EXPECTED_RECORDS`, a mistyped state), which would otherwise be counted in
    without being required. The terminal summary says which it was.
    """

    expected: frozenset[Key] = frozenset()
    recording: frozenset[str] = frozenset()  # the node ids of the tests that record
    failed: set[str] = field(default_factory=set)
    outcome: str = ""

    def why_not(self, recorded: set[Key]) -> str | None:
        """Why this run is not one to write the file from; None when it is."""
        if absent := set(LAYERS) - {key.layer for key in self.expected}:
            layers = f"{' and '.join(sorted(absent))} layer{'s' if len(absent) > 1 else ''}"
            return f"the browser tests of the {layers} were not collected"
        if self.failed:
            return f"{len(self.failed)} of the {len(self.recording)} tests that record findings failed"
        if missing := self.expected - recorded:
            return f"{len(missing)} of {len(self.expected)} records are missing ({_named(missing)})"
        if extra := recorded - self.expected:
            return f"{len(extra)} record{'s' if len(extra) > 1 else ''} no module declared ({_named(extra)})"
        return None


def _named(keys: set[Key]) -> str:
    """Up to three of the records, in words, and how many more there are."""
    named = ", ".join(f"{key.check} on the {key.mode} shop's {key.state}" for key in sorted(keys)[:3])
    return named + (f" and {len(keys) - 3} more" if len(keys) > 3 else "")


COLLECTOR = Collector()


def pytest_collection_finish(session: pytest.Session) -> None:
    """Note what a complete run records, and which tests record it, from the modules that were collected."""
    expected: set[Key] = set()
    recording: set[str] = set()
    for item in session.items:
        keys = getattr(getattr(item, "module", None), EXPECTED_RECORDS, None)
        if keys:
            expected |= keys
            recording.add(item.nodeid)
    COLLECTOR.expected, COLLECTOR.recording = frozenset(expected), frozenset(recording)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.failed and report.nodeid in COLLECTOR.recording:
        COLLECTOR.failed.add(report.nodeid)


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Write the results file when this run was complete; either way, note what happened for the summary."""
    where = RESULTS.relative_to(ROOT)
    if reason := COLLECTOR.why_not(FINDINGS.keys()):
        COLLECTOR.outcome = f"{where} not written: {reason}"
        return
    data = summarize(FINDINGS.records.values())
    write(data)
    counts = ", ".join(f"{mode} shop {total_findings(data, mode)}" for mode in COLUMNS)
    COLLECTOR.outcome = f"{where} written from this run: {len(FINDINGS.records)} records; findings: {counts}"


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    terminalreporter.write_line(COLLECTOR.outcome)
