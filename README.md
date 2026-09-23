# Accessibility Test Automation Framework

A small shop in a broken and a fixed mode, and the checks that test its pages against WCAG 2.1 AA success criteria.

[![CI](https://github.com/WolfGung/Accessibility-Test-Automation-Framework/actions/workflows/ci.yml/badge.svg)](https://github.com/WolfGung/Accessibility-Test-Automation-Framework/actions/workflows/ci.yml)
[![live report](https://img.shields.io/badge/live%20report-GitHub%20Pages-brightgreen)](https://wolfgung.github.io/Accessibility-Test-Automation-Framework/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue)](pyproject.toml)
[![license: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

<!-- a11y:start -->
| Findings | Broken shop | Fixed shop |
| --- | ---: | ---: |
| Scan, critical | 8 | 0 |
| Scan, serious | 7 | 0 |
| Scan, moderate | 0 | 0 |
| Scan, minor | 0 | 0 |
| Keyboard, stops on the way to an order with the keyboard alone (2.1.1) | 1 | 0 |
| Keyboard, forms whose fields Tab reaches out of their order (2.4.3) | 1 | 0 |
| Keyboard, Tab stops with no visible focus (2.4.7) | 26 | 0 |
| Keyboard, dialogs Escape does not close, or closes without returning focus (2.1.2) | 1 | 0 |
| Keyboard, dialogs focus cannot leave (2.1.2) | 1 | 0 |

| Criterion | What is wrong in the broken shop | Found by |
| --- | --- | --- |
| 1.1.1 | Product images on the list have no text alternative | axe-core scan |
| 1.3.1, 4.1.2 | The email field has no label, only words above it | axe-core scan |
| 1.4.3 | The product page's price is light grey on white, 1.87:1 | axe-core scan |
| 2.1.1 | "Add to cart" on the product list works only with a mouse | keyboard checks |
| 2.1.2 | The "Added to cart" dialog cannot be left with the keyboard | keyboard checks |
| 2.4.3 | Tab reaches three checkout fields first, out of their visual order | keyboard checks |
| 2.4.7 | Links and buttons show no focus indicator | keyboard checks |
| 3.1.1 | Pages do not say what language they are in | axe-core scan |
| 3.3.1 | Checkout errors are shown only as a red border | manual checklist |
| 4.1.2 | The cart's remove control has no role and no name | manual checklist |
<!-- a11y:end -->

## What this shows

- **Checks that prove they catch what they claim.** Every check runs on both shops: the fixed one must come back clean, the broken one must show exactly the planted violations.
- **Two automated layers, and the line where they stop.** An axe-core scan of every page, keyboard checks driven by keys alone, and a checklist for what only a person can judge.
- **Numbers written by a run, not by hand.** The tables above are `results/a11y.json`, written by the suite and pinned by a test; a stale file fails CI.

## What automated checks cannot tell you

Of the ten planted violations, the scan finds four, the keyboard checks find four, and two are left to the manual checklist. Which layer finds which was not decided at a desk: `detected_by` in [`app/violations.py`](app/violations.py) was filled in from runs of the checks, and the suite requires each layer to report exactly its own entries, on their pages, so a change in what a layer finds fails the build.

The two that no automated layer reports:

- **Checkout errors shown only as a red border (3.3.1).** A coloured border is valid markup, and nothing automated here reads an error message and decides whether it says which field is wrong and what to enter.
- **The cart's remove control with no role and no name (4.1.2).** It takes focus, answers Enter and Space and keeps its focus outline, so the keyboard checks pass it. What it lacks is heard through a screen reader, and only there.

The scan runs the axe-core rules tagged for WCAG 2.1 level A and AA and no others, so its silence on a page means those rules found nothing there, not that the page is accessible. [`docs/manual-checklist.md`](docs/manual-checklist.md) holds the two violations above and the questions the automated layers do not ask at all: whether a text alternative says what the picture shows, what a screen reader announces on each page and after each step, how the pages hold up at 200% zoom and at 320 CSS px, and whether an error message helps. Each item says how to check and what counts as a failure.

## Adding these checks to your pipeline

The same work on your pages, described as work:

- **The scan and the keyboard checks in your CI**, run against the pages your users walk (a list, a product, a cart, a checkout, the dialogs on the way) on every push, in the browser the pipeline installs, the way [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs them here.
- **A report per run**: every finding with its rule, its success criterion, the element and where the rule is explained. The Allure report the live-report badge leads to is that report for this shop.
- **The manual checklist, done by hand** on the same pages, with a screen reader, at 200% zoom and at 320 CSS px, and written up in the same terms as the automated findings.
- **A list of findings mapped to success criteria**, with what was found, where, and by which layer, as the second table above lists them for the shop shipped here.

What that leaves is a page whose findings are known and listed against the criteria they bear on, and checks that fail the build when one comes back. Whether a page meets a standard is not something a scan decides, and this repository does not say it does.

## How to run

Python 3.12 and nothing else on the machine to run the suite: it starts the shops itself, and no test reaches the network.

```bash
make install    # the package with its dev extra, editable, and Playwright's Chromium
make test       # the whole suite: both shops, both layers, in one process
```

On Linux, `playwright install --with-deps chromium` also installs the browser's system packages, which takes root; `make install` installs the browser alone.

`make test` is `pytest`. It starts a fixed and a broken shop in threads of the test process, runs the HTTP tests against the fixed one, the markup tests against both, and the scan and the keyboard checks in Chromium against both, and at the end of a complete run writes `results/a11y.json`. A partial run, one module or a `-k` selection, writes nothing and says so in its summary.

```bash
python -m tools.report --readme           # print the tables the results file gives
python -m tools.report --update-readme    # write them between the markers in this README
pytest --alluredir=allure-results         # the same run, with every finding attached to the report
allure serve allure-results               # open that report (the Allure command line, which needs Java)
make app                                  # the fixed shop by hand, on http://127.0.0.1:8000
A11Y_MODE=broken make app                 # the broken one
make lint                                 # ruff
```

## Docker

Nothing on the machine but Docker:

```bash
docker compose up shop                     # the fixed shop on http://127.0.0.1:8000
A11Y_MODE=broken docker compose up shop    # the broken one
docker compose run --rm tests              # the whole suite, in a container built from this checkout
```

`shop` is Python 3.12 slim and the package, with `A11Y_MODE` passed through and `fixed` when it is not set. `tests` is Playwright's Python image, which ships the Chromium the checks drive, with this checkout copied in and the dev extra installed (its Dockerfile is written inside the compose file, which takes Docker Compose 2.17 or newer): the suite runs against shops of its own inside the container, so it needs nothing served to it, and the checkout on the host is not touched.

## How the repository is put together

- [`app/`](app/) is the shop: FastAPI and Jinja2, a product list, a product page with an "Added to cart" dialog, a cart and a checkout, carts kept in memory. `A11Y_MODE` picks `fixed` (the default) or `broken`; [`app/violations.py`](app/violations.py) is the one registry of the ten planted violations, each of them a single `{% if broken %}` branch in the templates, so the difference between the two modes is readable as one diff.
- [`a11y/axe.py`](a11y/axe.py) is the scan: axe-core 4.13.0, vendored in [`a11y/vendor/`](a11y/vendor/) and pinned by checksum, put into the page through Playwright and run with the WCAG 2.1 A and AA tags only. [`a11y/wcag.py`](a11y/wcag.py) reads success criteria out of its rule tags.
- [`a11y/keyboard.py`](a11y/keyboard.py) is the other layer: five checks (an order placed by keyboard, focus order, visible focus, Escape on the dialog, no trap in the dialog) that drive the browser with Tab, Shift+Tab, Enter, Space and Escape and return findings instead of asserting.
- [`tests/`](tests/) runs everything against a fixed and a broken shop started in the process ([`tests/conftest.py`](tests/conftest.py)), and writes [`results/a11y.json`](results/a11y.json) at the end of a complete run. [`tools/report.py`](tools/report.py) renders the tables at the top of this page from that file; [`tools/site.py`](tools/site.py) builds the published page from it.
- [`docs/manual-checklist.md`](docs/manual-checklist.md) is the third layer, done by hand.
- [`.github/workflows/ci.yml`](.github/workflows/ci.yml) lints, runs the suite with Chromium, fails when `results/a11y.json` differs from what the run wrote, and on `main` publishes the page and the Allure report to GitHub Pages.

The tests, counted by `pytest --collect-only` and pinned by [`tests/test_readme_pins.py`](tests/test_readme_pins.py):

| Module | What it proves | Tests |
| --- | --- | ---: |
| [`tests/test_app.py`](tests/test_app.py) | the shop over HTTP, without a browser: every page, the cart, the checkout and its errors, the mode switch | 61 |
| [`tests/test_markup.py`](tests/test_markup.py) | each planted violation is in the broken shop's markup and absent from the fixed one, and nothing else changes with the mode | 45 |
| [`tests/test_wcag.py`](tests/test_wcag.py) | success criteria read out of axe's rule tags | 25 |
| [`tests/test_vendor.py`](tests/test_vendor.py) | the vendored axe-core is 4.13.0 byte for byte, with its licence | 3 |
| [`tests/test_axe.py`](tests/test_axe.py) | the scan in Chromium: nothing serious on the fixed shop; on the broken one, each violation the registry says axe finds and nothing serious it does not explain | 22 |
| [`tests/test_keyboard.py`](tests/test_keyboard.py) | the keyboard checks in Chromium: clean on the fixed shop; on the broken one, each violation the registry says they find and nothing else | 31 |
| [`tests/test_report.py`](tests/test_report.py) | the results file, the tables, the published page (scanned with axe as the shop is) and the checklist | 33 |
| [`tests/test_readme_pins.py`](tests/test_readme_pins.py) | this README: the block, these counts, the registry's numbers, the links, the badges and the words | 12 |
| the whole suite, `make test` | all of the rows above, in one process, against shops it starts itself | 232 |

## Licence

MIT, see [`LICENSE`](LICENSE). axe-core is vendored unchanged under its own licence, the Mozilla Public License 2.0, in [`a11y/vendor/`](a11y/vendor/), with its version and checksum noted in [`a11y/vendor/README.md`](a11y/vendor/README.md).

## Related work

Five more repositories from the same portfolio:

- **[Toolshop-Test-Automation-Framework](https://github.com/WolfGung/Toolshop-Test-Automation-Framework)** — a test automation framework built from scratch for an online shop: API, browser and end-to-end cases against a public demo shop or a local Docker stand, with test design documents.
- **[Marketplace-Test-Automation-Framework](https://github.com/WolfGung/Marketplace-Test-Automation-Framework)** — API and browser tests for a marketplace shop, run against a small stand shipped in the repository with a nightly drift check of the public demo site, a smoke set, video and traces per browser test and a published Allure report.
- **[Web-Scraping-Automation-Framework](https://github.com/WolfGung/Web-Scraping-Automation-Framework)** — a scraper that collects two practice sites and a demo store of its own, over HTTP and through a browser, detects changes between nightly runs and publishes the data, the change report and the test report.
- **[Test-Suite-Rescue](https://github.com/WolfGung/Test-Suite-Rescue)** — a deliberately sick test suite, its cured version with the same coverage on Playwright and on Selenium, and the measured difference between them against the same application, reproducible with one command.
- **[API-Test-Generator](https://github.com/WolfGung/API-Test-Generator)** — a command-line tool that turns an OpenAPI document or a Postman collection into a runnable pytest suite, with four generated suites committed and proven against a sample API in CI.

## Hire me

I take short, well-defined jobs: a test automation framework from scratch, an API test suite for an existing backend, end-to-end tests for a critical flow, fixing flaky tests and reducing run time, setting up CI for existing tests, scrapers and data pipelines. Profile on Guru: [https://www.guru.com/freelancers/pavel-zhukov-atum](https://www.guru.com/freelancers/pavel-zhukov-atum). Time zone: Central European Time (CET/CEST), so my working hours overlap with Central European business hours. I work in writing.
