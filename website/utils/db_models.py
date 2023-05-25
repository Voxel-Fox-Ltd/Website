from __future__ import annotations

from datetime import datetime as dt
import logging
from typing import Any, Optional, overload
from typing_extensions import Self
import uuid

import aiohttp
from discord.ext import vbu

from .flags import RequiredLogins

__all__ = (
    'LoginUser',
    'CheckoutItem',
    'Purchase',
)


log = logging.getLogger("vbu.voxelfox.db_models")


MISSING: Any = object()


class LoginUser:
    """
    A user who is able to purchase items.

    Attributes
    ----------
    id : str
        The ID of the user.
    discord_user_id : str | None
    discord_refresh_token : str | None
    google_user_id : str | None
    google_refresh_token : str | None
    facebook_user_id : str | None
    facebook_refresh_token : str | None
    """

    __slots__ = (
        '_id',
        'discord_user_id',
        'discord_refresh_token',
        'google_user_id',
        'google_refresh_token',
        'facebook_user_id',
        'facebook_refresh_token',
    )

    def __init__(
            self,
            id: str | uuid.UUID,
            *,
            discord_user_id: str | None = None,
            discord_refresh_token: str | None = None,
            google_user_id: str | None = None,
            google_refresh_token: str | None = None,
            facebook_user_id: str | None = None,
            facebook_refresh_token: str | None = None):
        self._id = id
        self.discord_user_id = discord_user_id
        self.discord_refresh_token = discord_refresh_token
        self.google_user_id = google_user_id
        self.google_refresh_token = google_refresh_token
        self.facebook_user_id = facebook_user_id
        self.facebook_refresh_token = facebook_refresh_token

    @classmethod
    def from_row(cls, row: dict[str, Any]):
        return cls(
            id=row["id"],
            discord_user_id=row.get("discord_user_id"),
            discord_refresh_token=row.get("discord_refresh_token"),
            google_user_id=row.get("google_user_id"),
            google_refresh_token=row.get("google_refresh_token"),
            facebook_user_id=row.get("facebook_user_id"),
            facebook_refresh_token=row.get("facebook_refresh_token"),
        )

    @property
    def id(self) -> str:
        return str(self._id)

    @classmethod
    async def fetch(
            cls,
            db: vbu.Database,
            *,
            id: str | None = None,
            discord_user_id: str | None = None,
            google_user_id: str | None = None,
            facebook_user_id: str | None = None) -> Self | None:
        """
        Fetch a user from the database.

        Parameters
        ----------
        id: str | None
            The ID of the user.
        discord_user_id: str | None
            The ID of the user's Discord account.
        google_user_id: str | None
            The ID of the user's Google account.
        facebook_user_id: str | None
            The ID of the user's Facebook account.

        Returns
        -------
        Self | None
            The fetched user instance.
        """

        # Make sure we got something
        if all((
                id is None,
                discord_user_id is None,
                google_user_id is None,
                facebook_user_id is None)):
            return None
        if discord_user_id is not None:
            discord_user_id = str(discord_user_id)
        if google_user_id is not None:
            google_user_id = str(google_user_id)
        if facebook_user_id is not None:
            facebook_user_id = str(facebook_user_id)

        # Build our query
        query: str
        if id:
            query = "id = $1"
        elif discord_user_id:
            query = "discord_user_id = $1"
        elif google_user_id:
            query = "google_user_id = $1"
        elif facebook_user_id:
            query = "facebook_user_id = $1"
        else:
            raise ValueError("Missing query")

        # Fetch
        rows = await db.call(
            "SELECT * FROM login_users WHERE {0}".format(query),
            (
                id
                or discord_user_id
                or google_user_id
                or facebook_user_id
            ),
        )
        if not rows:
            return None
        return cls.from_row(rows[0])

    @classmethod
    async def create(
            cls,
            db: vbu.Database,
            *,
            discord_user_id: str | None = None,
            google_user_id: str | None = None,
            facebook_user_id: str | None = None) -> Self:
        """
        Create a new user.
        """

        rows = await db.call(
            """
            INSERT INTO
                login_users
                (
                    discord_user_id,
                    google_user_id,
                    facebook_user_id
                )
            VALUES
                (
                    $1,
                    $2,
                    $3
                )
            RETURNING *
            """,
            str(discord_user_id) if discord_user_id is not None else None,
            str(google_user_id) if google_user_id is not None else None,
            str(facebook_user_id) if facebook_user_id is not None else None,
        )
        return cls.from_row(rows[0])


