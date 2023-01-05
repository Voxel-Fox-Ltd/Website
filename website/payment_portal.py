from aiohttp.web import HTTPFound, Request, RouteTableDef
from aiohttp_jinja2 import template
from discord.ext import vbu

from .utils.db_util import CheckoutItem


routes = RouteTableDef()


@routes.get("/portal/{group}")
@template("portal/index.htm.j2")
@vbu.web.requires_login()
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
                product_group = $1
            """,
            request.match_info["group"],
        )
    items = [
        CheckoutItem.from_row(row)
        for row in item_rows
    ]

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
