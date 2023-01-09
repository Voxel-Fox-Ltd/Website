from datetime import datetime as dt
import logging
from typing import Optional
from typing_extensions import Self
import uuid

import aiohttp
from discord.ext import vbu

__all__ = (
    'CheckoutItem',
    'create_purchase',
    'fetch_purchase',
    'update_purchase',
)

log = logging.getLogger("vbu.voxelfox.webhook")


class CheckoutItem:

    __slots__ = (
        '_id',
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
    )

    def __init__(
            self,
            id: uuid.UUID | str,
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
            description: str):
        self._id = id
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

        self.description: str = description

        self.quantity: int = 1

        self.price: str | None = None
        self.price_number: int = 0
        self.currency_code: str | None = None
        self._currency_symbol: str | None = None

    @property
    def id(self) -> str:
        return str(self._id)

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
            resp = await session.get(url, auth=auth)
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
        )

    @classmethod
    async def fetch(
            cls, 
            db: vbu.Database, 
            product_name: Optional[str] = None, 
            **kwargs) -> Optional[Self]:
        """
        Fetch an instance from the database.
        """

        if product_name:
            item_rows = await db.call(
                """
                SELECT
                    *
                FROM
                    checkout_items
                WHERE
                    product_name = $1
                """,
                product_name,
            )
        else:
            if len(kwargs) > 1:
                raise ValueError("Can only fetch one item at a time.")
            item_rows = await db.call(
                """
                SELECT
                    *
                FROM
                    checkout_items
                WHERE
                    {0} = $1
                """.format(*kwargs.keys()),
                *kwargs.values(),
            )
        if not item_rows:
            return None
        return cls.from_row(item_rows[0])


async def create_purchase(
        db: vbu.Database,
        user_id: int,
        product_name: str,
        guild_id: Optional[int] = None,
        expiry_time: Optional[dt] = None,
        cancel_url: Optional[str] = None,
        timestamp: Optional[dt] = None):
    log.info("Storing purchase in database")
    await db.call(
        """
        INSERT INTO
            purchases
            (
                user_id,
                product_name,
                guild_id,
                expiry_time,
                cancel_url,
                timestamp
            )
        VALUES
            ($1, $2, $3, $4, $5, $6)
        """,
        int(user_id),
        product_name,
        int(guild_id) if guild_id else None,
        expiry_time,
        cancel_url,
        timestamp or dt.utcnow(),
    )


async def fetch_purchase(
        db: vbu.Database,
        user_id: int,
        product_name: str,
        guild_id: Optional[int] = None) -> Optional[dict]:
    if guild_id:
        rows = await db.call(
            """
            SELECT
                *
            FROM
                purchases
            WHERE
                user_id = $1
                AND product_name = $2
                AND guild_id = $3
            """,
            int(user_id),
            product_name,
            int(guild_id),
        )
    else:
        rows = await db.call(
            """
            SELECT
                *
            FROM
                purchases
            WHERE
                user_id = $1
                AND product_name = $2
                AND guild_id IS NULL
            ORDER BY 
                timestamp DESC 
            LIMIT 1
            """,
            int(user_id),
            product_name,
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
