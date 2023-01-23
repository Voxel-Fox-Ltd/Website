import uuid
from typing import Awaitable, Callable, Optional
from typing_extensions import Self
from datetime import datetime as dt, timedelta
from functools import wraps

from aiohttp.web import (
    HTTPFound,
    Request,
    Response,
    RouteTableDef,
    StreamResponse,
    json_response,
)
from aiohttp_jinja2 import render_template, template
import aiohttp_session
from discord.ext import vbu
import aiohttp

from .utils.db_util import CheckoutItem


routes = RouteTableDef()


CR = Callable[
    [Request],
    Awaitable[
        StreamResponse
        | tuple[StreamResponse, bool]
        | tuple[StreamResponse, timedelta]
    ]
]


class CacheItem:

    all_items: dict[str, Self] = dict()
    max_lifetime = timedelta(hours=1)

    __slots__ = (
        '_response',
        'cached_at',
        'lifetime',
    )

    def __init__(
            self,
            request: Request,
            response: StreamResponse,
            cached_at: Optional[dt] = None,
            lifetime: Optional[timedelta] = None):
        self._response = response
        self.cached_at = cached_at or dt.utcnow()
        self.lifetime = lifetime or self.max_lifetime
        self.all_items[self.get_key(request)] = self

    @property
    def response(self):
        return Response(
            body=self._response._body,
            status=self._response.status,
            headers=self._response.headers,
        )

    @staticmethod
    def get_key(request: Request) -> str:
        keys = sorted(request.query.keys())
        return (
            request.url.path
            + "&".join(f"{key}={request.query[key]}" for key in keys)
        )

    @classmethod
    def get(cls, request: Request) -> Optional[Self]:
        key = cls.get_key(request)
        v = cls.all_items.get(key)
        if v:
            if v.cached_at + v.lifetime < dt.utcnow():
                del cls.all_items[key]
                return None
            return v
        return None


def cache_by_query():
    """
    Cache a given request to a URL by its query string.
    """

    def decorator(func: CR) -> Callable[[Request], Awaitable[StreamResponse]]:
        @wraps(func)
        async def wrapper(request: Request) -> StreamResponse:
            cached = CacheItem.get(request)
            if cached and request.headers.get("Cache-Control") != "no-cache":
                return cached.response
            response = await func(request)
            keep = False
            if isinstance(response, tuple):
                response, keep = response
            if keep is True:
                CacheItem(request, response)
            elif isinstance(keep, timedelta):
                CacheItem(request, response, lifetime=keep)
            return response
        return wrapper
    return decorator


@routes.get("/api/portal/check")
@cache_by_query()
async def portal_check(request: Request):
    """
    Check if a user has purchased a certain product.
    """

    # Check the get params
    product_name = request.query.get("product_name", "")
    product_id = request.query.get("product_id", "")
    if not product_name and not product_id:
        return json_response(
            {
                "error": "No product ID provided.",
                "success": False,
                "result": False,
                "generated": dt.utcnow().isoformat(),
            },
            status=400,
        ), timedelta(days=7)
    user_id = request.query.get("user_id", "")
    guild_id = request.query.get("guild_id", "")
    if user_id or guild_id:
        pass
    elif user_id and guild_id:
        return json_response(
            {
                "error": "Both user_id and guild_id provided.",
                "success": False,
                "result": False,
                "generated": dt.utcnow().isoformat(),
            },
            status=400,
        ), timedelta(days=7)
    else:
        return json_response(
            {
                "error": "No user or guild ID provided.",
                "success": False,
                "result": False,
                "generated": dt.utcnow().isoformat(),
            },
            status=400,
        ), True

    # Make sure the given item is an int
    if not (user_id or guild_id).isdigit():
        return json_response(
            {
                "error": "Invalid user or guild ID provided.",
                "success": False,
                "result": False,
                "generated": dt.utcnow().isoformat(),
            },
            status=400,
        )

    # Check what they got
    result = None
    identify_column = (
        "checkout_items.id"
        if product_id
        else "checkout_items.product_name"
    )
    async with vbu.Database() as db:

        # Check by user ID
        if user_id:
            result = await db.call(
                """
                SELECT
                    purchases.*, checkout_items.subscription
                FROM
                    purchases
                LEFT JOIN
                    checkout_items
                ON
                    purchases.product_id = checkout_items.id
                WHERE
                    discord_user_id = $1
                AND
                    {identify_column} = $2
                AND
                    expiry_time IS NULL
                """.format(identify_column=identify_column),
                int(user_id),
                product_id or product_name,
                type=dict,
            )

        # Check by guild ID
        elif guild_id:
            result = await db.call(
                """
                SELECT
                    purchases.*, checkout_items.subscription
                FROM
                    purchases
                LEFT JOIN
                    checkout_items
                ON
                    purchases.product_id = checkout_items.id
                WHERE
                    discord_guild_id = $1
                AND
                    {identify_column} = $2
                AND
                    expiry_time IS NULL
                """.format(identify_column=identify_column),
                int(guild_id),
                product_id or product_name,
                type=dict,
            )

    # Return the result
    if result:
        return json_response(
            {
                "success": True,
                "result": True,
                "generated": dt.utcnow().isoformat(),
            },
        ), True
    return json_response(
        {
            "success": True,
            "result": False,
            "generated": dt.utcnow().isoformat(),
        },
    ), True


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
                "permissions": {
                    "manage_guild": bool(int(g['permissions']) & 0x20),
                    "administrator": bool(int(g['permissions']) & 0x8),
                    "owner": g['owner'],
                }
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
            await i.fetch_user(db)
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
        if item.subscription or not item.multiple:
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
                    session['user_id'],
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
                    session['user_id'],
                    items[0].id,
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
