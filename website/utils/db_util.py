import json
from datetime import datetime as dt
from typing import Optional, Literal
from typing_extensions import Self
import uuid

import aiohttp
from discord.ext import vbu


__all__ = (
    'CheckoutItem',
    'store_transaction',
)


class CheckoutItem:

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
            external_dsn: str,
            check_sql: str,
            success_sql: str,
            refund_sql: str,
            cancel_sql: str,
            product_group: str,
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

        self.external_dsn: str = external_dsn
        self.check_sql: str = check_sql
        self.success_sql: str = success_sql
        self.refund_sql: str = refund_sql
        self.cancel_sql: str = cancel_sql
        self.product_group: str = product_group
        self.per_guild: bool = per_guild

        self.description: str = description

        self.quantity: int = 1

        self.price: str | None = None
        self.price_number: int = 0

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
            self.price = f"£{product_data['unit_amount'] / 100:.2f}"
            self.price_number = product_data['unit_amount']
        else:
            self.price = "£0.00"
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
            external_dsn=row['external_dsn'],
            check_sql=row.get('check_sql', None),
            success_sql=row.get('success_sql', None),
            refund_sql=row.get('refund_sql', None),
            cancel_sql=row.get('cancel_sql', None),
            product_group=row['product_group'],
            per_guild=row['per_guild'],
            description=row['description'],
        )

    @classmethod
    async def fetch(cls, db: vbu.Database, product_name: str) -> Optional[Self]:
        """
        Fetch an instance from the database.
        """

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
        if not item_rows:
            return None
        return cls.from_row(item_rows[0])


async def store_transaction(
        db: vbu.Database,
        timestamp: dt,
        source: Literal['Stripe', 'PayPal'],
        data: dict):
    await db.call(
        """
        INSERT INTO
            transactions
            (timestamp, source, data)
        VALUES
            ($1, $2, $3)
        """,
        timestamp,
        source,
        json.dumps(data),
    )
