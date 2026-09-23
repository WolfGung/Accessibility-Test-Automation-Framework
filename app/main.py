"""The shop: a product list, a product page with an "Added to cart" dialog, a cart and a checkout.

`A11Y_MODE` says how the pages are rendered and is read once, when the app is
created: `fixed` (the default) or `broken`. Templates see it as the boolean
`broken`. Any other value stops the shop from starting, with a message naming
the two it accepts. What `broken` changes is listed in `app.violations`.

A browser's cart is found through a signed cookie that holds only the cart's
id; the cart itself is kept in memory by `app.cart.CartStore`.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Annotated, Any, Literal

import jinja2
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import checkout
from app.cart import CartStore
from app.catalog import PRODUCTS, Product, format_price, get_product

HERE = Path(__file__).resolve().parent

MODES = ("fixed", "broken")

#: The most units of one product a single "Add to cart" accepts.
MAX_QUANTITY = 10

#: The one thing the session cookie holds: the id of this browser's cart.
CART_KEY = "cart"


def resolve_mode(mode: str | None = None) -> str:
    """The mode to run in: `mode` when given, else `A11Y_MODE`, else `fixed`."""
    if mode is None:
        mode = os.environ.get("A11Y_MODE", "fixed")
    if mode not in MODES:
        raise ValueError(f"A11Y_MODE must be 'fixed' or 'broken', not {mode!r}")
    return mode


def _templates(*, broken: bool) -> Jinja2Templates:
    # One environment per app: tests run a fixed and a broken shop side by side
    # in one process, and each must keep its own `broken`.
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(HERE / "templates"),
        autoescape=True,
        # A misspelt variable fails loudly instead of rendering as nothing:
        # an empty `alt` would quietly turn a product photo into decoration.
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["broken"] = broken
    env.filters["price"] = format_price
    return Jinja2Templates(env=env)


def create_app(mode: str | None = None) -> FastAPI:
    mode = resolve_mode(mode)
    templates = _templates(broken=mode == "broken")
    carts = CartStore()

    app = FastAPI(title="Example Shop", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.mode = mode
    app.state.templates = templates
    app.state.carts = carts
    # The key is made for this process only. The carts live in this process's
    # memory, so a cookie signed by an earlier run would point at nothing.
    app.add_middleware(
        SessionMiddleware,
        secret_key=secrets.token_urlsafe(32),
        session_cookie="shop_session",
        max_age=None,  # a browser-session cookie: the cart lasts as long as the browser does
        same_site="lax",
    )
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    def cart_id(request: Request) -> str | None:
        return request.session.get(CART_KEY)

    def ensure_cart_id(request: Request) -> str:
        """The browser's cart id, giving it one on its first "Add to cart"."""
        found = request.session.get(CART_KEY)
        if found is None:
            found = carts.new_id()
            request.session[CART_KEY] = found
        return found

    def product_or_404(product_id: int) -> Product:
        product = get_product(product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="No such product")
        return product

    def render(request: Request, template: str, context: dict[str, Any]) -> Response:
        context = {"cart_count": carts.count(cart_id(request)), **context}
        return templates.TemplateResponse(request, template, context)

    def checkout_form(request: Request, values: dict[str, str], errors: dict[str, str]) -> Response:
        found = cart_id(request)
        return render(
            request,
            "checkout.html",
            {
                "current_page": "checkout",
                "values": values,
                "errors": errors,
                "countries": checkout.COUNTRIES,
                "lines": carts.lines(found),
                "total_cents": carts.total_cents(found),
            },
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "mode": mode}

    @app.get("/", response_class=HTMLResponse)
    async def product_list(request: Request) -> Response:
        in_cart = {line.product.id: line.quantity for line in carts.lines(cart_id(request))}
        return render(request, "list.html", {"current_page": "list", "products": PRODUCTS, "in_cart": in_cart})

    @app.get("/product/{product_id}", response_class=HTMLResponse)
    async def product_page(request: Request, product_id: int, added: bool = False) -> Response:
        product = product_or_404(product_id)
        in_cart = carts.quantity(cart_id(request), product)
        context = {
            "current_page": "product",
            "product": product,
            "in_cart": in_cart,
            # `?added=1` comes from the redirect after "Add to cart", but on its
            # own it proves nothing: the dialog also needs the product to be in
            # the cart. shop.js drops the parameter from the address as soon as
            # the dialog opens, so a reload or coming Back does not reopen it.
            "added": added and in_cart > 0,
            "max_quantity": MAX_QUANTITY,
        }
        return render(request, "product.html", context)

    @app.post("/cart/add")
    async def cart_add(
        request: Request,
        product_id: Annotated[int, Form()],
        quantity: Annotated[int, Form(ge=1, le=MAX_QUANTITY)],
        return_to: Annotated[Literal["product", "list"], Form()] = "product",
    ) -> Response:
        product = product_or_404(product_id)
        carts.add(ensure_cart_id(request), product, quantity)
        if return_to == "list":
            # Back to the button that was used: the browser focuses the element
            # a fragment names, so a keyboard or screen reader user carries on
            # from there, and the button is now described by "In your cart: N".
            return RedirectResponse(f"/#add-to-cart-{product.id}", status_code=303)
        return RedirectResponse(f"/product/{product.id}?added=1", status_code=303)

    @app.post("/cart/remove")
    async def cart_remove(request: Request, product_id: Annotated[int, Form()]) -> Response:
        product = get_product(product_id)
        if product is not None and carts.remove(cart_id(request), product):
            # The cart page says what was removed and puts focus on that line.
            return RedirectResponse(f"/cart?removed={product.id}", status_code=303)
        return RedirectResponse("/cart", status_code=303)

    @app.get("/cart", response_class=HTMLResponse)
    async def cart_page(request: Request, removed: int | None = None) -> Response:
        found = cart_id(request)
        gone = get_product(removed) if removed is not None else None
        if gone is not None and carts.quantity(found, gone):
            gone = None  # it is back in the cart, so "was removed" would no longer be true
        context = {
            "current_page": "cart",
            "lines": carts.lines(found),
            "total_cents": carts.total_cents(found),
            "removed": gone,
        }
        return render(request, "cart.html", context)

    @app.get("/checkout", response_class=HTMLResponse)
    async def checkout_page(request: Request) -> Response:
        return checkout_form(request, values=dict.fromkeys(checkout.FIELDS, ""), errors={})

    @app.post("/checkout")
    async def checkout_submit(request: Request) -> Response:
        form = await request.form()
        values = {field: str(form.get(field, "")).strip() for field in checkout.FIELDS}
        errors = checkout.validate(values)
        if errors:
            # 200, as a server-rendered form does: a 4xx here would make the
            # browser log an error for what is an ordinary step in the flow.
            return checkout_form(request, values, errors)
        found = cart_id(request)
        if found is None or not carts.lines(found):
            # The details are fine; there is just nothing to order yet.
            return RedirectResponse("/cart", status_code=303)
        carts.place_order(found, values)
        return RedirectResponse("/confirmation", status_code=303)

    @app.get("/confirmation", response_class=HTMLResponse)
    async def confirmation(request: Request) -> Response:
        order = carts.last_order(cart_id(request))
        if order is None:
            return RedirectResponse("/", status_code=303)
        context = {
            "current_page": "confirmation",
            "order": order,
            "country": checkout.COUNTRIES[order.details["country"]],
        }
        return render(request, "confirmation.html", context)

    return app


app = create_app()
