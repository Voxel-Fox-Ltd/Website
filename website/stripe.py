import json
import hmac
from hashlib import sha256
import logging
from typing import Optional

import aiohttp
from aiohttp.web import Request, RouteTableDef, Response, json_response
from discord.ext import vbu

from .utils.db_util import (
    CheckoutItem,
    fetch_purchase,
    create_purchase,
    log_transaction,
    update_purchase,
)
from .utils.webhook_util import send_webhook


routes = RouteTableDef()
log = logging.getLogger("vbu.voxelfox.stripe")
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
            dk = get_dict_key(base, key)
            output_dict[dk] = value
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                dk = get_dict_key(base, key, index)
                if isinstance(item, (str, int)):
                    output_dict[dk] = item
                else:
                    output_dict.update(form_encode(item, dk))
        else:
            dk = get_dict_key(base, key)
            output_dict.update(form_encode(value, dk))
    return output_dict


@routes.post('/webhooks/stripe/create_checkout_session')
async def create_checkout_session(request: Request):
    """
    Create a checkout session for the user.
    """

    # Get their post data for the item name
    post_data: dict = await request.json()
    product_id = post_data.pop('product_id')
    quantity = post_data.pop('quantity', 1)

    # Get the user's login details for metadata
    if 'discord_user_id' not in post_data:
        raise Exception("Missing user ID from POST request")
    metadata = post_data

    # Get the item data from the database
    async with vbu.Database() as db:
        item = await CheckoutItem.fetch(
            db,
            id=product_id
        )
    if item is None:
        raise Exception(f"Missing item {product_id} from database")

    # Make params to send to Stripe
    json_data = {
        "cancel_url": item.cancel_url,
        "payment_method_types": ["card"],
        "success_url": item.success_url,
        "mode": "subscription" if item.subscription else "payment",
        "line_items": [
            {
                "price": item.stripe_price_id,
                "quantity": quantity,
            },
        ],
        "metadata": metadata,
    }
    if item.subscription:
        json_data.update({"subscription_data": {"metadata": metadata}})

    # Send some data to Stripe
    async with aiohttp.ClientSession() as session:

        # Ask Stripe for a session object
        url = f"{STRIPE_BASE}/checkout/sessions"
        form_data = form_encode(json_data)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
        resp = await session.post(url, data=form_data, headers=headers, auth=auth)
        response = await resp.json()
        if not resp.ok:
            return json_response(
                response,
                status=500,
                headers={"Access-Control-Allow-Origin": "*"},
            )

    # And while we're here, add a Discord user ID to the customer's metadata
    if response['customer']:
        await set_customer_metadata(
            request,
            response['customer'],
            {
                "discord_user_id": metadata['discord_user_id'],
            },
        )

    # And return the session ID
    href_url = f"https://checkout.stripe.com/pay/{response['id']}"
    return json_response(
        {
            "href": href_url,
            "id": response['id'],
            **response,
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )


@routes.post('/webhooks/stripe/purchase_webhook')
async def stripe_purchase_complete(request: Request):
    """
    Handles Stripe throwing data my way.
    """

    # Get the data from the post request
    stripe_data_string = await request.read()
    stripe_data = json.loads(stripe_data_string.decode())

    # Let's throw that into a logger
    log.info(f"Data from Stripe: {json.dumps(stripe_data)}")

    # Check the signature to make sure it's valid
    signature = dict([
        i.strip().split("=", 1)
        for i in request.headers['Stripe-Signature'].split(",")
    ])
    signed_payload = signature['t'] + '.' + stripe_data_string.decode()
    signing_secret = request.app['config']['stripe_webhook_signing_secret']
    mac = hmac.new(signing_secret.encode(), signed_payload.encode(), sha256)
    hashed = mac.hexdigest()
    if not hmac.compare_digest(hashed.encode(), signature['v1'].encode()):
        log.info("Invalid data sent to Stripe webhook url")
        return Response(status=400)  # Oh no it was fake data

    # Handle each checkout event
    event = stripe_data['type']
    if event in ["checkout.session.completed", "charge.captured", "charge.succeeded"]:
        # Checkout session complete happens for all checkout types
        # Charge captured can happen without a checkout session
        await checkout_processor(
            request,
            stripe_data['data']['object'],
            stripe_data.get('account', 'Voxel Fox'),
            event_type=event
        )
    elif event == "customer.subscription.deleted":
        await subscription_deleted(
            request,
            stripe_data['data']['object'],
            stripe_data.get('account', 'Voxel Fox'),
        )
    elif event == "charge.refunded":
        await charge_refunded(
            request,
            stripe_data['data']['object'],
            stripe_data.get('account', 'Voxel Fox'),
        )
    else:
        log.info(f"Unhandled Stripe event '{event}'")

    # And we have no more events to process
    return Response(status=200)


async def checkout_processor(
        request: Request,
        data: dict,
        stripe_account_id: str,
        *,
        event_type: str,
        refunded: bool = False) -> None:
    """
    Pinged when a charge is successfully recieved, _including_ subscriptions and
    other items.

    Parameters
    ----------
    request : Request
        The request that triggered this method call.
    data : dict
        The checkout object.
    refunded : bool, optional
        Whether or not the purchased items have been refunded.
    """

    # First we want to update the customer metadata - apparently when you
    # create a subscription it doesn't update them, so we'll just do that here
    # if that's necessary
    if event_type == "checkout.session.completed":
        if data['mode'] == "subscription":
            await set_customer_metadata(
                request,
                data['customer'],
                data['metadata'],
            )

    # Ask Stripe for the items that the user checked out with
    log.info(f"Getting items from a checkout session {data['id']}")
    async with aiohttp.ClientSession() as session:
        url = f"{STRIPE_BASE}/checkout/sessions/{data['id']}/line_items"
        auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
        resp = await session.get(url, auth=auth)
        line_items_object = await resp.json()
    line_items = line_items_object['data']

    # Grab the item from the database
    line_item_products: list[str] = [
        i['price']['product']
        for i in line_items
    ]
    async with vbu.Database() as db:
        items = [
            await CheckoutItem.fetch(db, stripe_product_id=p)
            for p in line_item_products
        ]
        if not items:
            log.info(f"Missing items {line_item_products} from database")
            return
    items = [
        i
        for i in items
        if i is not None
    ]

    # Get the customer data
    customer_data = await get_customer_by_id(
        request,
        data['customer'],
    )

    # Update our item as necessary based on the Stripe data
    for i in items:
        for o in line_items:
            if i.stripe_product_id == o['price']['product']:
                i.subscription = o['price']['type'] == "recurring"
                i.quantity = o['quantity']
                break

    # Throw all the relevant data to the specified webhook if this is the
    # first checkout
    if event_type == "checkout.session.completed":
        for item in items:
            json_data = {
                "product_name": item.name,
                "quantity": item.quantity,
                "refund": refunded,
                "subscription": item.subscription,
                **data['metadata'],
                **customer_data['metadata'],
                "subscription_expiry_time": None,
                "source": "Stripe",
                "subscription_delete_url": None,
            }
            if data.get('subscription'):
                json_data["subscription_delete_url"] = (
                    f"{STRIPE_BASE}/subscriptions/{data['subscription']}"
                )
            await send_webhook(item, json_data)

    # And log the transaction
    subscription_cancel_url: Optional[str] = None
    if data.get('subscription'):
        subscription_cancel_url = (
            f"{STRIPE_BASE}/subscriptions/"
            f"{data['subscription']}"
        )

    # This gets a little whacky and wild so let's strap in
    async with vbu.Database() as db:

        # For each item
        for i in items:

            # (unrelated, but log the transaction)
            if event_type.startswith("charge."):
                await log_transaction(
                    db,
                    product_id=i.id,
                    amount_gross=(
                        -data['amount_refunded']
                        if data.get('refunded', False)
                        else data['amount_captured']
                    ),
                    amount_net=(
                        data['amount_captured']
                        - data['amount_captured']
                        - (data.get('amount_refunded', 0) or 0)
                    ),
                    currency=data['currency'],
                    settle_amount=None,
                    settle_currency=None,
                    identifier=data['id'],
                    payment_processor="Stripe",
                    customer_email=data['billing_details']['email'],
                    metadata={
                        **data['metadata'],
                        **customer_data['metadata'],
                    },
                )

            # If the item is refunded
            if refunded:

                # See if we've already stored it
                current = await fetch_purchase(
                    db,
                    data['metadata']['discord_user_id'],
                    i.name,
                    guild_id=data['metadata'].get('discord_guild_id'),
                    stripe_id=stripe_account_id,
                )

                # If not, we're done
                if current is None:
                    continue

                # If so, delete
                await update_purchase(db, current['id'], delete=True)

            # Item isn't refunded
            else:

                # Is it a subscription?
                if subscription_cancel_url:

                    # Do we have it stored already?
                    current = await fetch_purchase(
                        db,
                        data['metadata']['discord_user_id'],
                        i.name,
                        guild_id=data['metadata'].get('discord_guild_id'),
                        stripe_id=stripe_account_id,
                    )

                    # Yes? Fantastic. Let's move on
                    if current:
                        continue

                # Not a subscription OR a subscription not stored already
                await create_purchase(
                    db,
                    data['metadata']['discord_user_id'],
                    i.name,
                    guild_id=data['metadata'].get('discord_guild_id'),
                    expiry_time=None,
                    cancel_url=subscription_cancel_url,
                    stripe_id=stripe_account_id,
                )


async def set_customer_metadata(
        request: Request,
        customer_id: str,
        metadata: dict) -> dict:
    """
    Get the checkout session object given its payment intent ID.
    """

    url = STRIPE_BASE + "/customers/{0}".format(customer_id)
    auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
    data = form_encode({"metadata": metadata})
    async with aiohttp.ClientSession() as session:
        resp = await session.post(url, data=data, auth=auth)
        response_json = await resp.json()
    return response_json


async def get_customer_by_id(
        request: Request,
        customer_id: str) -> dict:
    """
    Get the checkout session object given its payment intent ID.
    """

    url = f"{STRIPE_BASE}/customers/{customer_id}"
    auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
    async with aiohttp.ClientSession() as session:
        resp = await session.get(url, auth=auth)
        response_json = await resp.json()
    return response_json


async def get_checkout_session_from_payment_intent(
        request: Request,
        payment_intent_id: str) -> dict:
    """
    Get the checkout session object given its payment intent ID.
    """

    url = STRIPE_BASE + "/checkout/sessions"
    params = {"payment_intent": payment_intent_id}
    auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
    async with aiohttp.ClientSession() as session:
        resp = await session.get(url, params=params, auth=auth)
        response_json = await resp.json()
    return response_json['data'][0]


async def charge_refunded(
        request: Request,
        data: dict,
        stripe_account_id: str) -> None:
    """
    Pinged when a charge is refunded.
    """

    checkout_data = await get_checkout_session_from_payment_intent(
        request,
        data['payment_intent'],
    )
    await checkout_processor(
        request,
        checkout_data,
        stripe_account_id,
        refunded=True,
        event_type="charge.refunded",
    )


async def subscription_deleted(
        request: Request,
        data: dict,
        stripe_account_id: str) -> None:
    """
    Pinged when a subscription is deleted.
    """

    # Get subscription info
    subscription_expiry_time = data['current_period_end']
    subscription_item = data['items']['data'][0]

    # Get the product item so that we can grab its name
    async with vbu.Database() as db:
        item = await CheckoutItem.fetch(
            db,
            (product_name := subscription_item['price']['product']),
            stripe_id=stripe_account_id,
        )
    if item is None:
        log.info(f"Missing item {product_name} from database")
        return
    item.quantity = subscription_item['quantity']

    # Get the customer item so that we can get the user's Discord ID
    customer_data = await get_customer_by_id(request, data['customer'])

    # Throw our relevant data at the webhook
    json_data = {
        "product_name": item.name,
        "quantity": item.quantity,
        "refund": False,
        "subscription": True,
        **subscription_item['metadata'],
        **customer_data['metadata'],
        "subscription_expiry_time": subscription_expiry_time,
        "source": "Stripe",
        "subscription_delete_url": None,
    }
    await send_webhook(item, json_data)

    # And log the transaction
    async with vbu.Database() as db:
        current = await fetch_purchase(
            db,
            data['metadata']['discord_user_id'],
            item.name,
            guild_id=data['metadata'].get('discord_guild_id'),
            stripe_id=stripe_account_id,
        )
        if current is None:
            return
        await update_purchase(
            db,
            current['id'],
            expiry_time=subscription_expiry_time,
        )
