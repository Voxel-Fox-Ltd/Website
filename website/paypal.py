import json
from urllib.parse import parse_qs
from datetime import datetime as dt, timedelta
from typing import Tuple, Generator
import logging

import aiohttp
from aiohttp.web import Request, RouteTableDef, Response, json_response
from discord.ext import vbu
import pytz


from .utils.get_paypal_access_token import get_paypal_access_token
from .utils.db_util import CheckoutItem, store_transaction


routes = RouteTableDef()
log = logging.getLogger("voxelfox.paypal")
PAYPAL_BASE = "https://api-m.paypal.com"  # "https://api-m.sandbox.paypal.com"


"""
Just so I can have it written here with the rest of the relevant data, these
are the valid IPN transaction types (list taken from the IPN list).
https://developer.paypal.com/docs/ipn/integration-guide/IPNandPDTVariables/

* null - Chargeback
* adjustment - Dispute resolution

* cart - Payment received for multiple items
* express_checkout - Payment for a single item
* masspay - Payment sent using mass pay
* web_accept - Any of the buy now buttons

* merch_pmt - Monthly subscription payment via merchant

* mp_cancel - Billing agreement cancelled

* new_case - New dispute opened

* payout - Payout related to global shipping transaction

* pro_hosted - Payment received via "website payments pro hosted solution"
whatever that is

* recurring_payment - Recurring payment received
* recurring_payment_expired
* recurring_payment_failed
* recurring_payment_profile_cancel
* recurring_payment_profile_created
* recurring_payment_skipped
* recurring_payment_suspended
* recurring_payment_suspended_due_to_max_failed_payment

* send_money - Generic "payment recieved" eg if someone just sends money to
your account

* subscr_cancel - Cancelled subscription
* subscr_eot - Expired subscription
* subscr_failed - Failed subscription payment
* subscr_modify
* subscr_payment - Subscription payment received
* subscr_signup - Subscription signup (doesn't mean payment received)

* virtual_terminal - Payment received via virtual terminal
"""


@routes.post('/webhooks/paypal/create_checkout_session')
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
    async with vbu.Database() as db:
        item = await CheckoutItem.fetch(db, product_name)
    if not item:
        raise Exception(f"Missing item {product_name} from database")

    # Ask Stripe for the information about the item
    async with aiohttp.ClientSession() as session:
        url = f"https://api.stripe.com/v1/prices/{item.stripe_price_id}"
        auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
        async with session.get(url, auth=auth) as r:
            product_data = await r.json()
            if not r.ok:
                return json_response(
                    {},
                    status=500,
                    headers={"Access-Control-Allow-Origin": "*"},
                )

    # Ask PayPal to create a checkout session
    args = (
        request,
        quantity,
        item,
        product_data,
        metadata,
    )
    if item.subscription:
        data = await create_subscription_checkout_session(*args)
    else:
        data = await create_single_purchase_checkout_session(*args)
    if data.status == 500:
        return data

    # Give that back to the user
    if not data.text:
        raise Exception
    parsed: dict = json.loads(data.text)
    return json_response(
        {
            "subscription": item.subscription,
            "id": parsed['id'],
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def create_single_purchase_checkout_session(
        request: Request,
        quantity: int,
        checkout_item: CheckoutItem,
        product_data: dict,
        metadata: dict) -> Response:
    """
    Create a single checkout session item.
    """

    amount = {
        "currency_code": product_data['currency'],
        "value": str((product_data['unit_amount'] * quantity) / 100),
        "breakdown": {
            "item_total": {
                "currency_code": product_data['currency'],
                "value": str((product_data['unit_amount'] * quantity) / 100)
            },
            "shipping": {
                "currency_code": product_data['currency'],
                "value": "0",
            },
            "discount": {
                "currency_code": product_data['currency'],
                "value": "0",
            },
        }
    }
    item = {
        "name": checkout_item.name,
        "unit_amount": {
            "currency_code": product_data['currency'],
            "value": str(product_data['unit_amount'] / 100),
        },
        "quantity": str(quantity),
        "category": "DIGITAL_GOODS",
    }
    data = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": amount,
                "items": [item],
                "custom_id": json.dumps(metadata),
            }
        ]
    }

    # Ask PayPal for a session object
    async with aiohttp.ClientSession() as session:
        url = PAYPAL_BASE + "/v2/checkout/orders"
        auth = aiohttp.BasicAuth(
            request.app['config']['paypal_client_id'],
            request.app['config']['paypal_client_secret'],
        )
        async with session.post(url, json=data, auth=auth) as r:
            response = await r.json()
            if not r.ok:
                return json_response(response, status=500)

    # And return the session ID
    return json_response(response)


async def create_subscription_checkout_session(
        request: Request,
        quantity: int,
        checkout_item: CheckoutItem,
        product_data: dict,
        metadata: dict):
    """
    Create a single checkout session item.
    """

    # Make params to send to PayPal
    data = {
        "plan_id": checkout_item.paypal_plan_id,
        "quantity": str(quantity),
        "custom_id": json.dumps(metadata),
    }

    # Ask PayPal for a session object
    url = PAYPAL_BASE + "/v1/billing/subscriptions"
    auth = aiohttp.BasicAuth(
        request.app['config']['paypal_client_id'],
        request.app['config']['paypal_client_secret'],
    )
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, auth=auth) as r:
            response = await r.json()
            if not r.ok:
                return json_response(response, status=500)

    # And return the session ID
    return json_response(response)


