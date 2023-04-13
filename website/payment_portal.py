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

from .utils.db_models import CheckoutItem
from .utils.login import requires_login, _require_login_wrapper, requires_manager_login


routes = RouteTableDef()


@routes.get("/portal/manage")
@template("portal/manage.htm.j2")
@requires_manager_login()
async def portal_management(request: Request):
    """
    A management page for payment items.
    """

    session = await aiohttp_session.get_session(request)
    async with vbu.Database() as db:
        user_data_rows = await db.call(
            """
            SELECT
                id,
                manager,
                stripe_id,
                paypal_id,
                paypal_client_id,
                paypal_client_secret
            FROM
                payment_users
            WHERE
                login_id = $1
            """,
            session["id"],
        )
        user_data = user_data_rows[0]
        override = ""
        if user_data['manager']:
            override = "OR 1 = 1"
        items = await db.call(
            """
            SELECT
                id,
                product_name,
                subscription,
                success_url,
                cancel_url,
                required_logins,
                stripe_product_id,
                stripe_price_id,
                paypal_plan_id,
                -- transaction_webhook,
                -- transaction_webhook_authorization,
                product_group,
                per_guild,
                multiple,
                description
                -- quantity,
                -- min_quantity,
                -- max_quantity,
                -- base_product
            FROM
                checkout_items
            WHERE
                creator_id = $1
                {0}
            """.format(override),
            user_data["id"],
        )
    return {
        "user_data": user_data,
        "items": items,
    }


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
        current_subscriptions = []
        # if session.get("id") is not None:
        #     current_subscriptions = await db.call(
        #         """
        #         SELECT
        #             *
        #         FROM
        #             purchases
        #         WHERE
        #             product_id = ANY($1::UUID[])
        #             AND user_id = $2
        #             AND expiry_time IS NULL
        #         """,
        #         [i.id for i in items if i.subscription],
        #         session["id"],
        #     )
    for i in items:
        await i.fetch_price(request.app['config']['stripe_api_key'])

    # If there aren't any items then let's just redirect back to the index
    if not items:
        return HTTPFound("/")

    # Render the template
    return {
        "logged_in": session.get('id') is not None,
        "guild_items": [
            i
            for i in items
            if i.per_guild
        ],
        "user_items": [
            i
            for i in items
            if not i.per_guild
        ],
        "current_subscriptions": current_subscriptions,
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
                    type=dict,
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
                    type=dict,
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
    if flags.facebook and "facebook" not in session:
        session["login_message"] = "Facebook login is required."
        session["redirect_on_login"] = f"/portal/{item.product_group}"
        return HTTPFound("/login")
    if flags.everlasting and "everlasting" not in session:
        session["login_message"] = "Everlasting login is required."
        session["redirect_on_login"] = f"/portal/{item.product_group}"
        return HTTPFound("/login")

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