class User:
    """
    A user in the database who can create checkout items.

    Attributes
    ----------
    id : str
        The ID of the user.
    stripe_id : str | None
        The ID of the user's Stripe account. If ``None``, then it's the user
        associated with the account rather than a connected account.
    paypal_id : str
        The ID of the account associated with the user's PayPal account.
    paypal_client_id : str
        The ID of an Oauth client that we can use to perform actions from the
        user's account.
    paypal_client_secret : str
        The secret of an Oauth client that we can use to perform actions from
        the user's account.
    """

    __slots__ = (
        '_id',
        'stripe_id',
        'paypal_id',
        'paypal_client_id',
        'paypal_client_secret',
    )

    def __init__(
            self,
            id: str | uuid.UUID,
            stripe_id: str | None,
            paypal_id: str | None,
            paypal_client_id: str | None,
            paypal_client_secret: str | None):
        self._id = id
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
            stripe_id=row.get('stripe_id'),
            paypal_id=row.get('paypal_id'),
            paypal_client_id=row.get('paypal_client_id'),
            paypal_client_secret=row.get('paypal_client_secret'),
        )

    @classmethod
    async def fetch(
            cls,
            db: vbu.Database,
            id: str | uuid.UUID) -> Self | None:
        """
        Get an account from the database by its ID.

        Parameters
        ----------
        db : vbu.Database
            An open database connection.
        id : str
            The ID of the account you want to fetch.

        Returns
        -------
        Self | None
            The fetched account, if exists.
        """

        row = await db.call(
            """SELECT * FROM payment_users WHERE id = $1""",
            id,
        )
        if row:
            return cls.from_row(row[0])
        return None


class CheckoutItem:
    """
    An item that you can purchase.

    Attributes
    ----------
    id : str
        The ID of the item.
    creator_id : str
        The ID of the person who created the item.
    name : str
        The name of the product.
    success_url : str
        The URL that the user is redirected to on successful transaction.
    cancel_url : str
        The URL that the user is redirected to on cancelled transaction.
    subscription : bool
        Whether or not the item is a subscription
    stripe_product_id : str
        The ID of the product on Stripe.
    stripe_price_id : str
        The ID of the product's price on Stripe.
    paypal_plan_id : str | None
        The ID of the associated PayPal plan.
    webhook : str | None
        A webhook to ping when the item is purchased or refunded.
    webhook_auth : str | None
        A string to go in the authorization header of the given webhook.
    product_group : str
        A group name that the product will be shown in the portal page for.
    per_guild : bool
        Whether or not the item is per guild (or per user).
    multiple : bool
        Whether or not the user is able to purchase multiple of this item.
        Ignored for subscriptions.
    required_logins : RequiredLogins
        The logins that are required to purchase the item.
    description : str
        The description of the item (in markdown).
    quantity : int
        The count of the item that will be purchased.
    purchased_quantity : int
        The amount of the item that *was* purchased. Defaults to the quantity
        from the database, but can be (and is intended to be) overridden if
        necessary.
    price : str | None
        A float string describing the item's price. May be ``None`` if the
        price hasn't been fetched.
    price_number : int
        An integer describing the item's price (in pence/cents). Will be ``0``
        until the item's price has been fetched.
    currency_code : str | None
        The currency code associated with the item's price. Requires the price
        to be fetched.
    currency_symbol : str | None
        The currency code associated with the item's price. Requires the price
        to be fetched.
    user : User | None
        The user who created the item.
    """

    __slots__ = (
        '_id',
        '_creator_id',
        'name',
        'success_url',
        'cancel_url',
        'subscription',
        'stripe_product_id',
        'stripe_price_id',
        'paypal_plan_id',
        'webhook',
        'webhook_auth',
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
        'purchased_quantity',
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
            required_logins: RequiredLogins):
        self._id = id
        self._creator_id = creator_id
        self.name: str = product_name
        self.success_url: str = success_url
        self.cancel_url: str = cancel_url
        self.subscription: bool = subscription
        self.stripe_product_id: str = stripe_product_id
        self.stripe_price_id: str = stripe_price_id
        self.paypal_plan_id: Optional[str] = paypal_plan_id
        self.webhook: str = transaction_webhook
        self.webhook_auth: str = transaction_webhook_authorization

        self.product_group: str = product_group
        self.per_guild: bool = per_guild
        self.multiple = multiple
        self.required_logins = required_logins

        self.description: str = description

        self.quantity: int = quantity
        self.purchased_quantity: int = quantity

        self.price: str | None = None
        self.price_number: int = 0
        self.currency_code: str | None = None
        self._currency_symbol: str | None = None

        self.user: User | None = None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id!s} name={self.name}>"

    @property
    def id(self) -> str:
        return str(self._id)

    @property
    def creator_id(self) -> str:
        return str(self._creator_id)

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

        Parameters
        ----------
        stripe_api_key : str
            The API key associated with the account you're fetching the price
            from.

        Returns
        -------
        str
            A formatted price string.
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
            required_logins=RequiredLogins(row['required_logins']),
        )

    @classmethod
    async def fetch(
            cls,
            db: vbu.Database,
            id: str) -> Self | None:
        """
        Get a checkout item instance from the database by its ID. The ID should
        be a UUID, but to support "user input", this isn't necessary.

        Parameters
        ----------
        db : vbu.Database
            An open database instance.
        id : str
            The product ID.

        Returns
        -------
        Self | None
            The fetched checkout item instance.
        """

        # Make sure the ID is valid
        try:
            uuid.UUID(id)
        except ValueError:
            return None

        # Get the data
        item_rows = await db.call(
            """
            SELECT
                *
            FROM
                checkout_items
            WHERE
                id = $1
            """,
            id,
        )

        # And done
        if not item_rows:
            return None
        return cls.from_row(item_rows[0])

    @classmethod
    async def fetch_by_product_id(
            cls,
            db: vbu.Database,
            id: str) -> Self | None:
        """
        Get a checkout item instance from the database by its Stripe product ID.

        Parameters
        ----------
        db : vbu.Database
            An open database instance.
        id : str
            The product ID.

        Returns
        -------
        Self | None
            The fetched checkout item instance.
        """

        # Get the data
        item_rows = await db.call(
            """
            SELECT
                *
            FROM
                checkout_items
            WHERE
                stripe_product_id = $1
            """,
            id,
        )

        # And done
        if not item_rows:
            return None
        return cls.from_row(item_rows[0])

    @classmethod
    async def fetch_by_name(
            cls,
            db: vbu.Database,
            product_name: str) -> Self | None:
        """
        Fetch a checkout item from the database via its name.

        Parameters
        ----------
        db : vbu.Database
            An open database instance.
        product_name : str
            The name of the product.
        paypal_id : str | None
            The ID of the associated user's PayPal account.
        stripe_id : str | None
            The ID of the associated user's Stripe account.

        Returns
        -------
        Self | None
            The retrieved instance, if there's one to retrieve.
        """

        # Fetch the item from the database
        # if (paypal_id, stripe_id,) == (None, None,):
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

        # Return the fetched item
        if not item_rows:
            return None
        items = [cls.from_row(i) for i in item_rows]
        if len(items) > 1:
            log.error("Multiple items found (%s)", items)
            raise Exception("Multiple items found.")
        await items[0].fetch_user(db)
        return items[0]

    async def fetch_user(self, db: vbu.Database) -> User:
        """
        Fetch the user who created the item.
        """

        user = await User.fetch(db, self.creator_id)
        assert user
        self.user = user
        return user


