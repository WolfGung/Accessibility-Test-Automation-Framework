"""The checkout form: its fields, the countries it delivers to, and what counts as an error.

Every message says what to do rather than what went wrong, and makes sense on
its own, because it is read on its own: next to its field, as a link in the
summary at the top of the form, and by a screen reader when the field takes
focus.
"""
from __future__ import annotations

import re

#: The form's fields, in the order they appear on the page. All are required.
FIELDS: tuple[str, ...] = ("name", "email", "address", "city", "postcode", "country")

MISSING: dict[str, str] = {
    "name": "Enter your full name",
    "email": "Enter your email address",
    "address": "Enter your street address",
    "city": "Enter your town or city",
    "postcode": "Enter your postal code",
    "country": "Select your country",
}

EMAIL_FORMAT = "Enter an email address in the correct format, like name@example.com"

# Something, an @, a domain with a dot in it, and no spaces anywhere. Loose on
# purpose: whether an address works is only known by writing to it.
_EMAIL_SHAPE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

#: ISO 3166-1 codes (what `autocomplete="country"` fills in) and the names shown.
COUNTRIES: dict[str, str] = {
    "AT": "Austria",
    "BE": "Belgium",
    "CZ": "Czechia",
    "DK": "Denmark",
    "FI": "Finland",
    "FR": "France",
    "DE": "Germany",
    "IE": "Ireland",
    "IT": "Italy",
    "NL": "Netherlands",
    "PL": "Poland",
    "PT": "Portugal",
    "ES": "Spain",
    "SE": "Sweden",
}


def validate(values: dict[str, str]) -> dict[str, str]:
    """One message per field in error, in the order the fields appear on the form."""
    errors: dict[str, str] = {}
    for field in FIELDS:
        value = values.get(field, "")
        if not value:
            errors[field] = MISSING[field]
        elif field == "email" and not _EMAIL_SHAPE.fullmatch(value):
            errors[field] = EMAIL_FORMAT
        elif field == "country" and value not in COUNTRIES:
            errors[field] = MISSING["country"]
    return errors
