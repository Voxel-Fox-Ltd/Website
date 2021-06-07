from datetime import datetime as dt

import aiohttp
from aiohttp.web import Request


PAYPAL_TOKEN_CACHE = {}


async def get_paypal_access_token(request: Request) -> str:
    """
    Get the PayPal access token from your client ID and secret.
    """

    # See if the token is expired
    if PAYPAL_TOKEN_CACHE.get("expires_at", dt(2000, 1, 1)) > dt.utcnow():
        return PAYPAL_TOKEN_CACHE.get("access_token")

    # Grab a new token from PayPal
    async with aiohttp.ClientSession() as session:
        url = PAYPAL_BASE + "/v1/oauth2/token"
        data = {"grant_type": "client_credentials"}
        auth = aiohttp.BasicAuth(
            request.app['config']['paypal_client_id'],
            request.app['config']['paypal_client_secret'],
        )
        async with session.post(url, data=data, auth=auth) as r:
            response = await r.json()
    PAYPAL_TOKEN_CACHE.update(response)
    PAYPAL_TOKEN_CACHE.update({"expires_at": dt.utcnow() + timedelta(seconds=response['expires_in'])})
    return response['access_token']
