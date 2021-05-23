import json
from datetime import datetime as dt
from urllib.parse import unquote, parse_qs

import aiohttp
from aiohttp.web import HTTPFound, Request, RouteTableDef, Response
from voxelbotutils import web as webutils
import aiohttp_session
import discord
from aiohttp_jinja2 import template, render_template
import htmlmin
import pytz


routes = RouteTableDef()


@routes.get('/login_processor')
async def login_processor(request:Request):
    """
    Page the discord login redirects the user to when successfully logged in with Discord.
    """

    v = await webutils.process_discord_login(request)
    if isinstance(v, Response):
        return v
    session = await aiohttp_session.get_session(request)
    return HTTPFound(location=session.pop('redirect_on_login', '/'))


@routes.get('/logout')
async def logout(request:Request):
    """
    Destroy the user's login session.
    """

    session = await aiohttp_session.get_session(request)
    session.invalidate()
    return HTTPFound(location='/')


@routes.get('/login')
async def login(request:Request):
    """
    Direct the user to the bot's Oauth login page.
    """

    return HTTPFound(location=webutils.get_discord_login_url(request, "/login_processor"))


@routes.post('/discord/chatlog')
async def discord_handler(request:Request):
    """
    Creates you a Discord chatlog you might be able to use.
    """

    with open('website/static/css/discord/core.min.css') as a:
        core_css = a.read()
    with open('website/static/css/discord/dark.min.css') as a:
        dark_css = a.read()
    rendered_template: Response = render_template('discord_page.html.j2', request, {
        'data': (await request.json()),
        'core_css': core_css,
        'dark_css': dark_css,
    })
    response_text = htmlmin.minify(
        rendered_template.text,
        remove_comments=True,
        remove_empty_space=True,
        reduce_boolean_attributes=True
    )
    rendered_template.text = response_text
    return rendered_template


@routes.post('/webhooks/paypal/purchase_ipn')
async def paypal_purchase_complete(request:Request):
    """
    Handles Paypal throwing data my way.
    """

    # Get the data from the post request
    content_bytes: bytes = await request.content.read()
    paypal_data_string: str = content_bytes.decode()
    try:
        paypal_data = {i.strip(): o[0].strip() for i, o in parse_qs(paypal_data_string).items()}
    except Exception:
        paypal_data = {'receiver_email': ''}

    # Let's throw that into a logger
    request.app['logger'].info(paypal_data_string)

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

    # See what the transaction is
    non_payment_transactions = [
        'adjustment', 'mp_cancel', 'new_case',
        'recurring_payment_profile_created',
        'recurring_payment_profile_cancel',
    ]
    if paypal_data.get('txn_type') is None:
        request.app['logger'].info("Null transaction type passed for PayPal IPN")
        return Response(status=200)  # It's a case update - we'll just discard those; we only store transactions
    if paypal_data['txn_type'] in non_payment_transactions:
        request.app['logger'].info("Non-payment transaction type passed for PayPal IPN")
        return Response(status=200)

    """
    Just so I can have it written here with the rest of the relevant data, these are the valid transaction types
    (list taken from https://developer.paypal.com/docs/ipn/integration-guide/IPNandPDTVariables/#id08CTB0S055Z)

    null - Chargeback
    adjustment - Dispute resolution
    cart - Payment received for multiple items
    express_checkout - Payment for a single item
    masspay - Payment sent using mass pay
    merch_pmt - Monthly subscription payment
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
    web_accept - Any of the buy now buttons
    """

    # Process static items
    if "item_name" in paypal_data:
        await process_paypal_item(request, paypal_data, "item_name", None)
    index = 1
    while f"item_name{index}" in paypal_data:
        await process_paypal_item(request, paypal_data, f"item_name{index}", index)
        index += 1

    # Process subscription items
    if "product_name" in paypal_data:
        await process_paypal_item(request, paypal_data, "product_name", None)

    # And we're done
    return Response(status=200)


def get_datetime_from_string(string) -> dt:
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


