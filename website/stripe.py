import json
import hmac
from hashlib import sha256
from base64 import b64encode

import aiohttp
from aiohttp.web import Request, RouteTableDef, Response, json_response


routes = RouteTableDef()
STRIPE_BASE = "https://api.stripe.com/v1"


def get_dict_key(base, key, index=None):
    if base:
        v = f"{base}[{key}]"
    else:
        v = key
    if index is not None:
        return f"{v}[{index}]"
    return v


def form_encode(data: dict, base: str = "") -> dict:
    """
    Form encode a dict for use in the Stripe API.
    """

    output_dict = {}
    for key, value in data.items():
        if isinstance(value, (str, int)):
            output_dict[get_dict_key(base, key)] = value
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                if isinstance(item, (str, int)):
                    output_dict[get_dict_key(base, key, index)] = item
                else:
                    output_dict.update(form_encode(item, get_dict_key(base, key, index)))
        else:
            output_dict.update(form_encode(value, get_dict_key(base, key)))
    return output_dict


@routes.post('/webhooks/stripe/create_checkout_session')
async def create_checkout_session(request: Request):
    """
    Create a checkout session for the user.
    """

    # Get their post data for the item name
    post_data: dict = await request.json()
    product_name = post_data.pop('product_name')
    quantity = post_data.pop('quantity', 1)

    # Get the user's login details for metadata
    if 'discord_user_id' not in post_data:
        raise Exception("Missing user ID from POST request")
    metadata = post_data

    # Get the item data from the database
    async with request.app['database']() as db:
        item_rows = await db(
            """SELECT * FROM checkout_items WHERE product_name=$1""",
            product_name,
        )
    if not item_rows:
        raise Exception(f"Missing item {product_name} from database")
    item_row = item_rows[0]

    # Make params to send to Stripe
    json = {
        "cancel_url": item_row['cancel_url'],
        "payment_method_types": ["card"],
        "success_url": item_row['success_url'],
        "mode": "subscription" if item_row['subscription'] else "payment",
        "line_items": [
            {
                "price": item_row['stripe_price_id'],
                "quantity": quantity,
            },
        ],
        "metadata": metadata,
    }
    if item_row['subscription']:
        json.update({"subscription_data": {"metadata": metadata}})

    # Send some data to Stripe
    async with aiohttp.ClientSession() as session:

        # Ask Stripe for a session object
        url = STRIPE_BASE + "/checkout/sessions"
        data = form_encode(json)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
        async with session.post(url, data=data, headers=headers, auth=auth) as r:
            response = await r.json()
            if not r.ok:
                return json_response(response, status=500)

        # And while we're here, add a Discord user ID to the customer's metadata
        url = STRIPE_BASE + "/customers/{0}".format(response['customer'])
        data = form_encode({"metadata": {"discord_user_id": metadata['discord_user_id']}})
        await session.post(url, data=data, headers=headers, auth=auth)

    # And return the session ID
    href_url = f"https://checkout.stripe.com/pay/{response['id']}"
    return json_response({'href': href_url, "id": response['id'], **response})


@routes.post('/webhooks/stripe/purchase_webhook')
async def stripe_purchase_complete(request: Request):
    """
    Handles Stripe throwing data my way.
    """

    # Get the data from the post request
    stripe_data_string = await request.read()
    stripe_data = json.loads(stripe_data_string.decode())

    # Let's throw that into a logger
    request.app['logger'].info(stripe_data_string)

    # Check the signature to make sure it's valid
    signature = dict([i.strip().split("=") for i in request.headers['Stripe-Signature'].split(",")])
    signed_payload = signature['t'] + '.' + stripe_data_string.decode()
    signing_secret = request.app['config']['stripe_webhook_signing_secret']
    mac = hmac.new(signing_secret.encode(), signed_payload.encode(), sha256)
    hashed = mac.hexdigest()
    if not hmac.compare_digest(hashed.encode(), signature['v1'].encode()):
        request.app['logger'].info("Invalid data sent to Stripe webhook url")
        return Response(status=400)  # Oh no it was fake data

    # Process the data
    event = stripe_data['type']
    if event == "checkout.session.completed":
        # This happens for subscriptions as well as single purchases
        data = await get_checkout_session_from_payment_intent(request, stripe_data['data']['object']['payment_intent'])
        await checkout_processor(request, data)
    elif event == "customer.subscription.deleted":
        await subscription_deleted(request, stripe_data['data']['object'])
    elif event == "charge.refunded":
        await charge_refunded(request, stripe_data['data']['object'])

    # And we have no more events to process
    return Response(status=200)


