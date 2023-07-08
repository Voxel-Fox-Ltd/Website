import asyncio
import json
import hmac
from hashlib import sha256
import logging
from typing import Any, Literal, TypedDict, cast
from datetime import datetime as dt

import aiohttp
from aiohttp.web import Request, RouteTableDef, Response, json_response
from discord.ext import vbu

from website.utils.db_models import User, Purchase

from .utils import (
    types,
    CheckoutItem,
    Purchase,
    send_webhook,
)


routes = RouteTableDef()
log = logging.getLogger("vbu.voxelfox.stripe")
STRIPE_BASE = "https://api.stripe.com/v1"


def _get_dict_key(base, key, index=None):
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
            dk = _get_dict_key(base, key)
            output_dict[dk] = value
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                dk = _get_dict_key(base, key, index)
                if isinstance(item, (str, int)):
                    output_dict[dk] = item
                else:
                    output_dict.update(form_encode(item, dk))
        else:
            dk = _get_dict_key(base, key)
            output_dict.update(form_encode(value, dk))
    return output_dict


CheckoutSessionJson = TypedDict(
    "CheckoutSessionJson",
    product_id=str, quantity=int, user_id=str,
)


@routes.post('/webhooks/stripe/create_checkout_session')
async def create_checkout_session(request: Request):
    """
    Create a checkout session for the user.
    This is meant for use with the internal API (though I don't verify since
    the worst case is that people make fake invboices for themselves).
    """

    # Get their post data for the item name
    post_data: CheckoutSessionJson = await request.json()
    product_id: str = post_data.pop("product_id", None)  # pyright: ignore
    quantity: int = post_data.pop("quantity", 1)  # pyright: ignore

    # Get the user's login details for metadata
    if "user_id" not in post_data:
        raise Exception("Missing user ID from POST request")
    if product_id is None:
        raise Exception("Missing product ID from POST request")

    # Get the item data from the database
    async with vbu.Database() as db:
        item = await CheckoutItem.fetch(db, id=product_id)
    if item is None:
        raise Exception(f"Missing item {product_id} from database")
    stripe_id: str | None = (
        item.user.stripe_id
        if item.user and item.user.stripe_id
        else None
    )  # For use in the API key header for multiple accounts

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
        "metadata": post_data,
    }
    if item.subscription:
        json_data.update({
            "subscription_data": {"metadata": post_data},
        })
    else:
        json_data.update({
            "invoice_creation": {
                "enabled": True,
                "invoice_data": {"metadata": post_data},
            },
        })

    # Send some data to Stripe
    async with aiohttp.ClientSession() as session:

        # Ask Stripe for a session object
        url = f"{STRIPE_BASE}/checkout/sessions"
        form_data = form_encode(json_data)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if stripe_id:
            headers["Stripe-Account"] = stripe_id
        auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
        resp = await session.post(url, data=form_data, headers=headers, auth=auth)
        response = await resp.json()
        if not resp.ok:
            return json_response(
                response,
                status=500,
                headers={"Access-Control-Allow-Origin": "*"},
            )

    # And while we're here, add a User ID to the customer's metadata
    if response["customer"]:
        await set_customer_metadata(
            request,
            customer_id=response["customer"],
            metadata={"user_id": post_data["user_id"]},
            stripe_account_id=stripe_id,
        )

    # And return the session ID
    href_url = f"https://checkout.stripe.com/pay/{response['id']}"
    return json_response(
        {
            "href": href_url,
            "id": response["id"],
            **response,
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )


def check_stripe_signature(
    request: Request,
    data_string: bytes) -> bool:
    """
    Check whether or not the given signature is valid for a Stripe webhook.

    Parameters
    ----------
    request : aiohttp.web.Request
        The request that sent the webhook.
    data_string : bytes
        The original data that was sent to the endpoint.
    """

    # Build the signature dict
    signature = dict([
        i.strip().split("=", 1)
        for i in request.headers['Stripe-Signature'].split(",")
    ])

    # Sign the payload
    signed_payload = signature['t'] + '.' + data_string.decode()

    # Get the signing secret
    data = json.loads(data_string.decode())
    if data.get("account") is None:
        signing_secret = request.app['config']['stripe_account_webhook_signing_secret']
    else:
        signing_secret = request.app['config']['stripe_webhook_signing_secret']

    # Hash and compare the payload
    mac = hmac.new(signing_secret.encode(), signed_payload.encode(), sha256)
    hashed = mac.hexdigest()
    return hmac.compare_digest(hashed.encode(), signature['v1'].encode())


@routes.post('/webhooks/stripe/purchase_webhook')
async def stripe_purchase_complete(request: Request):
    """
    Handles Stripe throwing data my way.
    """

    # Get the data from the post request
    stripe_data_string = await request.read()
    stripe_data: types.Event[types.CheckoutSession | types.Charge | types.Subscription]
    stripe_data = json.loads(stripe_data_string.decode())

    # Let's throw that into a logger
    log.info(f"Data from Stripe: {json.dumps(stripe_data)}")

    # Check the signature to make sure it's valid
    if not check_stripe_signature(request, stripe_data_string):
        log.info("Invalid data sent to Stripe webhook url")
        return Response(status=400)

    # Handle each checkout event
    event = stripe_data['type']
    data_object = stripe_data["data"]["object"]
    if event in [
            "checkout.session.completed",
            "charge.captured",
            "charge.succeeded",
            "charge.refunded"]:
        data_object = cast(types.CheckoutSession | types.Charge, data_object)
        await checkout_processor(
            request,
            data_object,
            stripe_data.get("account"),
            event_type=event,  # pyright: ignore
        )
    elif event == "customer.subscription.deleted":
        data_object = cast(types.Subscription, data_object)
        await subscription_deleted(
            request,
            data_object,
            stripe_data.get("account"),
        )
    else:
        log.info(f"Unhandled Stripe event '{event}'")

    # And we have no more events to process
    return Response(status=200)


async def checkout_processor(
        request: Request,
        data: types.Charge | types.CheckoutSession,
        stripe_account_id: str | None,
        event_type: Literal["charge.captured", "charge.succeeded", "checkout.session.completed", "charge.refunded"]) -> None:
    """
    Pinged when a charge is successfully recieved, _including_ subscriptions.

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
        data = cast(types.CheckoutSession, data)
        if data["mode"] == "subscription":
            await set_customer_metadata(
                request,
                data["customer"],
                data["metadata"],
                stripe_account_id,
            )

    # Ask Stripe for the items that the user checked out with
    auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
    headers = {}
    if stripe_account_id:
        headers["Stripe-Account"] = stripe_account_id
    if data["invoice"]:
        log.info(f"Getting items from an invoice {data['invoice']}")
        async with aiohttp.ClientSession() as session:
            url = f"{STRIPE_BASE}/invoices/{data['invoice']}"
            resp = await session.get(url, auth=auth, headers=headers)
            invoice_object = await resp.json()
            log.info(f"Invoice object: {json.dumps(invoice_object)}")
            line_items_object = invoice_object["lines"]
    elif data["object"] == "checkout.session":
        data = cast(types.CheckoutSession, data)
        log.info(f"Getting items from an checkout session {data['id']}")
        async with aiohttp.ClientSession() as session:
            url = f"{STRIPE_BASE}/checkout/sessions/{data['id']}/line_items"
            resp = await session.get(url, auth=auth, headers=headers)
            session_object = await resp.json()
            log.info(f"Session object: {json.dumps(session_object)}")
            line_items_object = session_object
    elif data["object"] == "charge":
        data = cast(types.CheckoutSession, data)
        log.info(f"Getting items from a charge {data['id']} via payment intent {data['payment_intent']}")
        async with aiohttp.ClientSession() as session:
            url = (
                f"{STRIPE_BASE}/payment_intents/{data['payment_intent']}?"
                "expand[]=invoice"
            )
            resp = await session.get(url, auth=auth, headers=headers)
            session_object = await resp.json()
            log.info(f"Charge object: {json.dumps(session_object)}")
            line_items_object = session_object["invoice"]["lines"]
    else:
        log.critical(f"Failed to get line items for purchase ({data['object']}).")
        return
    line_items: list[types.InvoiceLineItem | types.CheckoutSessionLineItem]
    line_items = line_items_object["data"]

    # Grab the item from the database
    line_item_products: list[str] = [
        i["price"]["product"]
        for i in line_items
    ]
    async with vbu.Database() as db:
        items = [
            await CheckoutItem.fetch_by_stripe_product_id(db, p)
            for p in line_item_products
        ]
    if not items:
        log.info(f"Missing items {line_item_products} from database")
        return
    items = [i for i in items if i is not None]  # remove None

    # Get the customer data so that we have a full set of metadata
    customer_data = await get_customer_by_id(
        request,
        data["customer"],
        stripe_account_id,
    )
    all_metadata = {
        **customer_data["metadata"],
        **data["metadata"],
    }

    # Update our item as necessary based on the Stripe data
    for purchased in items:
        for line in line_items:
            if purchased.stripe_product_id == line["price"]["product"]:
                purchased.subscription = line["price"]["type"] == "recurring"
                purchased.purchased_quantity = line["quantity"]
                break
        else:
            log.warning(f"Line item not found for {purchased!r}")

    # And log the transaction
    subscription_id: str | None = None
    if "subscription" in data and data["subscription"]:  # pyright: ignore
        data = cast(types.CheckoutSession, data)
        subscription_id = data["subscription"]
    else:
        for i in line_items:
            if "subscription" in i:
                i = cast(types.InvoiceLineItem, i)
                subscription_id = i["subscription"]
                break

    # Update our storage
    async with vbu.Database() as db:
        for i in items:
            if event_type != "charge.refunded":
                try:
                    user_id: str = all_metadata["user_id"]
                except KeyError:
                    continue  # No user ID in charge
                user = await User.fetch(db, id=user_id)
                assert user
                current = None
                if subscription_id:
                    current = await Purchase.fetch_by_identifier(db, subscription_id)
                else:
                    current = await Purchase.fetch_by_user(
                        db, user, i,
                        discord_guild_id=all_metadata.get("discord_guild_id"),
                    )
                if current:
                    log.info("Ignoring purchase that is already stored.")
                    continue  # Already stored
                current = await Purchase.create(
                    db,
                    user=user,
                    product=i,
                    discord_guild_id=all_metadata.get('discord_guild_id'),
                    expiry_time=None,
                    cancel_url=(
                        f"{STRIPE_BASE}/subscriptions/{subscription_id}"
                        if subscription_id else None
                    ),
                    identifier=subscription_id or data["id"],
                    quantity=i.purchased_quantity,
                )
            else:
                data = cast(types.Charge, data)
                current = await Purchase.fetch_by_identifier(
                    db,
                    data["refunds"]["data"][0]["charge"],
                )
                if current is None:
                    log.info("Cannot delete item that is not currently stored.")
                    continue
                await current.delete(db)
                user = await current.fetch_user(db)

            json_data = {
                "product_name": i.name,
                "quantity": i.purchased_quantity,
                "refund": event_type == "charge.refunded",
                "subscription": i.subscription,
                **all_metadata,
                "subscription_expiry_time": None,
                "source": "Stripe",
                "subscription_delete_url": None,
                "discord_user_id": user.discord_user_id,
                "discord_guild_id": current.discord_guild_id,
            }
            if data.get("subscription"):
                data = cast(types.CheckoutSession, data)
                json_data["subscription_delete_url"] = (
                    f"{STRIPE_BASE}/subscriptions/{data['subscription']}"
                )
            asyncio.create_task(send_webhook(i, json_data))


async def set_customer_metadata(
        request: Request,
        customer_id: str,
        metadata: dict,
        stripe_account_id: str | None) -> dict[str, Any]:
    """
    Get the checkout session object given its payment intent ID.
    """

    url = STRIPE_BASE + "/customers/{0}".format(customer_id)
    auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
    data = form_encode({"metadata": metadata})
    headers = {}
    if stripe_account_id:
        headers["Stripe-Account"] = stripe_account_id
    async with aiohttp.ClientSession() as session:
        resp = await session.post(url, data=data, auth=auth, headers=headers)
        response_json = await resp.json()
    return response_json


async def get_customer_by_id(
        request: Request,
        customer_id: str,
        stripe_account_id: str | None) -> dict[str, Any]:
    """
    Get a Stripe customer object given their user ID.
    """

    url = f"{STRIPE_BASE}/customers/{customer_id}"
    auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
    headers = {}
    if stripe_account_id:
        headers["Stripe-Account"] = stripe_account_id
    async with aiohttp.ClientSession() as session:
        resp = await session.get(url, auth=auth, headers=headers)
        response_json = await resp.json()
    return response_json


async def subscription_deleted(
        request: Request,
        data: types.Subscription,
        stripe_account_id: str | None) -> None:
    """
    Pinged when a subscription is deleted.
    """

    # Get subscription info
    subscription_expiry_time = data["current_period_end"]
    subscription_item = data["items"]["data"][0]

    # Get the product item so that we can grab its name
    product_id: str
    async with vbu.Database() as db:
        item = await CheckoutItem.fetch_by_stripe_product_id(
            db,
            product_id := subscription_item["price"]["product"],
        )
    if item is None:
        log.info(f"Missing item {product_id} from database")
        return
    item.quantity = subscription_item["quantity"]

    # Get the customer item so that we can get the user's Discord ID
    customer_data = await get_customer_by_id(
        request,
        data["customer"],
        stripe_account_id,
    )
    all_metadata = {
        **customer_data["metadata"],
        **subscription_item["metadata"],
    }

    # And log the transaction
    async with vbu.Database() as db:
        user_id = all_metadata["user_id"]
        user = await User.fetch(db, id=user_id)
        assert user
        current = await Purchase.fetch_by_user(
            db,
            user,
            item,
            discord_guild_id=all_metadata.get("discord_guild_id"),
        )
        if not current:
            return
        await current[0].update(
            db,
            expiry_time=dt.fromtimestamp(subscription_expiry_time),
        )

        json_data = {
            "product_name": item.name,
            "quantity": item.quantity,
            "refund": False,
            "subscription": True,
            **all_metadata,
            "subscription_expiry_time": subscription_expiry_time,
            "source": "Stripe",
            "subscription_delete_url": None,
            "discord_user_id": user.discord_user_id,
            "discord_guild_id": current[0].discord_guild_id,
        }
        asyncio.create_task(send_webhook(item, json_data))
