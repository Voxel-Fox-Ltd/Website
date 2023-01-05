from aiohttp.web import RouteTableDef, Request, HTTPFound, json_response
from aiohttp_jinja2 import template
import aiohttp_session
from discord.ext import vbu


routes = RouteTableDef()


VALID_USERS = [
    141231597155385344,
    607952795794145281,
]


@routes.get('/checkout_items')
@vbu.web.requires_login()
@template("checkout_items.htm.j2")
async def checkout_items(request: Request):
    """
    The Kae-only checkout items page.
    """

    session = await aiohttp_session.get_session(request)
    if session['user_id'] not in VALID_USERS:
        return HTTPFound('/')

    async with vbu.Database() as db:
        rows = await db.call("SELECT * FROM checkout_items")
        return {
            'data': rows
        }


@routes.post('/checkout_items')
async def checkout_items_post(request: Request):
    """
    The new checkout item backend.
    """

    # Validate login
    session = await aiohttp_session.get_session(request)
    if session.get('user_id') not in VALID_USERS:
        return json_response(
            {"error": "You are not a valid user."},
            status=401,
        )

    # Validate request
    data = await request.json()
    required_keys = [
        "product_name",
        "success_url",
        "cancel_url",
        "subscription",
        "stripe_product_id",
        "stripe_price_id",
        "paypal_plan_id",
        "transaction_webhook",
        "transaction_webhook_authorization",
    ]
    missing_keys = set()
    for key in required_keys:
        if key not in data:
            missing_keys.add(key)
    if missing_keys:
        return json_response(
            {"error": f"Missing keys: {', '.join(missing_keys)}"},
            status=400,
        )

    # SQL time
    async with vbu.Database() as db:
        await db.call(
            """
            INSERT INTO
                checkout_items
                (
                    product_name,
                    success_url,
                    cancel_url,
                    subscription,
                    stripe_product_id,
                    stripe_price_id,
                    paypal_plan_id,
                    transaction_webhook,
                    transaction_webhook_authorization
                )
            VALUES
                ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT
                (product_name)
            DO UPDATE
            SET
                success_url = excluded.success_url,
                cancel_url = excluded.cancel_url,
                subscription = excluded.subscription,
                stripe_product_id = excluded.stripe_product_id,
                stripe_price_id = excluded.stripe_price_id,
                paypal_plan_id = excluded.paypal_plan_id,
                transaction_webhook = excluded.transaction_webhook,
                transaction_webhook_authorization = excluded.transaction_webhook_authorization
            """,
            data['product_name'],
            data['success_url'],
            data['cancel_url'],
            data['subscription'] == '1',
            data['stripe_product_id'],
            data['stripe_price_id'],
            data['paypal_plan_id'] or None,
            data['transaction_webhook'] or None,
            data['transaction_webhook_authorization'],
        )
    return json_response({"error": None})