@routes.post('/webhooks/paypal/purchase_ipn_new')
async def paypal_ipn_complete(request: Request):
    """
    Handles Paypal throwing data my way.
    """

    # Get the data from the post request
    content_bytes: bytes = await request.content.read()
    paypal_data_string: str = content_bytes.decode()
    paypal_data: dict
    try:
        paypal_data = {
            i.strip(): o[0].strip()
            for i, o in parse_qs(paypal_data_string).items()
        }
    except Exception:
        paypal_data = {'receiver_email': '@business.example.com'}

    # Let's throw that into a logger
    log.info(f"Data from PayPal: {json.dumps(paypal_data_string)}")

    # Get the right URL based on whether this is a sandbox payment or not
    use_sandbox = (
        paypal_data['receiver_email'].casefold()
        .endswith('@business.example.com')
    )
    paypal_url = {
        False: "https://ipnpb.paypal.com/cgi-bin/webscr",
        True: "https://ipnpb.sandbox.paypal.com/cgi-bin/webscr",
    }[use_sandbox]

    # Send the data back to PayPal to make sure it's valid
    data_send_back = "cmd=_notify-validate&" + paypal_data_string
    async with aiohttp.ClientSession() as session:
        resp = await session.post(paypal_url, data=data_send_back)
        site_data = await resp.read()
        if site_data.decode() != "VERIFIED":
            # Fake data, but PayPal expects a 200
            return Response(status=200)

    # Process the data
    event = paypal_data.get('txn_type')
    charge_capture_events = [
        "cart",
        "express_checkout",
        "web_accept",
        None,
    ]
    subscription_create_events = [
        "recurring_payment_profile_created",
        "recurring_payment",
    ]
    subscription_cancel_events = [
        "recurring_payment_profile_cancel",
        "recurring_payment_suspended",
        "recurring_payment_suspended_due_to_max_failed_payment",
    ]
    if event in charge_capture_events:
        await charge_captured(request, paypal_data)  # Also refunds
    elif event in subscription_create_events:
        await subscription_created(request, paypal_data)
    elif event in subscription_cancel_events:
        await subscription_deleted(request, paypal_data)
    else:
        log.info(f"Unhandled PayPal event '{event}'")

    # And we have no more events to process
    return Response(status=200)


def get_local_datetime_from_string(string: str) -> dt:
    """
    Gets a datetime object from a PayPal purchase time string.
    """

    *time_string, zone_string = string.split(" ")
    time_string = " ".join(time_string)
    date = dt.strptime(time_string, "%H:%M:%S %B %d, %Y")
    zone = {
        "PST": pytz.timezone("US/Pacific"),
        "PDT": pytz.timezone("US/Pacific"),
    }.get(zone_string, pytz.utc)
    date = date.replace(tzinfo=zone)  # PayPal always uses PST (and PDT)
    return date


def get_standard_format_datetime(datetime: dt) -> str:
    return datetime.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_datetime_from_standard_format(string: str) -> dt:
    return dt.strptime(string, "%Y-%m-%dT%H:%M:%SZ")


def get_time_around_datetime(datetime: dt) -> Tuple[dt, dt]:
    constructor = (datetime.year, datetime.month, datetime.day,)
    return (
        dt(*constructor),
        dt(*constructor) + timedelta(days=1),
    )


async def get_subscription_by_subscription_id(
        request: Request,
        subscription_id: str) -> dict:
    """
    Get the information for a subscription (not a plan) given its ID.
    """

    access_token = await get_paypal_access_token(request)
    async with aiohttp.ClientSession() as session:
        url = f"{PAYPAL_BASE}/v1/billing/subscriptions/{subscription_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = await session.get(url, headers=headers)
        return await resp.json()


def get_products_from_charge(data: dict) -> Generator[dict, None, None]:
    """
    Get the products from a given charge object.
    """

    if "item_name" in data:
        yield {
            "name": data['item_name'],
            "quantity": int(data.get("quantity", 1)),
        }
    if "product_name" in data:
        yield {
            "name": data['product_name'],
            "quantity": 1,
        }
    index = 1
    while f"item_name{index}" in data:
        yield {
            "name": data[f'item_name{index}'],
            "quantity": int(data.get(f"quantity{index}", 1)),
        }
        index += 1
    return