async def process_paypal_item(request, paypal_data, item_name_field, index):
    """
    Process the item in a given set of PayPal data.
    """

    # Load the custom data from the payload
    try:
        custom_data_dict = json.loads(paypal_data['custom'])
    except Exception:
        custom_data_dict = {}

    # Get the payment amount
    payment_field = None
    if index is None:
        payment_field = "mc_gross"
    else:
        payment_field = f"mc_gross_{index}"
    payment_amount = int(paypal_data.get(payment_field, "0").replace('.', ''))

    # Make sure they're actually buying something
    if paypal_data.get(item_name_field) is None:
        request.app['logger'].info("Item name set to null for PayPal IPN")
        return None

    # Get the item data
    try:
        webhook_data = request.app['config']['paypal_item_webhooks'][paypal_data.get(item_name_field)]
    except KeyError:
        return None  # It's not an item we're handling

    # Make sure it's to the right person
    if paypal_data['receiver_email'].casefold() != webhook_data['receiver_email'].casefold():
        request.app['logger'].info("Invalid email passed for PayPal IPN")
        return None  # Wrong email passed

    # See if it's refunded data
    refunded = False
    if payment_amount < 0:
        if 'payment_status' not in paypal_data:
            request.app['logger'].info("IPN *probably* a subscription create/delete.")
        elif paypal_data['payment_status'] in ['Denied', 'Expired', 'Failed', 'Voided', 'Refunded', 'Reversed']:
            refunded = True
            request.app['logger'].info("IPN set as refunded payment")
        else:
            request.app['logger'].info("Payment below zero and non-reversed payment for PayPal IPN")
            return None  # Payment below zero AND it's not reversed

    # Set up our data to be databased
    checkout_complete_timestamp = get_datetime_from_string(paypal_data['payment_date']).timestamp()
    next_payment_date = None
    if 'next_payment_date' in paypal_data:
        next_payment_date = get_datetime_from_string(paypal_data['next_payment_date']).timestamp()
    database = {
        'completed': paypal_data.get('payment_status', 'Completed') == 'Completed',  # Benefit of the doubt - assume it's done
        'transaction_type': paypal_data['txn_type'],
        'checkout_complete_timestamp': checkout_complete_timestamp,
        'customer_id': paypal_data['payer_id'],
        'id': paypal_data['txn_id'],
        'payment_amount': payment_amount,
        'discord_id': int(custom_data_dict.get('discord_user_id', 0)),
        'guild_id': int(custom_data_dict.get('discord_guild_id', 0)),
        'item_name': paypal_data[item_name_field],
        'option_selection': None,
        'custom': json.dumps(custom_data_dict),
        'custom_dict': custom_data_dict,  # Doesn't actually go into the database
        'payment_currency': paypal_data['mc_currency'],
        'refunded': refunded,
        'quantity': int(paypal_data.get('quantity' if index is None else f'quantity{index}', '1')),
        'next_payment_date': next_payment_date,
    }
    if database['completed'] is False:
        database['checkout_complete_timestamp'] = None

    # Save the data
    sql = """
    INSERT INTO paypal_purchases (
        id, transaction_type, customer_id, payment_amount, discord_id, guild_id, completed,
        checkout_complete_timestamp, item_name, option_selection, custom, payment_currency,
        quantity, next_payment_date
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
    ) ON CONFLICT (id, item_name) DO UPDATE
    SET
        customer_id=excluded.customer_id, payment_amount=excluded.payment_amount, discord_id=excluded.discord_id,
        guild_id=excluded.guild_id, completed=excluded.completed,
        checkout_complete_timestamp=excluded.checkout_complete_timestamp, next_payment_date=excluded.next_payment_date
    """
    async with request.app['database']() as db:
        next_payment_date_timestamp = dt.fromtimestamp(database['next_payment_date']) if database['next_payment_date'] else None
        await db(
            sql, database['id'], database['transaction_type'], database['customer_id'],
            database['payment_amount'], database['discord_id'], database['guild_id'], database['completed'],
            dt.fromtimestamp(database['checkout_complete_timestamp']), database['item_name'],
            database['option_selection'], database['custom'], database['payment_currency'],
            database['quantity'], next_payment_date_timestamp,
        )

    # Get the webhook url
    try:
        if database['completed'] or refunded:
            webhook_url = webhook_data['webhook_url']
        else:
            webhook_url = None
    except KeyError:
        webhook_url = None

    # Ping the webhook url with the data
    if webhook_url:
        request.app['logger'].info(f"Pinging {webhook_url} with PayPal data")
        try:
            async with aiohttp.ClientSession(loop=request.app.loop) as session:
                headers = {'Authorization': webhook_data['authorization']}
                async with session.post(webhook_url, headers=headers, json=database):
                    pass
        except Exception as e:
            request.app['logger'].info(e)

    # Let the user get redirected
    request.app['logger'].info(f"Processed payment for item '{database['item_name']} - {database['option_selection']}")
    return None


@routes.post('/webhooks/topgg/vote_added')
async def webhook_handler(request:Request):
    """
    Sends a PM to the user with the webhook attached if user in owners.
    """

    # See if we can get it
    try:
        request_data = await request.json()
    except Exception:
        request.app['logger'].info("Error parsing TopGG webhook")
        return Response(status=400)

    # See if it's all valid
    keys = set(['bot', 'user', 'type'])
    if not set(request_data.keys()).issuperset(keys):
        request.app['logger'].info("Error parsing TopGG webhook - invalid keys")
        return Response(status=400)

    # Get the bot's ID
    try:
        bot_id = int(request_data['bot'])
    except ValueError:
        request.app['logger'].info("Error parsing TopGG webhook - invalid bot")
        return Response(status=400)

    # Get the user's ID
    try:
        user_id = int(request_data['user'])
    except ValueError:
        request.app['logger'].info("Error parsing TopGG webhook - invalid user")
        return Response(status=400)

    # Grab data from the config
    try:
        webhook_data = [i for i in request.app['config']['topgg_bot_webhooks'] if i['bot_id'] == bot_id][0]
    except IndexError:
        request.app['logger'].info(f"No TopGG passthrough webhook set for bot ID {bot_id}")
        return Response(status=400)

    # Check type
    if request_data['type'] not in ['upvote', 'test']:
        request.app['logger'].info("Error parsing TopGG webhook - invalid webhook type")
        return Response(status=400)

    # Check auth token from topgg
    if request.headers.get('Authorization') != webhook_data['authorization']:
        request.app['logger'].info("Error parsing TopGG webhook - invalid authorization")
        return Response(status=400)

    # Generate webhook ping data
    response_data = {
        'bot_id': bot_id,  # Doesn't need to be present but eh why not
        'user_id': user_id,
        'type': request_data['type']
    }

    # Ping the webhook
    url = webhook_data['webhook_url']
    async with aiohttp.ClientSession(loop=request.app.loop) as session:
        headers = {"Authorization": webhook_data['authorization']}
        async with session.post(url, headers=headers, json=response_data):
            pass
    request.app['logger'].info(f"Pinged TopGG webhook data to {url}")

    return Response(status=200)
