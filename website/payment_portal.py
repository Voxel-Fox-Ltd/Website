import uuid
from typing import Optional
from datetime import datetime as dt

from aiohttp.web import (
    HTTPFound,
    Request,
    RouteTableDef,
)
from aiohttp_jinja2 import render_template, template
import aiohttp_session
from discord.ext import vbu

from .utils.db_models import CheckoutItem, User, Purchase
from .utils.login import requires_login, _require_login_wrapper


routes = RouteTableDef()


@routes.get("/portal/{group}")
@template("portal/index.htm.j2")
async def index(request: Request):
    """
    Portal page for payments. This should show all items in the group.
    """

    # See if we were redirected
    if "login" in request.query:
        if (x := await _require_login_wrapper(request)):
            return x
    session = await aiohttp_session.get_session(request)

    # Get the items to be shown on the page
    async with vbu.Database() as db:

        # Get the items from the database
        item_rows = await db.call(
            """
            SELECT
                *
            FROM
                checkout_items
            WHERE
                LOWER(product_group) = LOWER($1)
            """,
            request.match_info["group"],
        )
        available_items = [
            CheckoutItem.from_row(row)
            for row in item_rows
        ]

        # If there aren't any items then let's just redirect back to the index
        if not available_items:
            return HTTPFound("/")

        for i in available_items:
            await i.fetch_user(db)
        item_ids = {i.id: i for i in available_items}

        # Get the user's purchase history
        user_purchases: list[Purchase] | None = None  # Will be None for no login
        if "id" in session:
            user = await User.fetch(db, id=session["id"])
            assert user
            item_ids = {i.id: i for i in available_items}
            user_purchases = [
                i for i in await Purchase.fetch_by_user(db, user)
                if i.product_id in item_ids
            ]

    # Get the prices for all available items
    for i in available_items:
        await i.fetch_price(request.app['config']['stripe_api_key'])

    # Filter out stuff that's expired
    if user_purchases:
        user_purchases = [
            i for i in user_purchases
            if (
                i.expiry_time is None  # no expiry
                or i.expiry_time > dt.utcnow()  # expires in the future
            )
        ]

    # Add item objects to the purchases
    for i in (user_purchases or []):
        i._item = item_ids[i.product_id]
        if not i._item.multiple:
            try:
                available_items.remove(i._item)
            except ValueError:
                pass

    # Work out what we have unabailable
    unavailable_items: set[CheckoutItem] = set()
    for i in (user_purchases or []):
        assert i._item
        if i._item.multiple:
            continue
        if i._item.per_guild:
            continue
        for p in available_items:
            if p.base_product_id == i._item.base_product_id:
                unavailable_items.add(p)

    # Render the template
    v = {
        "logged_in": session.get("id") is not None,
        "available_items": available_items,
        "unavailable_items": unavailable_items,
        "user_purchases": user_purchases,
    }
    return v


@routes.get("/portal/item/{id}")
@requires_login()
async def purchase(request: Request):
    """
    Portal page for payments. This will show one particular item in the group.
    """

    # Make sure we have an ID
    product_id = request.match_info["id"]
    try:
        uuid.UUID(product_id)
    except ValueError:
        return HTTPFound("/")

    # Get session
    session = await aiohttp_session.get_session(request)

    # Get the item to be shown on the page
    async with vbu.Database() as db:
        item = await CheckoutItem.fetch(db, product_id)
        if not item:
            return HTTPFound("/")
        await item.fetch_user(db)

        # Make sure we have a guild ID if we need one
        guild_id_str = request.query.get("guild", "")
        if guild_id_str.isdigit():
            guild_id = int(guild_id_str)
        elif item.per_guild:
            return HTTPFound(f"/portal/{item.product_group}")
        else:
            guild_id = None

        # See if a purchase already exists for the given guild
        if guild_id:
            purchase_rows = await db.call(
                """SELECT * FROM purchases WHERE discord_guild_id = $1""",
                guild_id,
            )
            if purchase_rows:
                session["login_message"] = (
                    "{} has already been purchased for guild {}."
                    .format(item.name, guild_id)
                )
                session["redirect_on_login"] = f"/portal/{item.product_group}"
                return HTTPFound("/login")

        # Get a user
        user = await User.fetch(db, id=session["id"])
        assert user

        # See if the user has purchased this item already - we'll use this to
        # redirect (if they can't buy multiple) or redirect to unsubscribe
        # (if it's a subscription)
        purchase: Optional[Purchase] = None
        if (item.subscription or not item.multiple) and "discord" in session:
            if item.per_guild and guild_id:
                purchase_list = await Purchase.fetch_by_user(
                    db, None, item,
                    discord_guild_id=guild_id,
                )
            elif not item.per_guild:
                purchase_list = await Purchase.fetch_by_user(
                    db, user, item,
                )
            else:
                return HTTPFound(f"/portal/{item.product_group}")  # missing required guild ID
            if purchase_list:
                purchase = purchase_list[0]

    # See if we have relevant login data
    flags = item.required_logins
    if flags.discord and "discord" not in session:
        session["login_message"] = "Discord login is required."
        session["redirect_on_login"] = f"/portal/{item.product_group}"
        return HTTPFound("/login")
    if flags.google and "google" not in session:
        session["login_message"] = "Google login is required."
        session["redirect_on_login"] = f"/portal/{item.product_group}"
        return HTTPFound("/login")

    # Get the item price if they're able to buy it more
    if not purchase:
        await item.fetch_price(request.app['config']['stripe_api_key'])

    # Render the template
    context = {
        "item": item,
        "user_id": session["id"],
        "discord_guild_id": request.query.get("guild"),
        "purchase": purchase,
    }
    template_name = "portal/purchase.htm.j2"
    if purchase:
        if item.subscription:
            template_name = "portal/unsubscribe.htm.j2"
        elif not item.multiple:
            return HTTPFound(f"/portal/{item.product_group}")
        else:
            raise Exception("This shouldn't happen")
    return render_template(template_name, request, context)


