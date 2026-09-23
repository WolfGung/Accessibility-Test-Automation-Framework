"""Carts kept in memory, one per browser session, and the orders they turn into.

The browser holds nothing but a signed cookie with its cart's id (see
`app.main`); the lines, the totals and the last order live here, in the
process. Restarting the shop empties every cart, which suits a shop that exists
to be tested.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from app.catalog import Product


@dataclass(frozen=True)
class CartLine:
    product: Product
    quantity: int

    @property
    def subtotal_cents(self) -> int:
        return self.product.price_cents * self.quantity


@dataclass(frozen=True)
class Order:
    lines: tuple[CartLine, ...]
    details: dict[str, str]  # the checkout form's fields, as submitted

    @property
    def total_cents(self) -> int:
        return sum(line.subtotal_cents for line in self.lines)


class CartStore:
    """Every cart and every last order of one running shop, keyed by cart id."""

    def __init__(self) -> None:
        self._carts: dict[str, dict[Product, int]] = {}
        self._orders: dict[str, Order] = {}

    @staticmethod
    def new_id() -> str:
        return secrets.token_urlsafe(16)

    def add(self, cart_id: str, product: Product, quantity: int) -> None:
        cart = self._carts.setdefault(cart_id, {})
        cart[product] = cart.get(product, 0) + quantity

    def remove(self, cart_id: str | None, product: Product) -> None:
        self._carts.get(cart_id or "", {}).pop(product, None)

    def lines(self, cart_id: str | None) -> list[CartLine]:
        """The cart's lines in the order their products were first added."""
        cart = self._carts.get(cart_id or "", {})
        return [CartLine(product, quantity) for product, quantity in cart.items()]

    def quantity(self, cart_id: str | None, product: Product) -> int:
        return self._carts.get(cart_id or "", {}).get(product, 0)

    def count(self, cart_id: str | None) -> int:
        """How many items the cart holds, counting each unit."""
        return sum(self._carts.get(cart_id or "", {}).values())

    def total_cents(self, cart_id: str | None) -> int:
        return sum(line.subtotal_cents for line in self.lines(cart_id))

    def place_order(self, cart_id: str, details: dict[str, str]) -> Order:
        """Turn the cart into an order and empty it."""
        order = Order(lines=tuple(self.lines(cart_id)), details=dict(details))
        self._orders[cart_id] = order
        self._carts.pop(cart_id, None)
        return order

    def last_order(self, cart_id: str | None) -> Order | None:
        return self._orders.get(cart_id or "")
