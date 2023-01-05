import json
from datetime import datetime as dt
from typing import Optional, Literal
from typing_extensions import Self
import uuid

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
        self.success_sql: str = success_sql
        self.refund_sql: str = refund_sql
        self.cancel_sql: str = cancel_sql
        self.product_group: str = product_group
        self.per_guild: bool = per_guild

        self.description: str = description

        self.quantity: int = 1

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

    @classmethod
    def from_row(cls, row: dict) -> Self:
        return cls(**row)

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
