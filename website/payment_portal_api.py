from typing import Awaitable, Callable, Optional, Any
from typing_extensions import Self
from datetime import datetime as dt, timedelta
from functools import wraps
import time

from aiohttp.web import (
    Request,
    Response,
    StreamResponse,
    json_response,
    RouteTableDef,
)
import aiohttp_session
from discord.ext import vbu
import aiohttp

from .utils.json_utils import serialize
from .utils.get_paypal_access_token import get_paypal_basicauth
from .utils.login import requires_manager_login


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
    max_lifetime = timedelta(minutes=1)

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


@routes.patch("/api/portal/update")
@requires_manager_login()
async def portal_update(request: Request):
    """
    Update a given item.
    """

    data = await request.json()
    session = await aiohttp_session.get_session(request)
    async with vbu.Database() as db:
        await db.call(
            """
            UPDATE
                checkout_items
            SET
                product_name = $2,
                description = $3,
                product_group = $4,
                success_url = $5,
                cancel_url = $6,
                stripe_product_id = $7,
                stripe_price_id = $8,
                paypal_plan_id = $9
            WHERE
                id = $1
            AND
                creator_id = (
                    SELECT
                        id
                    FROM
                        manager_users
                    WHERE
                        login_id = $10
                )
            """,
            data['id'],
            data['product_name'],
            data['description'],
            data['product_group'],
            data['success_url'],
            data['cancel_url'],
            data['stripe_product_id'],
            data['stripe_price_id'],
            data['paypal_plan_id'],
            session['id'],
        )
    return Response()


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

    vfl_id = request.query.get("id", "")
    discord_user_id = request.query.get("discord_user_id", request.query.get("user_id", ""))
    google_user_id = request.query.get("google_user_id", "")
    facebook_user_id = request.query.get("facebook_user_id", "")
    guild_id = request.query.get("guild_id", "")
    any_id = (
        ("vfl", vfl_id,),
        ("discord", discord_user_id,),
        ("guild", guild_id,),
        ("google", google_user_id,),
        ("facebook", facebook_user_id,),
    )
    if any((i[1] for i in any_id)):
        pass
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

    # Work out what identity to use
    user_column: str  # The column that the user identifies with (X_user_id)
    identity: str | int  # The given identity (X_user_id = Y)
    for k, i in any_id:
        if i:
            identity = i
            if k == "guild":
                user_column = "purchases.discord_guild_id"
                identity = int(i)
            elif k == "vfl":
                user_column = "users.user_id"
            else:
                user_column = f"users.{k}_user_id"
            break
    else:
        raise ValueError("Could not find identity")

    # It is time to open our database connection
    db = await vbu.Database.get_connection()

    # Get the product we want to check for
    if product_id:
        base_products = await db.call(
            """
            SELECT
                id,
                product_name,
                subscription,
                description
            FROM
                checkout_items
            WHERE
                id = $1
            OR
                base_product_id = $1
            """,
            product_id,
        )
        possible_base_product = [
            i
            for i in base_products
            if str(i['id']) == product_id
        ]
    else:
        base_products = await db.call(
            """
            SELECT
                id,
                product_name,
                subscription,
                description
            FROM
                checkout_items
            WHERE
                checkout_items.product_name = $1
            """,
            product_name,
        )
        possible_base_product = base_products

    # We didn't get a product
    if not possible_base_product:
        await db.disconnect()
        return json_response(
            {
                "error": "Product doesn't exist.",
                "success": False,
                "result": False,
                "generated": dt.utcnow().isoformat(),
            },
            status=400,
        )
    recursive_base_product: dict[str, Any] = possible_base_product[0]

    # Try and get the user's purchases
    result: list[dict] | None = await db.call(
        """
        SELECT
            purchases.id,
            purchases.user_id,
            purchases.discord_guild_id,
            purchases.expiry_time,
            purchases.timestamp,
            purchases.quantity,
            purchases.product_id,
            checkout_items.base_product_id
        FROM
            purchases
        LEFT JOIN
            checkout_items
        ON
            purchases.product_id = checkout_items.id
        LEFT JOIN
            users
        ON
            users.id = purchases.user_id
        WHERE
            {0} = $1
        AND
            expiry_time IS NULL
        AND
            (
                    purchases.product_id = $2
                OR
                    checkout_items.base_product_id = $2
            )
        """.format(user_column),
        identity,
        recursive_base_product['id'],
    )
    await db.disconnect()

    # Return the result
    if result:
        return json_response(
            {
                "success": True,
                "result": True,
                "product": serialize(recursive_base_product),
                "products": serialize({
                    str(i['id']): serialize(i)
                    for i in base_products
                }),
                "purchases": [serialize(i) for i in result],
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
    access_token = user_session.get("discord", dict()).get("access_token")
    refresh_token = user_session.get("discord", dict()).get("refresh_token")
    if not refresh_token:
        user_session.invalidate()  # type: ignore
        return json_response([], headers={"X-Message": "Missing refresh token"})

    # Do some web requesting
    async with aiohttp.ClientSession() as session:

        # Get an access token
        if access_token is None or int(access_token.split(":", 1)[0]) < time.time():
            discord_config = request.app['config']['oauth']['discord']
            resp = await session.post(
                "https://discord.com/api/v9/oauth2/token",
                data={
                    "client_id": discord_config['client_id'],
                    "client_secret": discord_config['client_secret'],
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )
            token_json = await resp.json()
            try:
                access_token = token_json['access_token']
                expires_at = token_json['expires_at']
            except KeyError:
                user_session.invalidate()  # type: ignore
                return json_response([], headers={"X-Message": "Failed getting access token"})
            user_session["discord"]["access_token"] = (
                f"{expires_at + time.time() - 60}:"
                f"{token_json['access_token']}"
            )
            user_session["discord"]["refresh_token"] = token_json['refresh_token']
        else:
            access_token = user_session['discord']['access_token'].split(":", 1)[-1]

        # Get the guilds
        resp = await session.get(
            "https://discord.com/api/users/@me/guilds",
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        )
        if not resp.ok:
            user_session.invalidate()  # type: ignore
            return json_response([], headers={"X-Message": "Failed getting guilds"})
        guilds = await resp.json()

    # Save new token to db
    async with vbu.Database() as db:
        await db.call(
            "UPDATE users SET discord_refresh_token = $2 WHERE id = $1",
            user_session["id"],
            user_session["discord"]["refresh_token"],
        )

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
            user_session['id'],
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
        auth = await get_paypal_basicauth()
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
