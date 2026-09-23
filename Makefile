.PHONY: install test app lint

PYTHON ?= python3

# The shop's mode and port for `make app`: A11Y_MODE=broken make app
A11Y_MODE ?= fixed
APP_PORT ?= 8000

install:
	$(PYTHON) -m pip install -e ".[dev]"
	$(PYTHON) -m playwright install chromium

# Everything runs in-process against the shop the tests start themselves.
test:
	$(PYTHON) -m pytest

# The shop by hand, on http://127.0.0.1:$(APP_PORT)
app:
	A11Y_MODE=$(A11Y_MODE) $(PYTHON) -m uvicorn app.main:app --port $(APP_PORT)

lint:
	$(PYTHON) -m ruff check .
