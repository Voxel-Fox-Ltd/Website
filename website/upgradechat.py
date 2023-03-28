import logging
import asyncio
from base64 import b64encode
from datetime import datetime as dt

import aiohttp
from aiohttp.web import Response, RouteTableDef, Request, StreamResponse
from discord.ext import vbu

from .utils import types
from .utils.db_util import create_purchase, fetch_purchase, update_purchase
from .utils.db_models import CheckoutItem, LoginUser


routes = RouteTableDef()
ACCESS_TOKEN: str | None = None
access_token_refresh_task: asyncio.Task | None = None


log = logging.getLogger("vbu.voxelfox.upgradechat")


async def get_access_token(
        request: Request | None,
        force_refresh: bool = False) -> str:
    """
    Get an access token for Upgrade.Chat.
    """

    # See if we already have one
    global ACCESS_TOKEN
    if ACCESS_TOKEN and not force_refresh:
        return ACCESS_TOKEN

    # Get oauth data from config file
    if request is None:
        raise TypeError("Request is required if we need to get a new access token.")
    oauth_data = request.app['config']['oauth']['upgradechat']
    basic_auth_token = b64encode(
        f"{oauth_data['client_id']}:{oauth_data['client_secret']}"
        .encode()
    ).decode()

    # Set up params
    data = {"grant_type": "client_credentials"}
    headers = {
        "Authorization": f"Basic {basic_auth_token}",
        "Accept": "application/json",
    }

    # Let's get one
    log.info("Getting new access token")
    url = "https://api.upgrade.chat/oauth/token"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data, headers=headers) as r:
            data = await r.json()

    # Start new task
    async def refresh():
        expires_at = dt.fromtimestamp(int(data['access_token_expires_in']) / 1_000)
        expires_in = (expires_at - dt.utcnow()).total_seconds() - 10
        await asyncio.sleep(expires_in)
        log.info("Access token expiring, now refreshing...")
        await get_access_token(request, True)
    global access_token_refresh_task
    access_token_refresh_task = asyncio.create_task(refresh())

    # Return created token
    return data['access_token']


@routes.post('/webhooks/upgradechat/purchase_webhook')
async def purchase_webhook(request: Request) -> StreamResponse:
    """
    Pinged when a person purchases something from UpgradeChat.
    """

    # Get the data
    data: types.UpgradeChatWebhookEvent = await request.json()

    # Validate
    access_token = await get_access_token(request)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "User-Agent": "Voxel Fox payment processor (kae@voxelfox.co.uk)",
    }
    url = "https://api.upgrade.chat/v1/webhook-events/{0}/validate"
    async with aiohttp.ClientSession() as session:
        async with session.get(url.format(data['id']), headers=headers) as r:
            validated: types.UpgradeChatValidation = await r.json()
    if validated['valid'] is False:
        log.info("Received invalid UpgradeChat event")
        return Response(status=201)  # Valid code, invalid body
    log.info(f"Received UpgradeChat event - {data}")

    # Make sure the product name is valid
    # We are hardcoding product names because I don't want to use UpgradeChat again
    body = data.get("data", data.get("body"))
    assert body is not None
    uc_product_names = [
        i['product']['name']
        for i in body['order_items']
    ]
    if len(uc_product_names) > 1:
        log.info(f"UpgradeChat event references multiple products - {uc_product_names}")
        raise Exception()  # Fuck this
    product_name = {
        "MarriageBot Subscription Tier 1": "MarriageBot Tier 1",
        "MarriageBot Subscription Tier 2": "MarriageBot Tier 2",
        "MarriageBot Subscription Tier 3": "MarriageBot Tier 3",
    }.get(uc_product_names[0], None)
    if product_name is None:
        log.info(f"UpgradeChat event references invalid product - {uc_product_names[0]}")
        return Response(status=201)  # Valid body, invalid product

    # Store data
    async with vbu.Database() as db:
        product = await CheckoutItem.fetch_by_name(db, product_name)
        assert product
        user_rows: list[dict] = await db.call(
            "SELECT * FROM login_users WHERE discord_user_id = $1",
            body['user']['discord_id']  # pyright: ignore
        )
        if not user_rows:
            user_rows: list[dict] = await db.call(
                "INSERT INTO login_users (discord_user_id) VALUES ($1)",
                body['user']['discord_id']  # pyright: ignore
            )
        user = LoginUser.from_row(user_rows[0])
        if data['type'] == "order.created":
            await create_purchase(
                db,
                user,
                product,
                identifier=body['payment_processor_record_id'],
            )
        elif data['type'] in ["order_updated", "order.deleted"]:
            purchase = await fetch_purchase(db, user, product)
            if not purchase:
                log.info(f"UpgradeChat event does not have a purchase stored in the database already")
                raise Exception()
            if data['type'] == "order.deleted":
                params = {
                    "deleted": True,
                }
            else:
                assert body['cancelled_at']
                params = {
                    "expiry_time": dt.strptime(
                        body['cancelled_at'],
                        "%Y-%m-%dT%H:%M:%S.%fZ",
                    ),
                }
            await update_purchase(
                db,
                purchase[0].id,
                **params,
            )

    # And done
    return Response(status=201)
