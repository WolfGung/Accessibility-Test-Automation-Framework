"""The six products the shop sells, and how a price is written.

Each image has an `alt` that says what the picture shows rather than repeating
the product's name: the name is already printed next to it, and the picture is
where a sighted shopper learns the colour and the shape.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    price_cents: int
    image: str  # a file in app/static/img
    alt: str
    description: str


PRODUCTS: tuple[Product, ...] = (
    Product(
        id=1,
        name="Canvas tote bag",
        price_cents=1800,
        image="tote-bag.svg",
        alt="Natural canvas tote bag with two long black handles",
        description=(
            "Heavy cotton canvas with a pocket inside. Big enough for a laptop and a lunch, "
            "or for a week of groceries."
        ),
    ),
    Product(
        id=2,
        name="Ceramic mug",
        price_cents=1250,
        image="mug.svg",
        alt="White ceramic mug with a dark blue rim and handle",
        description="A 350 ml stoneware mug, glazed inside and out. Safe in the dishwasher and the microwave.",
    ),
    Product(
        id=3,
        name="Dotted notebook",
        price_cents=990,
        image="notebook.svg",
        alt="Dark green notebook held shut by a black elastic band",
        description=(
            "A5, 192 pages of 100 g/m² paper with a 5 mm dot grid, a ribbon marker "
            "and a pocket inside the back cover."
        ),
    ),
    Product(
        id=4,
        name="Pencil set",
        price_cents=700,
        image="pencils.svg",
        alt="Three sharpened pencils: yellow, red and blue",
        description="Three HB pencils in cedar wood, sharpened and ready to use. Each one is a different colour.",
    ),
    Product(
        id=5,
        name="Desk lamp",
        price_cents=4200,
        image="desk-lamp.svg",
        alt="Black desk lamp with a jointed arm and a round base",
        description="An LED lamp with a two-joint arm and a warm light that dims in three steps.",
    ),
    Product(
        id=6,
        name="Water bottle",
        price_cents=2400,
        image="water-bottle.svg",
        alt="Brushed steel water bottle with a bamboo cap",
        description="750 ml, double-walled, keeps a drink cold for a day. The cap is bamboo.",
    ),
)

_BY_ID = {product.id: product for product in PRODUCTS}


def get_product(product_id: int) -> Product | None:
    return _BY_ID.get(product_id)


def format_price(cents: int) -> str:
    """`4590` → `€45.90`. Prices are whole cents, so a total is an exact sum."""
    euros, rest = divmod(cents, 100)
    return f"€{euros:,}.{rest:02d}"
