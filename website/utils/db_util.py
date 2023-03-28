from __future__ import annotations

from datetime import datetime as dt
import logging
from typing import TYPE_CHECKING, Any
import uuid

from discord.ext import vbu

from .db_models import Purchase

if TYPE_CHECKING:
    from .db_models import LoginUser, CheckoutItem

__all__ = (
    'create_purchase',
    'fetch_purchase',
    'update_purchase',
)


log = logging.getLogger("vbu.voxelfox.purchase")


async def create_purchase(
        db: vbu.Database,
        user: LoginUser,
        product: CheckoutItem,
        *,
        quantity: int = 1,
        discord_guild_id: int | None = None,
        expiry_time: dt | None = None,
        cancel_url: str | None = None,
        timestamp: dt | None = None,
        # paypal_id: str | None = None,
        # stripe_id: str | None = None,
        identifier: str) -> Purchase:
    """
    Store a created purchase in the database.

    Parameters
    ----------
    db : vbu.Database
        An open database connection.
    user: LoginUser
        The user who you want to store the purchase for.
    product: CheckoutItem
        The item that the user is purchasing.
    quantity: int
        The quantity of the purchased item.
    discord_guild_id: int | None
        The ID of the guild associated with the purchase, if there is one.
    expiry_time: dt | None
        The expiry time for the purchase, should it be time limited.
    cancel_url: str | None
        The URL that needs to be POSTed to in order to cancel the subscription.
    timestamp: dt | None
        The timestamp that the transaction took place. Defaults to the current
        time.
    identifier: str
        An identifier for the purchase.
        For Stripe, this should be either the subscription ID (sub_XXX) for
        subscriptions, or a checkout session (cs_XXX) for single items.
        For PayPal, this should be the plan ID for subscriptions, or the
        transaction ID for single items.
    """

    added_rows = await db.call(
        """
        INSERT INTO
            purchases
            (
                user_id,
                product_id,
                discord_guild_id,
                expiry_time,
                cancel_url,
                timestamp,
                identifier,
                quantity
            )
        VALUES
            (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                $8
            )
        ON CONFLICT
            (identifier)
        DO UPDATE
        SET
            user_id = excluded.user_id,
            product_id = excluded.product_id,
            discord_guild_id = excluded.discord_guild_id,
            expiry_time = excluded.expiry_time,
            cancel_url = excluded.cancel_url,
            timestamp = excluded.timestamp,
            quantity = excluded.quantity
        RETURNING
            *
        """,
        user.id,  # user_id
        product.id,  # product_id
        discord_guild_id,  # discord_guild_id
        expiry_time,  # expiry_time
        cancel_url,  # cancel_url
        timestamp,  # timestamp
        identifier,  # identifier
        quantity,  # quantit
    )
    return Purchase.from_row(added_rows[0])


async def fetch_purchase(
        db: vbu.Database,
        user: LoginUser | None,
        product: CheckoutItem,
        *,
        discord_guild_id: int | None = None) -> list[Purchase]:
    """
    Fetch a purchase from the database.

    Parameters
    ----------
    db : vbu.Database
        An open database connection.
    user : LoginUser | None
        The user who purchased the item.
        This can only be ``None`` if a guild ID is provided.
    product : CheckoutItem
        The item that was purchased.
    discord_guild_id : int | None
        The guild that the item was purchased for. If this is given, the user
        parameter is ignored.
    """

    if discord_guild_id:
        check = "purchases.discord_guild_id"
    else:
        assert user
        check = "purchases.user_id"
    rows = await db.call(
        """
        SELECT
            purchases.*
        FROM
            purchases
        LEFT JOIN
            checkout_items
            ON purchases.product_id = checkout_items.id
        WHERE
            {0} = $1
            AND checkout_items.id = $2
        ORDER BY
            timestamp DESC
        """.format(check),
        int(discord_guild_id) if discord_guild_id else user.id,  # pyright: ignore
        product.id,
    )
    return [
        Purchase.from_row(r)
        for r in rows
    ]


MISSING: Any = object()


async def update_purchase(
        db: vbu.Database,
        id: uuid.UUID | str,
        *,
        delete: bool = False,
        discord_guild_id: int | None = MISSING,
        expiry_time: dt | None = MISSING,
        cancel_url: str | None = MISSING):
    """
    Update a purchase in the database.

    Parameters
    ----------
    db : vbu.Database
        An open database connection.
    id : str
        The ID of the purchase that you want to update.
    """

    if delete is True:
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
        return

    log.info("Updating purchase with ID %s" % id)
    kwargs = {
        "discord_guild_id": discord_guild_id,
        "expiry_time": expiry_time,
        "cancel_url": cancel_url,
    }
    kwargs = {i: o for i, o in kwargs.items() if o is not MISSING}
    await db.call(
        """
        UPDATE
            purchases
        SET
            {0}
        WHERE
            id = $1
        """.format(
            ", ".join(
                f"{key} = ${i + 2}"
                for i, key in enumerate(kwargs)
            )
        ),
        id,
        *kwargs.values(),
    )
