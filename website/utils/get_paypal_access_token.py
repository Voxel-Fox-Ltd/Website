from datetime import datetime as dt, timedelta

import aiohttp
from aiohttp.web import Request
from discord.ext import vbu


PAYPAL_TOKEN_CACHE = {}
PAYPAL_BASE = "https://api-m.paypal.com"  # "https://api-m.sandbox.paypal.com"


async def get_paypal_basicauth() -> aiohttp.BasicAuth:
    """
    Get the only valid baisc auth for PayPal that I have.
    """

    async with vbu.Database() as db:
        row = await db.call(
            """
            SELECT
                paypal_client_id,
                paypal_client_secret
            FROM
                users
            WHERE
                stripe_id = 'VFL'
            """,
        )
    paypal_client_id = row[0]['paypal_client_id']
    paypal_client_secret = row[0]['paypal_client_secret']
    return aiohttp.BasicAuth(
        paypal_client_id,
        paypal_client_secret,
    )


async def get_paypal_access_token(request: Request) -> str:
    """
    Get the PayPal access token from your client ID and secret.
    """

    # See if the token is expired
    if PAYPAL_TOKEN_CACHE.get("expires_at", dt(2000, 1, 1)) > dt.utcnow():
        return PAYPAL_TOKEN_CACHE["access_token"]

    # Grab a new token from PayPal
    auth = await get_paypal_basicauth()
    async with aiohttp.ClientSession() as session:
        url = PAYPAL_BASE + "/v1/oauth2/token"
        data = {"grant_type": "client_credentials"}
        async with session.post(url, data=data, auth=auth) as r:
            response = await r.json()
    PAYPAL_TOKEN_CACHE.update(response)
    PAYPAL_TOKEN_CACHE.update({
        "expires_at": dt.utcnow() + timedelta(seconds=response['expires_in'])
    })
    return response['access_token']
