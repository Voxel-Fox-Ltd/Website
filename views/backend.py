import json
from datetime import datetime as dt
from urllib.parse import unquote

import aiohttp
from aiohttp.web import Request, RouteTableDef, Response

routes = RouteTableDef()


@routes.post('/webhooks/paypal/purchase_ipn')
async def paypal_purchase_complete(request:Request):
    """Handles Paypal throwing data my way"""

    # Get the data
    content_bytes: bytes = await request.content.read()
    paypal_data_string: str = content_bytes.decode()

    request.app['logger'].info(paypal_data_string)

    # Send the data back to see if it's valid
    data_send_back = "cmd=_notify-validate&" + paypal_data_string
    async with aiohttp.ClientSession(loop=request.app.loop) as session:
        paypal_url = {
            True: "https://ipnpb.sandbox.paypal.com/cgi-bin/webscr",
            False: "https://ipnpb.paypal.com/cgi-bin/webscr",
        }.get(request.app['config']['paypal_ipn']['sandbox'])
        async with session.post(paypal_url, data=data_send_back) as site:
            site_data = await site.read()
            if site_data.decode() != "VERIFIED":
                request.app['logger'].info("Invalid data sent to PayPal IPN url")
                return Response(status=200)  # Oh no it was fake data

    # Get the data from PP
    paypal_data = {unquote(i.split('=')[0].replace("+", " ")):unquote(i.split('=')[1].replace("+", " ")) for i in paypal_data_string.split('&')}
    try:
        custom_data_dict = json.loads(paypal_data['custom'])
    except Exception:
        custom_data_dict = {}
    payment_amount = int(paypal_data.get('mc_gross', '0').replace('.', ''))

    # See if we want to handle it at all
    if paypal_data.get('txn_type') is None:
        request.app['logger'].info("Null transaction type passed for PayPal IPN")
        return Response(status=200)  # It's a case update - we'll just discard those; we only store transactions
    if paypal_data['txn_type'] in ['adjustment', 'mp_cancel', 'new_case']:
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

    # Make sure it's to the right person
    if paypal_data['receiver_email'] != request.app['config']['paypal_ipn']['receiver_email']:
        request.app['logger'].info("Invalid email passed for PayPal IPN")
        return Response(status=200)  # Wrong email passed

    # Make sure they're actually buying something
    if paypal_data.get('item_name') is None:
        request.app['logger'].info("Item name set to null for PayPal IPN")
        return Response(status=200)

    # See if it's refunded data
    refunded = False
    if payment_amount < 0:
        if paypal_data['payment_status'] in ['Denied', 'Expired', 'Failed', 'Voided', 'Refunded', 'Reversed']:
            refunded = True
            request.app['logger'].info("IPN set as refunded payment")
        else:
            request.app['logger'].info("Payment below zero and non-reversed payment for PayPal IPN")
            return Response(status=200)  # Payment below zero AND it's not reversed

    # Lets print this or whatever
    request.app['logger'].info(paypal_data)

    # Set up our data to be databased
    database = {
        'completed': paypal_data['payment_status'] == 'Completed',
        'transaction_type': paypal_data['txn_type'],
        'checkout_complete_timestamp': dt.utcnow().timestamp(),
        'customer_id': paypal_data['payer_id'],
        'id': paypal_data['txn_id'],
        'payment_amount': payment_amount,
        'discord_id': int(custom_data_dict.get('discord_user_id', 0)),
        'guild_id': int(custom_data_dict.get('discord_guild_id', 0)),
        'item_name': paypal_data['item_name'],
        'option_selection': paypal_data.get('option_selection1', None),
        'custom': json.dumps(custom_data_dict),
        'payment_currency': paypal_data['mc_currency'],
        'refunded': refunded,
    }
    if database['completed'] is False:
        database['checkout_complete_timestamp'] = None

    # Save the data
    sql = """
    INSERT INTO paypal_purchases (
        id, transaction_type, customer_id, payment_amount, discord_id, guild_id, completed, checkout_complete_timestamp,
        item_name, option_selection, custom, payment_currency
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
    ) ON CONFLICT (id, transaction_type) DO UPDATE
    SET
        customer_id=excluded.customer_id, payment_amount=excluded.payment_amount, discord_id=excluded.discord_id, guild_id=excluded.guild_id,
        completed=excluded.completed, checkout_complete_timestamp=excluded.checkout_complete_timestamp
    """
    async with request.app['database']() as db:
        await db(
            sql, database['id'], database['transaction_type'], database['customer_id'],
            database['payment_amount'], database['discord_id'], database['guild_id'], database['completed'],
            dt.fromtimestamp(database['checkout_complete_timestamp']), database['item_name'], database['option_selection'], database['custom'],
            database['payment_currency'],
        )

    # Ping our relevant webhooks IF a refund was processed OR the checkout was completed and I've received the funds
    webhook_url = None
    try:
        if refunded is True or database['completed']:
            webhook_data = [i for i in request.app['config']['paypal_item_webhooks'] if i['item_name'] == database['item_name']][0]
            webhook_url = webhook_data['webhook_url']['purchase' if refunded is False else 'refund']
    except IndexError:
        pass
    if webhook_url:
        request.app['logger'].info(f"Pinging {webhook_url} with PayPal data")
        try:
            async with aiohttp.ClientSession(loop=request.app.loop) as session:
                headers = {'Token': webhook_data['webhook_token']}
                async with session.post(webhook_url, headers=headers, json=database):
                    pass
        except Exception as e:
            print(e)

    # Let the user get redirected
    return Response(status=200)
