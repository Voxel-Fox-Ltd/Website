from aiohttp.web import HTTPFound, Request, RouteTableDef
from aiohttp_jinja2 import template
import aiohttp_session
from discord.ext import vbu

from .utils.db_util import CheckoutItem


routes = RouteTableDef()


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
    for i in items:
        await i.fetch_price(request.app['config']['stripe_api_key'])

    # If there aren't any items then let's just redirect back to the index
    if not items:
        return HTTPFound("/")

    # Render the template
    return {
        "item": items[0],
        "user_id": session['user_id'],
        "guild_id": None,
    }