class Purchase:
    """
    An item that was purchased and stored in the database.

    Attributes
    ----------
    id : str
        The ID of the purchase.
    quantity : int
        The number of items that were purchased.
    identifier : str
        The identifier for the purchased.
    product_id : str
        The ID of the product that was purchased.
    user_id : str
        The ID of the user who purchased the product.
    discord_user_id : int | None
        Deprecated. The ID of the Discord account that purchased the item.
    discord_guild_id : int | None
        The ID of the guild associated with the purchase.
    cancel_url : str | None
        The cancel URL for the purchase.
    expiry_time : datetime.datetime | None
        The time that the subscription expires. May be ``None`` if the item
        isn't a subscription.
    timestamp : datetime.datetime
        The timestamp for the item's purchase.
    """

    __slots__ = (
        '_id',
        'quantity',
        'identifier',
        '_product_id',
        '_user_id',
        'discord_user_id',
        'discord_guild_id',
        'cancel_url',
        'expiry_time',
        'timestamp',
        '_item',
    )

    def __init__(
            self,
            id: str | uuid.UUID,
            quantity: int,
            identifier: str,
            product_id: str | uuid.UUID,
            user_id: str | uuid.UUID,
            discord_user_id: int | None,
            discord_guild_id: int | None,
            cancel_url: str | None,
            expiry_time: dt | None,
            timestamp: dt):
        self._id = str(id)
        self.quantity = quantity
        self.identifier = identifier
        self._product_id = str(product_id)
        self._user_id = str(user_id)
        self.discord_user_id = discord_user_id
        self.discord_guild_id = discord_guild_id
        self.cancel_url = cancel_url
        self.expiry_time = expiry_time
        self.timestamp = timestamp
        self._item: CheckoutItem | None = None

    @property
    def id(self) -> str:
        return str(self._id)

    @property
    def product_id(self) -> str:
        return str(self._product_id)

    @property
    def user_id(self) -> str:
        return str(self._user_id)

    @classmethod
    def from_row(cls, data: dict[str, Any]) -> Self:
        return cls(
            id=data['id'],
            quantity=data['quantity'],
            identifier=data['identifier'],
            product_id=data['product_id'],
            user_id=data['user_id'],
            discord_user_id=data['discord_user_id'],
            discord_guild_id=data['discord_guild_id'],
            cancel_url=data['cancel_url'],
            expiry_time=data['expiry_time'],
            timestamp=data['timestamp'],
        )

    @classmethod
    async def fetch_by_identifier(
            cls,
            db: vbu.Database,
            id: str) -> Self | None:
        """
        Get an item from the database given its identifying ID.

        Parameters
        ----------
        db : vbu.Database
            An open database connection.
        id : str
            The identifier in question.
        """

        rows = await db.call(
            "SELECT * FROM purchases WHERE identifier = $1",
            id,
        )
        if rows:
            return cls.from_row(rows[0])
        return None

    @overload
    @classmethod
    async def fetch_by_user(
            cls,
            db: vbu.Database,
            user: LoginUser,
            product: CheckoutItem | None = None,
            *,
            discord_guild_id: None = ...) -> list[Purchase]:
        ...

    @overload
    @classmethod
    async def fetch_by_user(
            cls,
            db: vbu.Database,
            user: None,
            product: CheckoutItem | None = None,
            *,
            discord_guild_id: int = ...) -> list[Purchase]:
        ...

    @classmethod
    async def fetch_by_user(
            cls,
            db: vbu.Database,
            user: LoginUser | None,
            product: CheckoutItem | None = None,
            *,
            discord_guild_id: int | None = MISSING) -> list[Purchase]:
        """
        Fetch a purchase from the database.

        Parameters
        ----------
        db : vbu.Database
            An open database connection.
        user : LoginUser | None
            The user who purchased the item.
            This can only be ``None`` if a guild ID is provided.
        product : CheckoutItem | None
            The item that was purchased.
        discord_guild_id : int
            The guild that the item was purchased for. If this is given,
            the user parameter is ignored.
        """

        # Work out what we're searching by
        if discord_guild_id is not MISSING:
            check = "purchases.discord_guild_id"
        else:
            assert user
            check = "purchases.user_id"

        # Call the database
        if product:
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
                (
                    int(discord_guild_id)
                    if discord_guild_id is not MISSING and discord_guild_id is not None
                    else user.id
                ),
                product.id,
            )
        else:
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
                ORDER BY
                    timestamp DESC
                """.format(check),
                (
                    int(discord_guild_id)
                    if discord_guild_id is not MISSING and discord_guild_id is not None
                    else user.id
                ),
            )

        # Return rows
        return [
            cls.from_row(r)
            for r in rows
        ]

    async def delete(self, db: vbu.Database) -> None:
        """
        Delete this purchase from the database.
        """

        await self.update_by_id(db, self.id, delete=True)

    @staticmethod
    async def update_by_id(
            db: vbu.Database,
            id: uuid.UUID | str,
            *,
            delete: bool = False,
            discord_guild_id: int | None = MISSING,
            expiry_time: dt | None = MISSING,
            cancel_url: str | None = MISSING) -> Purchase | None:
        """
        Update (or delete) a purchase via its ID.

        Parameters
        ----------
        id : uuid.UUID | str
            The ID of the purchase.
        delete : bool
            Whether or not you want to delete the purchase.
        discord_guild_id : int | None
            The new ID for the guild associated with the purchase.
        expiry_time : datetime.datetime | None
            The expiry time associated with the purchase
        cancel_url : str | None
            The URL associated with cancelling the purchase.
        """

        if delete:
            log.info("Deleting purchase with ID %s" % id)
            await db.call("DELETE FROM purchases WHERE id = $1", id)
            return

    async def update(
            self,
            db: vbu.Database,
            *,
            discord_guild_id: int | None = MISSING,
            expiry_time: dt | None = MISSING,
            cancel_url: str | None = MISSING):
        """
        Update a purchase in the database.

        Parameters
        ----------
        db : vbu.Database
            An open database connection.
        """

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

    @classmethod
    async def create(
            cls,
            db: vbu.Database,
            user: LoginUser,
            product: CheckoutItem,
            *,
            quantity: int = 1,
            discord_guild_id: int | None = None,
            expiry_time: dt | None = None,
            cancel_url: str | None = None,
            timestamp: dt | None = None,
            identifier: str) -> Self:
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
            int(discord_guild_id) if discord_guild_id is not None else discord_guild_id,  # discord_guild_id
            expiry_time,  # expiry_time
            cancel_url,  # cancel_url
            timestamp or dt.utcnow(),  # timestamp
            identifier,  # identifier
            quantity,  # quantity
        )
        return Purchase.from_row(added_rows[0])

    async def fetch_product(self, db: vbu.Database) -> CheckoutItem:
        """
        Fetch the product associated with the purchase.
        """

        v = await CheckoutItem.fetch_by_product_id(db, self.product_id)
        assert v
        self._item = v
        return v
