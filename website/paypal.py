import json
import binascii
from base64 import b64decode
from datetime import datetime as dt, timedelta

import aiohttp
from aiohttp.web import Request, RouteTableDef, Response, json_response
from OpenSSL import crypto


routes = RouteTableDef()
PAYPAL_BASE = "https://api-m.sandbox.paypal.com"


def get_expected_signature(transmission_id, timestamp, webhook_id, event_body):
    """
    Get the input string to generate the HMAC signature
    """

    data = str(binascii.crc32(event_body) & 0xffffffff)
    expected_sig = f"{transmission_id}|{timestamp}|{webhook_id}|{data}"
    return expected_sig.encode()


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
                return json_response({}, status=500)

    # Ask PayPal for the right data
    if item_row['subscription']:
        data = await create_subscription_checkout_session(request, product_name, quantity, item_row, product_data, metadata)
    else:
        data = await create_single_purchase_checkout_session(request, product_name, quantity, item_row, product_data, metadata)
    if data.status == 500:
        return data
    data = json.loads(data.text)
    return json_response({"subscription": item_row['subscription'], "id": data['id']})


async def create_single_purchase_checkout_session(request, product_name, quantity, item_row, product_data, metadata):
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


async def create_subscription_checkout_session(request, product_name, quantity, item_row, product_data, metadata):
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


@routes.post('/webhooks/paypal/purchase_webhook')
async def paypal_purchase_complete(request:Request):
    """
    Handle webhooks from PayPal.
    """

    # Get the data from the post request
    paypal_data_string = await request.read()
    paypal_data = json.loads(paypal_data_string.decode())

    # Let's throw that into a logger
    request.app['logger'].info(paypal_data_string)

    # Grab some headers to use in the signature
    transmission_signature = request.headers['PAYPAL-TRANSMISSION-SIG']
    auth_algorithm = request.headers['PAYPAL-AUTH-ALGO']
    cert_url = request.headers['PAYPAL-CERT-URL']  # x509 pubkey
    transmission_id = request.headers['PAYPAL-TRANSMISSION-ID']
    timestamp = request.headers['PAYPAL-TRANSMISSION-TIME']
    expected_signature = get_expected_signature(
        transmission_id, timestamp, request.app['config']['paypal_webhook_id'],
        paypal_data_string,
    )

    # Check the signature to make sure it's valid
    async with aiohttp.ClientSession() as session:
        async with session.get(cert_url) as r:
            cert_text = await r.read()

    cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert_text.decode())
    algo_instance = {
        'SHA256withRSA': 'sha256WithRSAEncryption',
        'SHA1withRSA': 'sha1WithRSAEncryption',
        'sha256': 'sha256',
    }[auth_algorithm]
    try:
        crypto.verify(cert, b64decode(transmission_signature), expected_signature, algo_instance)
    except Exception as e:
        request.app['logger'].error(e)
        return Response(status=200)

    # Process the data
    event = paypal_data['event_type']
    if event == "PAYMENT.CAPTURE.COMPLETED":  # This does not happen for subscriptions' initial payment
        await charge_captured(request, paypal_data)
    elif event == "BILLING.SUBSCRIPTION.ACTIVATED":
        await subscription_created(request, paypal_data)
    elif event == "BILLING.SUBSCRIPTION.CANCELLED":
        await subscription_deleted(request, paypal_data)
    elif event == "PAYMENT.CAPTURE.REFUNDED":
        await charge_refunded(request, paypal_data)

    # And we have no more events to process
    return Response(status=200)


async def send_charge_payload(request: Request, data: dict):
    """
    Send a payload for a given charge.
    """

    # Get the item from the database
    unit = data['purchase_units'][0]
    product = unit['items'][0]
    product_name = product['name']
    async with request.app['database']() as db:
        item_rows = await db(
            """SELECT * FROM checkout_items WHERE product_name=$1""",
            product_name,
        )
    if not item_rows:
        raise Exception(f"Missing item {product_name} from database")
    item_row = item_rows[0]

    # Ping the webhook with the relevant data
    headers = {"Authorization": item_row['transaction_webhook_authentication']}
    json_data = {
        "product_name": item_row['product_name'],
        "quantity": int(product['quantity']),
        "refund": unit['payments'].get("refunds") is not None,
        "subscription": False,
        **json.loads(unit['custom_id']),
        # "_stripe": data,
        "subscription_expiry_time": None,
    }
    async with aiohttp.ClientSession() as session:
        await session.post(item_row['transaction_webhook'], json=json_data, headers=headers)


async def charge_captured(request: Request, data: dict) -> None:
    """
    Pinged when a charge is successfully recieved.
    """

    async with aiohttp.ClientSession() as session:
        url = [i for i in data['resource']['links'] if i['rel'] == 'up'][0]['href']
        auth = aiohttp.BasicAuth(
            request.app['config']['paypal_client_id'],
            request.app['config']['paypal_client_secret'],
        )
        async with session.post(url, json=data, auth=auth) as r:
            response = await r.json()
            if not r.ok:
                return json_response(response, status=500)
    return await send_charge_payload(request, response)


async def charge_refunded(request: Request, data: dict) -> None:
    """
    Pinged when a charge is refunded.
    """

    async with aiohttp.ClientSession() as session:
        url = [i for i in data['resource']['links'] if i['rel'] == 'up'][0]['href']
        auth = aiohttp.BasicAuth(
            request.app['config']['paypal_client_id'],
            request.app['config']['paypal_client_secret'],
        )
        async with session.post(url, json=data, auth=auth) as r:
            response = await r.json()
            if not r.ok:
                return json_response(response, status=500)
    return await charge_captured(request, response)


async def send_subscription_payload(request: Request, data: dict, expiry_timestamp: float = None):
    """
    Pings the relevant webhook for when a subscription is created or deleted.
    """

    # Get the plan object from PayPal
    async with aiohttp.ClientSession() as session:
        url = PAYPAL_BASE + "/v1/billing/plans/{0}".format(data['resource']['plan_id'])
        auth = aiohttp.BasicAuth(
            request.app['config']['paypal_client_id'],
            request.app['config']['paypal_client_secret'],
        )
        async with session.post(url, json=data, auth=auth) as r:
            response = await r.json()
            if not r.ok:
                return json_response(response, status=500)

        # Get the item from the database
        product_name = response['name']
        async with request.app['database']() as db:
            item_rows = await db(
                """SELECT * FROM checkout_items WHERE product_name=$1""",
                product_name,
            )
        if not item_rows:
            raise Exception(f"Missing item {product_name} from database")
        item_row = item_rows[0]

        # Ping the webhook with the relevant data
        headers = {"Authorization": item_row['transaction_webhook_authentication']}
        json_data = {
            "product_name": item_row['product_name'],
            "quantity": data['resource']['quantity'],
            "refund": False,
            "subscription": True,
            **json.loads(data['resource']['custom_id']),
            # "_stripe": data,
            "subscription_expiry_time": expiry_timestamp,
        }
        await session.post(item_row['transaction_webhook'], json=json_data, headers=headers)


async def subscription_created(request: Request, data: dict) -> None:
    """
    Pinged when a subscription is created.
    """

    return await send_subscription_payload(request, data, None)


async def subscription_deleted(request: Request, data: dict) -> None:
    """
    Pinged when a subscription is deleted.
    """

    cancel_time = dt.strptime(data['resource']['billing_info']['last_payment']['time'], "%Y-%m-%dT%H:%M:%SZ")
    expiry_time = cancel_time + timedelta(days=30)
    return await send_subscription_payload(request, data, expiry_time.timestamp())
