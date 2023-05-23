import uuid
from typing import Optional

from aiohttp.web import (
    HTTPFound,
    Request,
    RouteTableDef,
)
from aiohttp_jinja2 import render_template, template
import aiohttp_session
from discord.ext import vbu

from .utils.db_models import CheckoutItem, LoginUser, Purchase
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
        items = [
            CheckoutItem.from_row(row)
            for row in item_rows
        ]
        for i in items:
            await i.fetch_user(db)

        # Get the user's purchase history
        user = await LoginUser.fetch(db, id=session["id"])
        assert user
        item_ids = {i.id: i for i in items}
        current_items = [
            i for i in await Purchase.fetch_by_user(db, user)
            if i.product_id in item_ids
        ]
        for i in current_items:
            i._item = item_ids[i.product_id]

    # Get the prices for all available items
    for i in items:
        await i.fetch_price(request.app['config']['stripe_api_key'])

    # If there aren't any items then let's just redirect back to the index
    if not items:
        return HTTPFound("/")

    # Render the template
    return {
        "logged_in": session.get('id') is not None,
        "purchase_items": items,
        "current_items": current_items,
    }


@routes.get("/portal/item/{id}")
@requires_login()
async def purchase(request: Request):
    """
    Portal page for payments. This should show all items in the group.
    """

    # Make sure we have an ID
    product_id = request.match_info["id"]
    try:
        uuid.UUID(product_id)
    except ValueError:
        return HTTPFound("/")

    # Get session
    session = await aiohttp_session.get_session(request)

    # Get the items to be shown on the page
    async with vbu.Database() as db:
        item_rows = await db.call(
            """
            SELECT
                *
            FROM
                checkout_items
            WHERE
                id = $1
            """,
            product_id,
        )
        items = [
            CheckoutItem.from_row(row)
            for row in item_rows
        ]

        # If there aren't any items then let's just redirect back to
        # the index
        if not items:
            return HTTPFound("/")
        item = items[0]
        await item.fetch_user(db)

        # Make sure we have a guild ID if we need one
        guild_id_str = request.query.get("guild", "")
        if guild_id_str.isdigit():
            guild_id = int(guild_id_str)
        elif item.per_guild:
            return HTTPFound(f"/portal/{item.product_group}")
        else:
            guild_id = None

        # See if the user has purchased this item already - we'll use this to
        # redirect (if they can't buy multiple) or show an unsubscribe screen
        # (if it's a subscription)
        purchase: Optional[dict] = None
        if (item.subscription or not item.multiple) and "discord" in session:
            if item.per_guild:
                purchase_rows = await db.call(
                    """
                    SELECT
                        *
                    FROM
                        purchases
                    WHERE
                        discord_user_id = $1
                    AND
                        discord_guild_id = $2
                    AND
                        product_id = $3
                    AND
                        expiry_time IS NULL
                    """,
                    int(session['discord']['id']),
                    guild_id,
                    items[0].id,
                )
            else:
                purchase_rows = await db.call(
                    """
                    SELECT
                        *
                    FROM
                        purchases
                    WHERE
                        discord_user_id = $1
                    AND
                        discord_guild_id IS NULL
                    AND
                        product_id = $2
                    AND
                        expiry_time IS NULL
                    """,
                    int(session['discord']['id']),
                    items[0].id,
                )
            if purchase_rows:
                purchase = purchase_rows[0]

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
    # if flags.facebook and "facebook" not in session:
    #     session["login_message"] = "Facebook login is required."
    #     session["redirect_on_login"] = f"/portal/{item.product_group}"
    #     return HTTPFound("/login")

    # Get the item price if they're able to buy it more
    if not purchase:
        await item.fetch_price(request.app['config']['stripe_api_key'])

    # Render the template
    context = {
        "item": item,
        "user_id": session['id'],
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
