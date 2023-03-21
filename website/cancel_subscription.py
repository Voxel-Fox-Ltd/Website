import aiohttp
from aiohttp.web import Request, RouteTableDef, json_response
from discord.ext import vbu

from .utils.get_paypal_access_token import get_paypal_basicauth


routes = RouteTableDef()


@routes.post('/webhooks/cancel_subscription')
async def cancel_subscription(request: Request):
    """
    Delete a subscription for a user. This requires an authorization header
    and should only be done via the backend, not through the frontend.
    """

    # Grab data
    auth_header = request.headers.get('Authorization', '')
    data = await request.json()
    product_name = data.get('product_name', '')
    cancel_url = data.get('cancel_url', '')

    # Make sure all data is present
    if not auth_header or not product_name or not cancel_url:
        return json_response(
            {'error': 'Missing data'},
            status=400,
        )

    # Make sure the authorization header is correct for the associated product
    # name
    async with vbu.Database() as db:
        item_rows = await db.call(
            """
            SELECT
                1
            FROM
                checkout_items
            WHERE
                product_name = $1
                AND transaction_webhook_authorization = $2
            """,
            product_name, auth_header,
        )
    if not item_rows:
        return json_response(
            {"error": "Invalid auth header."},
            status=401,
        )

    # Get the right auth and url
    if "paypal.com" in cancel_url:
        auth = await get_paypal_basicauth()
        method = "POST"
    elif "stripe.com" in cancel_url:
        auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
        method = "DELETE"
    else:
        raise Exception()

    # Make the request
    async with aiohttp.ClientSession() as session:
        r = await session.request(method, cancel_url, auth=auth)
    return json_response({"error": "", "status": r.status})
