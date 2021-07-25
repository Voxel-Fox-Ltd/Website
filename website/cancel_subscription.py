import json
import hmac
from hashlib import sha256

import aiohttp
from aiohttp.web import Request, RouteTableDef, Response, json_response

from .utils.get_paypal_access_token import get_paypal_access_token


routes = RouteTableDef()


@routes.post('/webhooks/cancel_subscription')
async def cancel_subscription(request: Request):
    """
    Delete a subscription for a user. This requires an authorization header and should only be done
    via the backend, not through the frontend.
    """

    # Grab data
    auth_header = request.headers['Authorization']
    data = await request.json()
    product_name = data['product_name']
    cancel_url = data['cancel_url']

    # See if the data is right
    async with request.app['database']() as db:
        item_rows = await db("SELECT * FROM checkout_items WHERE product_name=$1", product_name)
    if auth_header != item_rows[0]['transaction_webhook_authorization']:
        return json_response({"error": "Invalid auth header."}, status=401)

    # Cancel sub
    if "paypal.com" in cancel_url:
        auth = aiohttp.BasicAuth(
            request.app['config']['paypal_client_id'],
            request.app['config']['paypal_client_secret'],
        )
        async with aiohttp.ClientSession() as session:
            json = {"reason": "Voxel Fox webhook invoked."}
            async with session.post(cancel_url, auth=auth) as r:
                return json_response({"error": "", "status": r.status})

    # Cancel sub
    elif "stripe.com" in cancel_url:
        auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
        async with aiohttp.ClientSession() as session:
            async with session.delete(cancel_url, auth=auth) as r:
                return json_response({"error": "", "status": r.status})

    # Cancel sub
    else:
        raise Exception()
