from aiohttp.web import HTTPFound, Request, RouteTableDef, json_response
from aiohttp_jinja2 import template
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
@template("portal/user_item.htm.j2")
async def user_item(request: Request):
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

        # See if the user has purchased this item already
        purchased = False
        if item.multiple and item.subscription is False:
            if item.per_guild:
                purchased = await db.call(
                    """
                    SELECT
                        1
                    FROM
                        purchases
                    WHERE
                        user_id = $1
                    AND 
                        guild_id = $2
                    AND 
                        item_name = $3
                    """,
                    session['user_id'],
                    request.query.get("guild"),
                    items[0].name,
                )
            else:
                purchased = await db.call(
                    """
                    SELECT
                        1
                    FROM
                        purchases
                    WHERE
                        user_id = $1
                    AND 
                        guild_id = $2
                    AND 
                        item_name = $3
                    """,
                    session['user_id'],
                    request.query.get("guild"),
                    items[0].name,
                )

    # Get the item price
    await item.fetch_price(request.app['config']['stripe_api_key'])

    # Render the template
    return {
        "item": item,
        "user_id": session['user_id'],
        "guild_id": request.query.get("guild"),
        "purchased": bool(purchased),
    }
