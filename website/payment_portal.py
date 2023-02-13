import uuid
from typing import Awaitable, Callable, Optional
from typing_extensions import Self
from datetime import datetime as dt, timedelta
from functools import wraps
import time

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
from .utils.json_utils import serialize
from .utils.login import requires_login, _require_login_wrapper
from .utils.get_paypal_access_token import get_paypal_basicauth


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
    max_lifetime = timedelta(minutes=15)

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

    vfl_id = request.query.get("id", "")
    discord_user_id = request.query.get("discord_user_id", request.query.get("user_id", ""))
    google_user_id = request.query.get("google_user_id", "")
    facebook_user_id = request.query.get("facebook_user_id", "")
    everlasting_user_id = request.query.get("everlasting_user_id", "")
    guild_id = request.query.get("guild_id", "")
    any_id = (
        ("vfl", vfl_id,),
        ("discord", discord_user_id,),
        ("guild", guild_id,),
        ("google", google_user_id,),
        ("facebook", facebook_user_id,),
        ("everlasting", everlasting_user_id,),
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

    # Check what they got
    result: list[dict] | None = None
    identify_column = (
        "checkout_items.id"
        if product_id
        else "checkout_items.product_name"
    )
    user_column: str
    identity: str | int
    for k, i in any_id:
        if i:
            identity = i
            if k == "guild":
                user_column = "purchases.discord_guild_id"
                identity = int(i)
            elif k == "vfl":
                user_column = "login_users.user_id"
            else:
                # if k ==  "discord":
                #     identity = int(i)
                user_column = f"login_users.{k}_user_id"
            break
    else:
        raise ValueError("Could not find identity")
    async with vbu.Database() as db:
        base_product = await db.call(
            """
            SELECT
                id,
                product_name,
                subscription,
                description
            FROM
                checkout_items
            WHERE
                {0} = $1
            """.format(identify_column),
            product_id or product_name,
            type=dict,
        )
        if not base_product:
            return json_response(
                {
                    "error": "Product doesn't exist.",
                    "success": False,
                    "result": False,
                    "generated": dt.utcnow().isoformat(),
                },
                status=400,
            )
        result = await db.call(
            """
            SELECT
                purchases.id,
                purchases.user_id,
                purchases.discord_guild_id,
                purchases.expiry_time,
                purchases.timestamp,
                purchases.quantity
            FROM
                purchases
            LEFT JOIN
                checkout_items
            ON
                purchases.product_id = checkout_items.id
            LEFT JOIN
                login_users
            ON
                login_users.id = purchases.user_id
            WHERE
                {0} = $1
            AND
                expiry_time IS NULL
            AND
                (
                        purchases.product_id = $2
                    OR
                        checkout_items.base_product = $2
                )
            """.format(user_column, identify_column),
            identity,
            base_product[0]['id'],
            type=dict,
        )

    # Return the result
    if result:
        return json_response(
            {
                "success": True,
                "result": True,
                "product": serialize(base_product[0]),
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
            except KeyError:
                user_session.invalidate()  # type: ignore
                return json_response([], headers={"X-Message": "Failed getting access token"})
            user_session["discord"]["access_token"] = (
                f"{token_json['expires_at'] + time.time() - 60}:"
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
            "UPDATE login_users SET discord_refresh_token = $2 WHERE id = $1",
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
                discord_user_id = $2
            AND
                expiry_time IS NULL
            AND
                cancel_url IS NOT NULL
            """,
            purchase_id,
            int(user_session['discord']['id']),
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
    session = await aiohttp_session.get_session(request)
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
