from datetime import datetime as dt
import logging
from typing import Literal, Optional
from typing_extensions import Self
import uuid
import json

import aiohttp
from discord.ext import vbu

from .flags import RequiredLogins

__all__ = (
    'CheckoutItem',
    'create_purchase',
    'fetch_purchase',
    'update_purchase',
    'log_transaction',
)

log = logging.getLogger("vbu.voxelfox.webhook")


class User:

    __slots__ = (
        '_id',
        'discord_user_id',
        'stripe_id',
        'paypal_id',
        'paypal_client_id',
        'paypal_client_secret',
    )

    def __init__(
            self,
            id: str | uuid.UUID,
            discord_user_id: Optional[int],
            stripe_id: Optional[str],
            paypal_id: Optional[str],
            paypal_client_id: Optional[str],
            paypal_client_secret: Optional[str]):
        self._id = id
        self.discord_user_id = discord_user_id
        self.stripe_id = None if stripe_id == "VFL" else stripe_id
        self.paypal_id = paypal_id
        self.paypal_client_id = paypal_client_id
        self.paypal_client_secret = paypal_client_secret

    @property
    def id(self) -> str:
        return str(self._id)

    @classmethod
    def from_row(cls, row: dict):
        return cls(
            id=row['id'],
            discord_user_id=row.get('discord_user_id'),
            stripe_id=row.get('stripe_id'),
            paypal_id=row.get('paypal_id'),
            paypal_client_id=row.get('paypal_client_id'),
            paypal_client_secret=row.get('paypal_client_secret'),
        )

    @classmethod
    async def fetch(
            cls,
            db: vbu.Database,
            id: str | uuid.UUID) -> Optional[Self]:
        row = await db.call(
            """SELECT * FROM users WHERE id=$1""",
            id,
        )
        if row:
            return cls.from_row(row[0])
        return None