async def checkout_processor(request: Request, data: dict, *, refunded: bool = False) -> None:
    """
    Pinged when a charge is successfully recieved, _including_ subscriptions and
    other items.

    Args:
        request (Request): The request that triggered this method call.
        data (dict): The checkout object.
        refunded (bool, optional): Whether or not the purchased items have been refunded.
    """

    # Ask Stripe for the items that the user checked out with
    async with aiohttp.ClientSession() as session:
        url = STRIPE_BASE + "/checkout/sessions/{0}/line_items".format(data['id'])
        auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
        async with session.get(url, auth=auth) as r:
            line_items_object = await r.json()
    line_items = line_items_object['data']

    # Grab the item from the database
    line_item_names = [i['description'] for i in line_items]
    async with request.app['database']() as db:
        item_rows = await db(
            """SELECT * FROM stripe_checkout_items WHERE product_name=ANY($1::TEXT)""",
            line_item_names,
        )

    # Add a `_stripe` attr to all of the line items
    item_rows = [dict(i) for i in item_rows]
    for i in item_rows:
        for o in line_items:
            if i['product_name'] == o['description']:
                i['_stripe'] = o
                break

    # Throw all the relevant data to the specified webhook
    async with aiohttp.ClientSession() as session:
        for row in item_rows:
            if not row['transaction_webhook']:
                continue
            headers = {"Authorization": row['transaction_webhook_authentication']}
            json = {
                "product_name": row['product_name'],
                "quantity": row['_stripe']['quantity'],
                "refund": refunded,
                "subscription": row['_stripe']['type'] == "recurring",
                **data['metadata'],
                **data['customer']['metadata'],
                # "_stripe": row['_stripe'],
                "subscription_expiry_time": None,
            }
            await session.post(row['transaction_webhook'], json=json, headers=headers)


async def get_checkout_session_from_payment_intent(request: Request, payment_intent_id: str) -> dict:
    """
    Get the checkout session object given its payment intent ID.
    """

    async with aiohttp.ClientSession() as session:
        url = STRIPE_BASE + "/checkout/sessions/"
        params = {"payment_intent": payment_intent_id}
        auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
        data = form_encode({"expand": ["customer"]})
        async with session.get(url, params=params, data=data, auth=auth) as r:
            return await r.json()


async def charge_refunded(request: Request, data: dict) -> None:
    """
    Pinged when a charge is refunded.
    """

    checkout_data = await get_checkout_session_from_payment_intent(data['payment_intent'])
    await checkout_processor(request, checkout_data['data'][0], refunded=True)


async def subscription_deleted(request: Request, data: dict) -> None:
    """
    Pinged when a subscription is deleted.
    """

    # See when the subscription expires
    subscription_expiry_time = data['current_period_end']

    # Get the subscription item
    subscription_item = data['items']['data'][0]

    # Get the product item so that we can grab its name
    async with aiohttp.ClientSession() as session:
        url = STRIPE_BASE + "/products/{0}".format(subscription_item['price']['product'])
        auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
        async with session.get(url, auth=auth) as r:
            product_data = await r.json()

    # Grab the relevant data from the database
    async with request.app['database']() as db:
        item_rows = await db(
            """SELECT * FROM stripe_checkout_items WHERE product_name=$1""",
            product_data['name'],
        )

    # Get the customer item so that we can get the user's Discord ID
    async with aiohttp.ClientSession() as session:
        url = STRIPE_BASE + "/customers/{0}".format(subscription_item['customer'])
        async with session.get(url, auth=auth) as r:
            customer_data = await r.json()

    # Make a loop here so I don't need to do it while I have a session open
    item_row = [dict(i) for i in item_rows][0]

    # Throw our relevant data at the webhook
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": item_row['transaction_webhook_authentication']}
        json = {
            "product_name": item_row['product_name'],
            "quantity": subscription_item['quantity'],
            "refund": False,
            "subscription": True,
            **subscription_item['metadata'],
            **customer_data['metadata'],
            # "_stripe": data,
            "subscription_expiry_time": subscription_expiry_time,
        }
        await session.post(item_row['transaction_webhook'], json=json, headers=headers)