@routes.get("/portal/unsubscribe/product/{id}")
@requires_login()
async def unsubscribe_product(request: Request):
    """
    Unsubscribe page for a user. Takes a product ID, redirects to the
    individual user's unsubscribe page by the purchase ID.
    """

    # Make sure we have an ID
    product_id = request.match_info["id"]
    try:
        uuid.UUID(product_id)
    except ValueError:
        return HTTPFound("/")

    # Get session
    session = await aiohttp_session.get_session(request)

    # Make sure we have a guild ID if we need one
    guild_id_str = request.query.get("guild", "")
    if guild_id_str.isdigit():
        guild_id = int(guild_id_str)
    else:
        guild_id = None

    # Get the items to be shown on the page
    async with vbu.Database() as db:

        # See if the user has purchased this item already - we'll use this to
        # redirect (if they can't buy multiple) or redirect to unsubscribe
        # (if it's a subscription)
        purchase: Optional[Purchase] = None
        if guild_id:
            purchase_rows = await db.call(
                """
                SELECT
                    *
                FROM
                    purchases
                WHERE
                    user_id = $1
                    AND discord_guild_id = $2
                    AND product_id = $3
                    AND expiry_time IS NULL
                """,
                session["id"],
                guild_id,
                product_id,
            )
        else:
            purchase_rows = await db.call(
                """
                SELECT
                    *
                FROM
                    purchases
                WHERE
                    user_id = $1
                    AND discord_guild_id IS NULL
                    AND product_id = $2
                    AND expiry_time IS NULL
                """,
                session["id"],
                product_id,
            )

    # Check if they purchased something
    if purchase_rows:
        purchase = Purchase.from_row(purchase_rows[0])

    # Get the item price if they're able to buy it more
    if not purchase:
        return HTTPFound(f"/portal/item/{product_id}")
    return HTTPFound(f"/portal/unsubscribe/{purchase.id}")


@routes.get("/portal/unsubscribe/{id}")
@template("portal/unsubscribe.htm.j2")
@requires_login()
async def unsubscribe(request: Request):
    """
    Unsubscribe page for a user via its purchase ID.
    """

    # Make sure we have an ID
    purchase_id = request.match_info["id"]
    try:
        uuid.UUID(purchase_id)
    except ValueError:
        return HTTPFound("/")

    # Get session
    session = await aiohttp_session.get_session(request)

    # Get the items to be shown on the page
    async with vbu.Database() as db:
        purchase: Optional[Purchase] = None
        purchase_rows = await db.call(
            """
            SELECT
                *
            FROM
                purchases
            WHERE
                user_id = $1
                AND id = $2
            """,
            session["id"],
            purchase_id,
        )

        # Check if they purchased something
        if purchase_rows:
            purchase = Purchase.from_row(purchase_rows[0])
        else:
            return HTTPFound("/")
        item = await purchase.fetch_product(db)

    # Render the template
    return {
        "item": item,
        "purchase": purchase,
    }