class CheckoutItem:

    __slots__ = (
        '_id',
        '_creator_id',
        'product_name',
        'success_url',
        'cancel_url',
        'subscription',
        'stripe_product_id',
        'stripe_price_id',
        'paypal_plan_id',
        'transaction_webhook',
        'transaction_webhook_authorization',
        'product_group',
        'per_guild',
        'multiple',
        'description',
        'quantity',
        'price',
        'price_number',
        'currency_code',
        '_currency_symbol',
        'user',
        'quantity',
        'min_quantity',
        'max_quantity',
        'required_logins',
    )

    def __init__(
            self,
            id: uuid.UUID | str,
            creator_id: uuid.UUID | str,
            product_name: str,
            success_url: str,
            cancel_url: str,
            subscription: bool,
            stripe_product_id: str,
            stripe_price_id: str,
            paypal_plan_id: Optional[str],
            transaction_webhook: str,
            transaction_webhook_authorization: str,
            product_group: str,
            multiple: bool,
            per_guild: bool,
            description: str,
            quantity: int,
            min_quantity: int | None,
            max_quantity: int | None,
            required_logins: RequiredLogins):
        self._id = id
        self._creator_id = creator_id
        self.product_name: str = product_name
        self.success_url: str = success_url
        self.cancel_url: str = cancel_url
        self.subscription: bool = subscription
        self.stripe_product_id: str = stripe_product_id
        self.stripe_price_id: str = stripe_price_id
        self.paypal_plan_id: Optional[str] = paypal_plan_id
        self.transaction_webhook: str = transaction_webhook
        self.transaction_webhook_authorization: str = transaction_webhook_authorization

        self.product_group: str = product_group
        self.per_guild: bool = per_guild
        self.multiple = multiple
        self.required_logins = required_logins

        self.description: str = description

        self.quantity: int = quantity
        self.min_quantity: int | None = min_quantity
        self.max_quantity: int | None = max_quantity

        self.price: str | None = None
        self.price_number: int = 0
        self.currency_code: str | None = None
        self._currency_symbol: str | None = None

        self.user: User | None = None

    @property
    def id(self) -> str:
        return str(self._id)

    @property
    def creator_id(self) -> str:
        return str(self._creator_id)

    @property
    def name(self) -> str:
        return self.product_name

    @property
    def webhook(self) -> str:
        return self.transaction_webhook

    @property
    def webhook_auth(self) -> str:
        return self.transaction_webhook_authorization

    @property
    def currency_symbol(self) -> str:
        if self._currency_symbol is not None:
            return self._currency_symbol
        if self.currency_code is None:
            return ""
        if self.currency_code.casefold() == "gbp":
            self._currency_symbol = "£"
        elif self.currency_code.casefold() == "usd":
            self._currency_symbol = "$"
        elif self.currency_code.casefold() == "eur":
            self._currency_symbol = "€"
        else:
            self._currency_symbol = self.currency_code
        return self._currency_symbol

    async def fetch_price(self, stripe_api_key: str) -> str:
        """
        Fetches the price of the item from Stripe.
        """

        if self.price is not None:
            return self.price

        async with aiohttp.ClientSession() as session:
            url = f"https://api.stripe.com/v1/prices/{self.stripe_price_id}"
            auth = aiohttp.BasicAuth(stripe_api_key)
            headers = {}
            if self.user and self.user.stripe_id:
                headers['Stripe-Account'] = self.user.stripe_id
            resp = await session.get(url, auth=auth, headers=headers)
            product_data = await resp.json()

        if resp.ok:
            self.price = f"{product_data['unit_amount'] / 100:.2f}"
            self.price_number = product_data['unit_amount']
            self.currency_code = product_data['currency'].upper()
            self._currency_symbol = None
        else:
            self.price = "0.00"
            self.price_number = 0
            self.currency_code = "GBP"
            self._currency_symbol = None

        if self.subscription:
            self.price = f"{self.price} per month"
        return self.price

    @classmethod
    def from_row(cls, row: dict) -> Self:
        return cls(
            id=row['id'],
            creator_id=row['creator_id'],
            product_name=row['product_name'],
            success_url=row['success_url'],
            cancel_url=row['cancel_url'],
            subscription=row['subscription'],
            stripe_product_id=row['stripe_product_id'],
            stripe_price_id=row['stripe_price_id'],
            paypal_plan_id=row['paypal_plan_id'],
            transaction_webhook=row['transaction_webhook'],
            transaction_webhook_authorization=row['transaction_webhook_authorization'],
            product_group=row['product_group'],
            per_guild=row['per_guild'],
            multiple=row.get('multiple', False),
            description=row['description'],
            quantity=row['quantity'],
            min_quantity=row.get('min_quantity'),
            max_quantity=row.get('max_quantity'),
            required_logins=RequiredLogins(row['required_logins']),
        )

    @classmethod
    async def fetch(
            cls,
            db: vbu.Database,
            product_name: Optional[str] = None,
            *,
            paypal_id: Optional[str] = None,
            stripe_id: Optional[str] = None,
            **kwargs) -> Optional[Self]:
        """
        Fetch an instance from the database.
        """

        # Add product name to kwargs
        if product_name:
            kwargs['product_name'] = product_name

        # Fetch from db
        if [paypal_id, stripe_id] == [None, None]:
            item_rows = await db.call(
                """
                SELECT
                    checkout_items.*
                FROM
                    checkout_items
                WHERE
                    {args}
                """.format(
                    args=" AND ".join(
                        f"checkout_items.{key} = ${index + 1}"
                        for index, key in enumerate(kwargs.keys())
                    )
                ),
                *kwargs.values()
            )
        else:
            item_rows = await db.call(
                """
                SELECT
                    checkout_items.*
                FROM
                    checkout_items
                LEFT JOIN
                    users
                ON
                    checkout_items.creator_id = users.id
                WHERE
                    {args}
                    AND users.{processor}_id = $1
                """.format(
                    processor="paypal" if paypal_id else "stripe",
                    args=" AND ".join(
                        f"checkout_items.{key} = ${index + 2}"
                        for index, key in enumerate(kwargs.keys())
                    )
                ),
                paypal_id or (stripe_id or 'VFL'),
                *kwargs.values()
            )

        # Return what we got
        if not item_rows:
            return None
        if len(item_rows) > 1:
            raise ValueError("Multiple items found")
        v = cls.from_row(item_rows[0])
        await v.fetch_user(db)
        return v

    async def fetch_user(self, db):
        self.user = await User.fetch(db, self.creator_id)


