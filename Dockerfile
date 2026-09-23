# The shop, for `docker compose up shop`: Python 3.12 and the package, nothing
# else. The mode comes from `A11Y_MODE` at run time (fixed or broken); the
# compose file passes it through and defaults it to fixed.
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY a11y ./a11y
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