async def charge_captured(request: Request, data: dict):
    """
    Pinged when a user purchases an object via checkout.
    """

    # See if they're refunded
    refunded = data['payment_status'] in ['Denied', 'Refunded', 'Reversed']

    # Grab the metadata from the request
    metadata = json.loads(data.get("custom_id", "{}"))
    metadata.update(json.loads(data.get("custom", "{}")))

    # See if it's a subscription refund
    if data.get('recurring_payment_id'):
        recurring_payment_info = await get_subscription_by_subscription_id(
            request,
            data['recurring_payment_id'],
        )
        metadata.update(json.loads(recurring_payment_info.get("custom_id", "{}")))
        metadata.update(json.loads(recurring_payment_info.get("custom", "{}")))

    # Grab the data from the database for each of the items
    products = get_products_from_charge(data)
    async with vbu.Database() as db:
        item_list = [
            await CheckoutItem.fetch(db, i['name'])
            for i in products
        ]
    item_list = [i for i in item_list if i]

    # Fix up those dicts to include quantity
    for i in item_list:
        for p in products:
            if i.name == p['name']:
                i.quantity = p['quantity']
                break  # Only break out of the inner loop

    # And send a POST request for each of the items
    db_data = []
    async with aiohttp.ClientSession() as session:
        for item in item_list:

            # Only bother if we have a webhook
            if not item.webhook:
                log.info(f"No transaction webhook for {item.name}")
                continue

            # Build our send data
            headers = {
                "Authorization":
                item.webhook_auth,
            }
            json_data = {
                "product_name": item.name,
                "quantity": item.quantity,
                "refund": refunded,
                "subscription": False,
                **metadata,
                "subscription_expiry_time": None,
                "source": "PayPal",
                "subscription_delete_url": None,
            }
            db_data.append((dt.utcnow(), 'PayPal', json_data,))
            log.info(f"Sending POST {item.webhook} {json_data}")

            # And request
            kwargs = {
                "json": json_data,
                "headers": headers
            }
            resp = await session.post(item.webhook, **kwargs)
            body = await resp.read()
            log.info(f"POST {item.webhook} returned {resp.status} {body}")

    # Add these transactions to the database
    async with vbu.Database() as db:
        for d in db_data:
            await store_transaction(db, *d)


async def subscription_created(request: Request, data: dict):
    """
    Pigned when a user creates a new subscription purchase.
    """

    # Get the data from the subscription
    product_name = data['product_name']
    recurring_payment_id = data['recurring_payment_id']

    # Get the recurring payment info
    recurring_payment_info = await get_subscription_by_subscription_id(
        request,
        recurring_payment_id,
    )
    metadata = json.loads(recurring_payment_info.get('custom_id', "{}"))
    metadata.update(json.loads(recurring_payment_info.get('custom', "{}")))

    # Grab the data from the database
    async with vbu.Database() as db:
        item = await CheckoutItem.fetch(db, product_name)
    if item is None:
        raise Exception(f"Unknown product {product_name}")

    # And send a POST request for the item
    async with aiohttp.ClientSession() as session:
        if not item.webhook:
            log.info(f"No transaction webhook for {item.name}")
            return
        headers = {"Authorization": item.webhook_auth}
        json_data = {
            "product_name": item.name,
            "quantity": item.quantity,
            "refund": False,
            "subscription": True,
            **metadata,
            "subscription_expiry_time": None,
            "source": "PayPal",
            "subscription_delete_url": f"{PAYPAL_BASE}/v1/billing/subscriptions/{recurring_payment_id}/cancel",
        }
        async with vbu.Database() as db:
            await store_transaction(db, dt.utcnow(), 'PayPal', json_data)
        log.info(f"Sending POST {item.webhook} {json_data}")
        resp = await session.post(item.webhook, json=json_data, headers=headers)
        body = await resp.read()
        log.info(f"POST {item.webhook} returned {resp.status} {body}")


async def subscription_deleted(request: Request, data: dict):
    """
    Pinged when a user cancels their subscription.
    """

    # Get the data from the subscription
    product_name = data['product_name']
    recurring_payment_id = data['recurring_payment_id']

    # Get the recurring payment info
    recurring_payment_info = await get_subscription_by_subscription_id(
        request,
        recurring_payment_id,
    )
    metadata = json.loads(recurring_payment_info.get('custom_id', "{}"))
    metadata.update(json.loads(recurring_payment_info.get('custom', "{}")))

    # Grab the data from the database
    async with vbu.Database() as db:
        item = await CheckoutItem.fetch(db, product_name)
    if item is None:
        raise Exception(f"Unknown product name {product_name}")

    # Get the last payment time
    payment_time_str = recurring_payment_info['billing_info']['last_payment']['time']
    last_purchase = get_datetime_from_standard_format(payment_time_str)
    expiry_time = last_purchase + timedelta(days=30)

    # And send a POST request for the item
    async with aiohttp.ClientSession() as session:
        if not item.webhook:
            log.info(f"No transaction webhook for {item.name}")
            return
        headers = {"Authorization": item.webhook_auth}
        json_data = {
            "product_name": item.name,
            "quantity": item.quantity,
            "refund": False,
            "subscription": True,
            **metadata,
            "subscription_expiry_time": expiry_time.timestamp(),
            "source": "PayPal",
            "subscription_delete_url": None,
        }
        async with vbu.Database() as db:
            await store_transaction(db, dt.utcnow(), 'PayPal', json_data)
        log.info(f"Sending POST {item.webhook} {json_data}")
        resp = await session.post(item.webhook, json=json_data, headers=headers)
        body = await resp.read()
        log.info(f"POST {item.webhook} returned {resp.status} {body}")