async def create_purchase(
        db: vbu.Database,
        user_id: int,
        product_name: str,
        *,
        guild_id: Optional[int] = None,
        expiry_time: Optional[dt] = None,
        cancel_url: Optional[str] = None,
        timestamp: Optional[dt] = None,
        paypal_id: Optional[str] = None,
        stripe_id: Optional[str] = None):
    log.info("Storing purchase in database")
    await db.call(
        """
        INSERT INTO
            purchases
            (
                discord_user_id,
                product_id,
                discord_guild_id,
                expiry_time,
                cancel_url,
                timestamp
            )
        VALUES
            (
                $1,
                (
                    SELECT
                        checkout_items.id
                    FROM
                        checkout_items
                    LEFT JOIN
                        users
                    ON
                        checkout_items.creator_id = users.id
                    WHERE
                        checkout_items.product_name = $2
                        AND users.{processor}_id = $3
                ),
                $4,
                $5,
                $6,
                $7
            )
        """.format(processor="paypal" if paypal_id else "stripe"),
        int(user_id),
        product_name,
        paypal_id or (stripe_id or 'VFL'),
        int(guild_id) if guild_id else None,
        expiry_time,
        cancel_url,
        timestamp or dt.utcnow(),
    )


async def fetch_purchase(
        db: vbu.Database,
        user_id: int,
        product_name: str,
        *,
        paypal_id: Optional[str] = None,
        stripe_id: Optional[str] = None,
        guild_id: Optional[int] = None) -> Optional[dict]:
    if guild_id:
        rows = await db.call(
            """
            SELECT
                purchases.*
            FROM
                purchases
            LEFT JOIN
                checkout_items
            ON
                purchases.product_id = checkout_items.id
            LEFT JOIN
                users
            ON
                checkout_items.creator_id = users.id
            WHERE
                purchases.discord_user_id = $1
                AND checkout_items.product_name = $2
                AND purchases.discord_guild_id = $3
                AND users.{processor}_id = $4
            ORDER BY
                timestamp DESC
            LIMIT 1
            """.format(processor="paypal" if paypal_id else "stripe"),
            int(user_id),
            product_name,
            int(guild_id),
            paypal_id or (stripe_id or 'VFL'),
        )
    else:
        rows = await db.call(
            """
            SELECT
                *
            FROM
                purchases
            LEFT JOIN
                checkout_items
            ON
                purchases.product_id = checkout_items.id
            LEFT JOIN
                users
            ON
                checkout_items.creator_id = users.id
            WHERE
                purchases.discord_user_id = $1
                AND checkout_items.product_name = $2
                AND purchases.discord_guild_id IS NULL
                AND users.{processor}_id = $3
            ORDER BY
                timestamp DESC
            LIMIT 1
            """.format(processor="paypal" if paypal_id else "stripe"),
            int(user_id),
            product_name,
            paypal_id or (stripe_id or 'VFL'),
        )
    if rows:
        return rows[0]
    return None


async def update_purchase(
        db: vbu.Database,
        id: uuid.UUID | str,
        **kwargs):
    if kwargs.pop("delete", False) is True:
        log.info("Deleting purchase with ID %s" % id)
        await db.call(
            """
            DELETE FROM
                purchases
            WHERE
                id = $1
            """,
            id,
        )
    else:
        log.info("Updating purchase with ID %s" % id)
        await db.call(
            """
            UPDATE
                purchases
            SET
                {kwargs}
            WHERE
                id = $1
            """.format(kwargs=", ".join(f"{key} = ${i + 2}" for i, key in enumerate(kwargs))),
            id,
            *kwargs.values(),
        )


async def log_transaction(
        db: vbu.Database,
        product_id: str | uuid.UUID,
        amount_gross: int | float,
        amount_net: Optional[int | float],
        currency: str,
        settle_amount: Optional[int | float],
        settle_currency: Optional[str],
        identifier: str,
        payment_processor: Literal["Stripe", "PayPal"],
        customer_email: Optional[str] = None,
        metadata: Optional[dict] = None):
    """
    Store a transaction in the database log.
    """

    if type(amount_gross) is float:
        amount_gross = int(amount_gross * 100)
    if type(amount_net) is float:
        amount_net = int(amount_net * 100)
    if type(settle_amount) is float:
        settle_amount = int(settle_amount * 100)
    if settle_amount is None:
        settle_amount = amount_gross
    if settle_currency is None:
        settle_currency = currency
    await db.call(
        """
        INSERT INTO
            transactions
            (
                product_id,
                amount_gross,
                amount_net,
                currency,
                settle_amount,
                settle_currency,
                identifier,
                payment_processor,
                customer_email,
                metadata
            )
        VALUES
            ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """,
        product_id,
        amount_gross,
        amount_net,
        currency.lower(),
        settle_amount,
        settle_currency.lower(),
        identifier,
        payment_processor,
        customer_email,
        json.dumps(metadata) if metadata else None,
    )
