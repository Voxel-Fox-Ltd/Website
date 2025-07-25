import json
from urllib.parse import parse_qs
from datetime import datetime as dt, timedelta
from typing import Tuple, Generator
import logging

import aiohttp
from aiohttp.web import Request, RouteTableDef, Response
from discord.ext import vbu
import pytz

from .utils import (
    send_webhook,
    get_paypal_access_token,
    CheckoutItem,
    types,
    User,
    Purchase,
    send_sql,
)


routes = RouteTableDef()
log = logging.getLogger("vbu.voxelfox.paypal")
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


@routes.post('/webhooks/paypal/purchase_ipn_new')
async def paypal_ipn_complete(request: Request):
    """
    Handles Paypal throwing data my way.
    """

    # Get the data from the post request
    content_bytes: bytes = await request.content.read()
    paypal_data_string: str = content_bytes.decode()
    paypal_data: types.IPNMessage
    try:
        paypal_data = {
            i.strip(): o[0].strip()
            for i, o in parse_qs(paypal_data_string).items()
        }  # pyright: ignore
    except Exception:
        paypal_data = {'receiver_email': '@business.example.com'}  # pyright: ignore

    # Let's throw that into a logger
    log.info(f"Data from PayPal: {json.dumps(paypal_data)}")

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
            return Response(status=200)  # Fake data, but PayPal expects a 200

    # Process the data
    event = paypal_data.get('txn_type')
    charge_capture_events = [
        "cart",
        "express_checkout",
        "web_accept",
        None,
    ]  # This includes refunds
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
        await charge_captured(request, paypal_data)
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
    return (
        datetime
        .astimezone(pytz.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def get_datetime_from_standard_format(string: str) -> dt:
    return dt.strptime(string, "%Y-%m-%dT%H:%M:%SZ")


def get_time_around_datetime(datetime: dt) -> Tuple[dt, dt]:
    constructor = (
        datetime.year,
        datetime.month,
        datetime.day,
    )
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
    url = f"{PAYPAL_BASE}/v1/billing/subscriptions/{subscription_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
    }
    async with aiohttp.ClientSession() as session:
        resp = await session.get(url, headers=headers)
        return await resp.json()


def get_products_from_charge(data: types.IPNMessage) -> Generator[dict, None, None]:
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
            "name": data["product_name"],
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


async def charge_captured(request: Request, data: types.IPNMessage):
    """
    Pinged when a user purchases an object via checkout.
    """

    # See if they're refunded
    refunded = data['payment_status'] in ['Denied', 'Refunded', 'Reversed']

    # Grab the metadata from the request
    metadata = json.loads(data.get("custom_id", "{}"))
    metadata.update(json.loads(data.get("custom", "{}")))

    # See if it's a subscription refund
    if "recurring_payment_id" in data:
        recurring_payment_info = await get_subscription_by_subscription_id(
            request,
            data['recurring_payment_id'],
        )
        metadata.update(json.loads(recurring_payment_info.get("custom_id", "{}")))
        metadata.update(json.loads(recurring_payment_info.get("custom", "{}")))

    # Grab the data from the database for each of the items
    products = get_products_from_charge(data)
    async with vbu.Database() as db:
        items = [
            await CheckoutItem.fetch_by_name(db, product_name=i['name'])
            for i in products
        ]
    items = [i for i in items if i]

    # Fix up those dicts to include quantity
    for i in items:
        for p in products:
            if i.name == p['name']:
                i.quantity = p['quantity']
                break  # Only break out of the inner loop

    # Add these transactions to the database
    async with vbu.Database() as db:
        for i in items:
            user = await User.fetch(
                db,
                id=metadata.get("user_id"),
                discord_user_id=metadata.get("discord_user_id"),
            )
            if user is None:
                user = await User.create(
                    db,
                    discord_user_id=metadata.get("discord_user_id"),
                )

            if refunded:
                current = await Purchase.fetch_by_user(
                    db, user, i,
                    discord_guild_id=metadata.get('discord_guild_id'),
                )
                if not current:
                    continue
                current = current[0]
                await current.delete(db)
            else:
                current = await Purchase.create(
                    db, user, i,
                    discord_guild_id=metadata.get('discord_guild_id'),
                    identifier=data.get('txn_id'),
                    # cancel_url=(
                    #     ""
                    #     if "recurring_payment_id" in data
                    #     else None
                    # ),
                )

            json_data = {
                "product_name": i.name,
                "quantity": i.quantity,
                "refund": refunded,
                "subscription": False,
                **metadata,
                "subscription_expiry_time": None,
                "source": "PayPal",
                "subscription_delete_url": None,
                "discord_user_id": user.discord_user_id,
                "discord_guild_id": current.discord_guild_id,
            }
            await send_webhook(i, json_data)
            await send_sql(i, json_data)


async def subscription_created(request: Request, data: types.IPNMessage):
    """
    Pigned when a user creates a new subscription purchase.
    """

    # Get the data from the subscription
    product_name = data.get('product_name')
    assert product_name
    recurring_payment_id = data.get('recurring_payment_id')
    assert recurring_payment_id

    # Get the recurring payment info
    recurring_payment_info = await get_subscription_by_subscription_id(
        request,
        recurring_payment_id,
    )
    metadata = json.loads(recurring_payment_info.get('custom_id', "{}"))
    metadata.update(json.loads(recurring_payment_info.get('custom', "{}")))

    # Grab the data from the database
    async with vbu.Database() as db:
        item = await CheckoutItem.fetch_by_name(db, product_name=product_name)
    if item is None:
        log.info(f"Missing item {product_name} from database.")
        return

    # And store in the database
    async with vbu.Database() as db:
        user = await User.fetch(
            db,
            id=metadata.get("user_id"),
            discord_user_id=metadata.get("discord_user_id"),
        )
        if user is None:
            user = await User.create(
                db,
                discord_user_id=metadata.get("discord_user_id"),
            )
        if data['txn_type'] == "recurring_payment":
            assert user
            current = await Purchase.fetch_by_user(
                db, user, item,
                discord_guild_id=metadata.get('discord_guild_id'),
            )
            if current:
                return  # We only want to store the original subscription create
        current = await Purchase.create(
            db, user, item,
            discord_guild_id=metadata.get('discord_guild_id'),
            expiry_time=None,
            cancel_url=(
                f"{PAYPAL_BASE}/v1/billing/subscriptions/"
                f"{recurring_payment_id}/cancel"
            ),
            identifier=data.get('txn_id'),
        )

        json_data = {
            "product_name": item.name,
            "quantity": item.quantity,
            "refund": False,
            "subscription": True,
            **metadata,
            "subscription_expiry_time": None,
            "source": "PayPal",
            "subscription_delete_url": (
                f"{PAYPAL_BASE}/v1/billing/subscriptions/"
                f"{recurring_payment_id}/cancel"
            ),
            "discord_user_id": user.discord_user_id,
            "discord_guild_id": current.discord_guild_id,
        }
        await send_webhook(item, json_data)
        await send_sql(item, json_data)


async def subscription_deleted(request: Request, data: types.IPNMessage):
    """
    Pinged when a user cancels their subscription.
    """

    # Get the data from the subscription
    product_name = data.get('product_name')
    assert product_name
    recurring_payment_id = data.get('recurring_payment_id')
    assert recurring_payment_id

    # Get the recurring payment info
    recurring_payment_info = await get_subscription_by_subscription_id(
        request,
        recurring_payment_id,
    )
    metadata = json.loads(recurring_payment_info.get('custom_id', "{}"))
    metadata.update(json.loads(recurring_payment_info.get('custom', "{}")))

    # Grab the data from the database
    async with vbu.Database() as db:
        item = await CheckoutItem.fetch_by_name(db, product_name=product_name)
    if item is None:
        log.info(f"Missing item {product_name} from database")
        return

    # Get the last payment time
    payment_time_str = recurring_payment_info['billing_info']['last_payment']['time']
    last_purchase = get_datetime_from_standard_format(payment_time_str)
    expiry_time = last_purchase + timedelta(days=30)

    # And update the database
    async with vbu.Database() as db:
        user = await User.fetch(
            db,
            id=metadata.get("user_id"),
            discord_user_id=metadata.get("discord_user_id"),
        )
        if user is None:
            user = await User.create(
                db,
                discord_user_id=metadata.get("discord_user_id"),
            )
        current = await Purchase.fetch_by_user(
            db, user, item,
            discord_guild_id=metadata.get('discord_guild_id'),
        )
        if not current:
            return
        await current[0].update(db, expiry_time=expiry_time)

        json_data = {
            "product_name": item.name,
            "quantity": item.quantity,
            "refund": False,
            "subscription": True,
            **metadata,
            "subscription_expiry_time": expiry_time.timestamp(),
            "source": "PayPal",
            "subscription_delete_url": None,
            "discord_user_id": user.discord_user_id,
            "discord_guild_id": current[0].discord_guild_id,
        }
        await send_webhook(item, json_data)
        await send_sql(item, json_data)
