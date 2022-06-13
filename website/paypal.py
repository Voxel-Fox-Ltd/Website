import json
from urllib.parse import parse_qs
from datetime import datetime as dt, timedelta
import typing

import aiohttp
from aiohttp.web import Request, RouteTableDef, Response, json_response
import pytz

from .utils.get_paypal_access_token import get_paypal_access_token


routes = RouteTableDef()
PAYPAL_BASE = "https://api-m.paypal.com"  # "https://api-m.sandbox.paypal.com"



"""
Just so I can have it written here with the rest of the relevant data, these are the valid IPN transaction types
(list taken from https://developer.paypal.com/docs/ipn/integration-guide/IPNandPDTVariables/#id08CTB0S055Z)

null - Chargeback
adjustment - Dispute resolution

cart - Payment received for multiple items
express_checkout - Payment for a single item
masspay - Payment sent using mass pay
web_accept - Any of the buy now buttons

merch_pmt - Monthly subscription payment via merchant

mp_cancel - Billing agreement cancelled

new_case - New dispute opened

payout - Payout related to global shipping transaction

pro_hosted - Payment received via "website payments pro hosted solution" whatever that is

recurring_payment - Recurring payment received
recurring_payment_expired
recurring_payment_failed
recurring_payment_profile_cancel
recurring_payment_profile_created
recurring_payment_skipped
recurring_payment_suspended
recurring_payment_suspended_due_to_max_failed_payment

send_money - Generic "payment recieved" eg if someone just sends money to your account

subscr_cancel - Cancelled subscription
subscr_eot - Expired subscription
subscr_failed - Failed subscription payment
subscr_modify
subscr_payment - Subscription payment received
subscr_signup - Subscription signup (doesn't mean payment received)

virtual_terminal - Payment received via virtual terminal
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
    async with request.app['database']() as db:
        item_rows = await db(
            """SELECT * FROM checkout_items WHERE product_name=$1""",
            product_name,
        )
    if not item_rows:
        raise Exception(f"Missing item {product_name} from database")
    item_row = item_rows[0]

    # Ask Stripe for the information about the item
    async with aiohttp.ClientSession() as session:
        url = f"https://api.stripe.com/v1/prices/{item_row['stripe_price_id']}"
        auth = aiohttp.BasicAuth(request.app['config']['stripe_api_key'])
        async with session.get(url, auth=auth) as r:
            product_data = await r.json()
            if not r.ok:
                return json_response({}, status=500, headers={"Access-Control-Allow-Origin": "*"})

    # Ask PayPal for the right data
    if item_row['subscription']:
        data = await create_subscription_checkout_session(request, product_name, quantity, item_row, product_data, metadata)
    else:
        data = await create_single_purchase_checkout_session(request, product_name, quantity, item_row, product_data, metadata)
    if data.status == 500:
        return data
    data = json.loads(data.text)
    return json_response({"subscription": item_row['subscription'], "id": data['id']}, headers={"Access-Control-Allow-Origin": "*"})


async def create_single_purchase_checkout_session(
        request: Request,
        product_name: str,
        quantity: int,
        item_row: dict,
        product_data: dict,
        metadata: dict):
    """
    Create a single checkout session item.
    """

    # Make params to send to PayPal
    data = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": product_data['currency'],
                    "value": str((product_data['unit_amount'] * quantity) / 100),
                    "breakdown": {
                        "item_total": {
                            "currency_code": product_data['currency'],
                            "value": str((product_data['unit_amount'] * quantity) / 100)
                        },
                        "shipping": {"currency_code": product_data['currency'], "value": "0"},
                        "discount": {"currency_code": product_data['currency'], "value": "0"},
                    }
                },
                "items": [
                    {
                        "name": item_row['product_name'],
                        "unit_amount": {
                            "currency_code": product_data['currency'],
                            "value": str(product_data['unit_amount'] / 100),
                        },
                        "quantity": str(quantity),
                        "category": "DIGITAL_GOODS",
                    }
                ],
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
        product_name: str,
        quantity: int,
        item_row: dict,
        product_data: dict,
        metadata: dict):
    """
    Create a single checkout session item.
    """

    # Make params to send to PayPal
    data = {
        "plan_id": item_row['paypal_plan_id'],
        "quantity": str(quantity),
        "custom_id": json.dumps(metadata),
    }

    # Ask PayPal for a session object
    async with aiohttp.ClientSession() as session:
        url = PAYPAL_BASE + "/v1/billing/subscriptions"
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


@routes.post('/webhooks/paypal/purchase_ipn_new')
async def paypal_ipn_complete(request: Request):
    """
    Handles Paypal throwing data my way.
    """

    # Get the data from the post request
    content_bytes: bytes = await request.content.read()
    paypal_data_string: str = content_bytes.decode()
    try:
        paypal_data = {i.strip(): o[0].strip() for i, o in parse_qs(paypal_data_string).items()}
    except Exception:
        paypal_data = {'receiver_email': '@business.example.com'}

    # Let's throw that into a logger
    request.app['logger'].debug(f"Data from PayPal: {paypal_data_string}")

    # Send the data back to PayPal to make sure it's valid
    data_send_back = "cmd=_notify-validate&" + paypal_data_string
    async with aiohttp.ClientSession(loop=request.app.loop) as session:

        # Get the right URL based on whether this is a sandbox payment or not
        paypal_url = {
            False: "https://ipnpb.paypal.com/cgi-bin/webscr",
            True: "https://ipnpb.sandbox.paypal.com/cgi-bin/webscr",
        }[paypal_data['receiver_email'].casefold().endswith('@business.example.com')]

        # Send the data back to check it
        async with session.post(paypal_url, data=data_send_back) as site:
            site_data = await site.read()
            if site_data.decode() != "VERIFIED":
                request.app['logger'].info("Invalid data sent to PayPal IPN url")
                return Response(status=200)  # Oh no it was fake data

    # Process the data
    event = paypal_data.get('txn_type')
    if event in ["cart", "express_checkout", "web_accept", None]:
        request.app['logger'].info("charge captured")
        await charge_captured(request, paypal_data)  # Also refunds
    elif event == "recurring_payment_profile_created":
        request.app['logger'].info("subscritpion created")
        await subscription_created(request, paypal_data)
    elif event in [
            "recurring_payment_profile_cancel", "recurring_payment_suspended",
            "recurring_payment_suspended_due_to_max_failed_payment"]:
        request.app['logger'].info("subscrpitpin stopped")
        await subscription_deleted(request, paypal_data)

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


def get_time_around_datetime(datetime: dt) -> typing.Tuple[dt, dt]:
    return (
        dt(datetime.year, datetime.month, datetime.day),
        dt(datetime.year, datetime.month, datetime.day) + timedelta(days=1),
    )


async def get_subscription_by_subscription_id(request: Request, subscription_id: str) -> dict:
    """
    Get the information for a subscription (not a plan) given its ID.
    """

    access_token = await get_paypal_access_token(request)
    async with aiohttp.ClientSession() as session:
        url = PAYPAL_BASE + "/v1/billing/subscriptions/{0}".format(subscription_id)
        headers = {"Authorization": f"Bearer {access_token}"}
        async with session.get(url, headers=headers) as r:
            response_data = await r.json()
    return response_data


def get_products_from_charge(data: dict):
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

    # Get the purchased items
    products = list(get_products_from_charge(data))

    # See if they're refunded
    refunded = data['payment_status'] in ['Denied', 'Refunded', 'Reversed']

    # Grab the metadata from the request
    metadata = json.loads(data.get("custom_id", "{}"))
    metadata.update(json.loads(data.get("custom", "{}")))

    # See if it's a subscription refund
    if data.get('recurring_payment_id'):
        recurring_payment_info = await get_subscription_by_subscription_id(request, data['recurring_payment_id'])
        metadata.update(json.loads(recurring_payment_info.get("custom_id", "{}")))
        metadata.update(json.loads(recurring_payment_info.get("custom", "{}")))

    # Grab the data from the database for each of the items
    async with request.app['database']() as db:
        item_rows = await db(
            """SELECT * FROM checkout_items WHERE product_name=ANY($1::TEXT[])""",
            [i['name'] for i in products],
        )

    # Fix up those dicts to include quantity
    item_rows = [dict(i) for i in item_rows]
    for i in item_rows:
        for p in products:
            if i['product_name'] == p['name']:
                i['quantity'] = p['quantity']
                break

    # And send a POST request for each of the items
    async with aiohttp.ClientSession() as session:
        async with request.app['database']() as db:
            for row in item_rows:
                if not row['transaction_webhook']:
                    request.app['logger'].info(f"No transaction webhook for {row['product_name']}")
                    continue
                headers = {"Authorization": row['transaction_webhook_authorization']}
                json_data = {
                    "product_name": row['product_name'],
                    "quantity": row['quantity'],
                    "refund": refunded,
                    "subscription": False,
                    **metadata,
                    "subscription_expiry_time": None,
                    "source": "PayPal",
                    "subscription_delete_url": None,
                }
                await db.call(
                    """INSERT INTO transactions (timestamp, data) VALUES ($1, $2)""",
                    dt.utcnow(), json_data,
                )
                request.app['logger'].info(f"Sending POST {row['transaction_webhook']} {json_data}")
                async with session.post(row['transaction_webhook'], json=json_data, headers=headers) as r:
                    body = await r.read()
                    request.app['logger'].info(f"POST {row['transaction_webhook']} returned {r.status} {body}")


async def subscription_created(request: Request, data: dict):
    """
    Pigned when a user creates a new subscription purchase.
    """

    # Get the data from the subscription
    product_name = data['product_name']
    recurring_payment_id = data['recurring_payment_id']

    # Get the recurring payment info
    recurring_payment_info = await get_subscription_by_subscription_id(request, recurring_payment_id)
    metadata = json.loads(recurring_payment_info.get('custom_id', "{}"))
    metadata.update(json.loads(recurring_payment_info.get('custom', "{}")))

    # Grab the data from the database
    async with request.app['database']() as db:
        item_rows = await db(
            """SELECT * FROM checkout_items WHERE product_name=$1""",
            product_name
        )
    item = item_rows[0]

    # And send a POST request for the item
    async with aiohttp.ClientSession() as session:
        if not item['transaction_webhook']:
            request.app['logger'].info(f"No transaction webhook for {item['product_name']}")
            return
        headers = {"Authorization": item['transaction_webhook_authorization']}
        json_data = {
            "product_name": product_name,
            "quantity": 1,
            "refund": False,
            "subscription": True,
            **metadata,
            "subscription_expiry_time": None,
            "source": "PayPal",
            "subscription_delete_url": f"{PAYPAL_BASE}/v1/billing/subscriptions/{recurring_payment_id}/cancel",
        }
        async with request.app['database']() as db:
            await db.call(
                """INSERT INTO transactions (timestamp, data) VALUES ($1, $2)""",
                dt.utcnow(), json_data,
            )
        request.app['logger'].info(f"Sending POST {item['transaction_webhook']} {json_data}")
        async with session.post(item['transaction_webhook'], json=json_data, headers=headers) as r:
            body = await r.read()
            request.app['logger'].info(f"POST {item['transaction_webhook']} returned {r.status} {body}")


async def subscription_deleted(request: Request, data: dict):
    """
    Pinged when a user cancels their subscription.
    """

    # Get the data from the subscription
    product_name = data['product_name']
    recurring_payment_id = data['recurring_payment_id']

    # Get the recurring payment info
    recurring_payment_info = await get_subscription_by_subscription_id(request, recurring_payment_id)
    metadata = json.loads(recurring_payment_info.get('custom_id', "{}"))
    metadata.update(json.loads(recurring_payment_info.get('custom', "{}")))

    # Grab the data from the database
    async with request.app['database']() as db:
        item_rows = await db(
            """SELECT * FROM checkout_items WHERE product_name=$1""",
            product_name
        )
    item = item_rows[0]

    # Get the last payment time
    last_purchase = get_datetime_from_standard_format(recurring_payment_info['billing_info']['last_payment']['time'])
    expiry_time = last_purchase + timedelta(days=30)

    # And send a POST request for the item
    async with aiohttp.ClientSession() as session:
        if not item['transaction_webhook']:
            request.app['logger'].info(f"No transaction webhook for {item['product_name']}")
            return
        headers = {"Authorization": item['transaction_webhook_authorization']}
        json_data = {
            "product_name": product_name,
            "quantity": 1,
            "refund": False,
            "subscription": True,
            **metadata,
            "subscription_expiry_time": expiry_time.timestamp(),
            "source": "PayPal",
            "subscription_delete_url": None,
        }
        async with request.app['database']() as db:
            await db.call(
                """INSERT INTO transactions (timestamp, data) VALUES ($1, $2)""",
                dt.utcnow(), json_data,
            )
        request.app['logger'].info(f"Sending POST {item['transaction_webhook']} {json_data}")
        async with session.post(item['transaction_webhook'], json=json_data, headers=headers) as r:
            body = await r.read()
            request.app['logger'].info(f"POST {item['transaction_webhook']} returned {r.status} {body}")
