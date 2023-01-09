from typing import Optional
from aiohttp.web import HTTPFound, Request, RouteTableDef, json_response
from aiohttp_jinja2 import render_template, template
import aiohttp_session
from discord.ext import vbu
import aiohttp

from .utils.db_util import CheckoutItem


routes = RouteTableDef()


@routes.get("/api/portal/get_guilds")
async def portal_get_guilds(request: Request):
    """
    Return a collection of guild IDs and names for the currently logged
    in user.
    """

    # Get session
    user_session = await aiohttp_session.get_session(request)
    access_token = user_session.get("token_info", dict()).get("access_token")
    if not access_token:
        return json_response([])

    # Get the guilds
    async with aiohttp.ClientSession() as session:
        resp = await session.get(
            "https://discord.com/api/users/@me/guilds",
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        )
        if not resp.ok:
            return json_response([])
        guilds = await resp.json()


    # Return the guilds
    return json_response(
        [
            {
                "id": g['id'],
                "name": g['name'],
            }
            for g in guilds
        ],
    )


@routes.post("/api/portal/unsubscribe")
async def portal_unsubscribe(request: Request):
    """
    Unsubscribe a currently subscribed user from an active subscription.
    """

    # Get session
    user_session = await aiohttp_session.get_session(request)

    # See what the user is unsubscribing from
    try:
        data = await request.json()
    except Exception:
        return json_response(
            {"error": "Invalid data.", "success": False},
            status=400,
        )
    purchase_id = data.get("id", "")

    # Get their current subscription
    async with vbu.Database() as db:
        purchase_rows = await db.call(
            """
            SELECT
                *
            FROM
                purchases
            WHERE
                id = $1
            AND
                user_id = $2
            AND
                expiry_time IS NULL
            AND
                cancel_url IS NOT NULL
            """,
            purchase_id,
            user_session.get("user_id"),
            type=dict,
        )
        if purchase_rows:
            purchased = purchase_rows[0]
        else:
            return json_response(
                {"error": "No active subscription found.", "success": False},
                status=400,
            )

    # Get the right auth and url
    auth: Optional[aiohttp.BasicAuth] = None
    method: str = ""
    if "paypal.com" in purchased['cancel_url'].casefold():
        auth = aiohttp.BasicAuth(
            request.app['config']['paypal_client_id'],
            request.app['config']['paypal_client_secret'],
        )
        method = "POST"
    elif "stripe.com" in purchased['cancel_url'].casefold():
        auth = aiohttp.BasicAuth(
            request.app['config']['stripe_api_key'],
        )
        method = "DELETE"

    # Make the request
    if method:
        async with aiohttp.ClientSession() as session:
            resp = await session.request(
                method,
                purchased['cancel_url'],
                auth=auth,
            )
        if not resp.ok:
            return json_response(
                {"error": "Failed to cancel subscription.", "success": False},
                status=400,
            )

    # If it was a fake purchase, update the expiry time in the database.
    # If it WASNT a fake purchase, then we'll get a webhook about it later.
    if not method:
        async with vbu.Database() as db:
            await db.call(
                """
                UPDATE
                    purchases
                SET
                    expiry_time = NOW() + INTERVAL '30 days'
                WHERE
                    id = $1
                """,
                purchased['id'],
            )

    # And done
    return json_response({"success": True})


@routes.get("/portal/{group}")
@vbu.web.requires_login()
@template("portal/index.htm.j2")
async def index(request: Request):
    """
    Portal page for payments. This should show all items in the group.
    """

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
        await i.fetch_price(request.app['config']['stripe_api_key'])

    # If there aren't any items then let's just redirect back to the index
    if not items:
        return HTTPFound("/")

    # Render the template
    return {
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
    }


@routes.get("/portal/item/{id}")
@vbu.web.requires_login()
async def purchase(request: Request):
    """
    Portal page for payments. This should show all items in the group.
    """

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
            request.match_info["id"],
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

        # Make sure we have a guild ID if we need one
        guild_id_str = request.query.get("guild", "")
        if guild_id_str.isdigit():
            guild_id = int(guild_id_str)
        else:
            return HTTPFound(f"/portal/{item.product_group}")

        # See if the user has purchased this item already - we'll use this to
        # redirect (if they can't buy multiple) or show an unsubscribe screen
        # (if it's a subscription)
        purchase: Optional[dict] = None
        if item.subscription or not item.multiple:
            if item.per_guild:
                purchase_rows = await db.call(
                    """
                    SELECT
                        *
                    FROM
                        purchases
                    WHERE
                        user_id = $1
                    AND
                        guild_id = $2
                    AND
                        product_name = $3
                    AND
                        expiry_time IS NULL
                    """,
                    session['user_id'],
                    guild_id,
                    items[0].name,
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
                        user_id = $1
                    AND
                        guild_id IS NULL
                    AND
                        product_name = $2
                    AND
                        expiry_time IS NULL
                    """,
                    session['user_id'],
                    items[0].name,
                    type=dict,
                )
            if purchase_rows:
                purchase = purchase_rows[0]

    # Get the item price if they're able to buy it more
    if not purchase:
        await item.fetch_price(request.app['config']['stripe_api_key'])

    # Render the template
    context = {
        "item": item,
        "user_id": session['user_id'],
        "guild_id": request.query.get("guild"),
        "purchase": purchase,
    }
    template_name = "portal/purchase.htm.j2"
    if purchase:
        if item.subscription:
            template_name = "portal/unsubscribe.htm.j2"
        elif not item.multiple:
            # template_name = "portal/owned.htm.j2"
            return HTTPFound(f"/portal/{item.product_group}")
        else:
            raise Exception("This shouldn't happen")
    return render_template(template_name, request, context)
