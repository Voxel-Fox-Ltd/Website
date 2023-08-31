from __future__ import annotations

from typing import Any, Generic, Literal, TypeAlias, TypeVar, TypedDict
from typing_extensions import NotRequired

__all__ = (
    'EventTypeObject',
    'Event',
    'DataList',
    'Plan',
    'Price',
    'PriceRecurring',
    'SubscriptionItem',
    'Subscription',
    'Refund',
    'Charge',
    'CheckoutSession',
    'Invoice',
    'InvoiceLineItem',
    'CheckoutSessionLineItem',
    'PaymentIntent',
)


Unused: TypeAlias = Any
Timestamp: TypeAlias = int
DLI = TypeVar("DLI")  # Data list item
ET = TypeVar("ET")  # Event type
ETO = TypeVar("ETO")  # Event type


class EventTypeObject(TypedDict, Generic[ETO]):
    object: ETO
    previous_attributes: NotRequired[dict[str, Any]]


class Event(TypedDict, Generic[ET]):
    id: str
    object: Literal["event"]
    data: EventTypeObject[ET]
    type: str
    created: Timestamp


class DataList(TypedDict, Generic[DLI]):
    """A dict with a list inside it. Thanks Stripe."""
    object: Literal["list"]
    data: list[DLI]
    has_more: bool
    total_count: int
    url: str


class Plan(TypedDict):
    """A Stripe subscription plan."""
    id: str
    object: Literal["plan"]
    amount: int
    amount_decimal: str
    billing_scheme: str
    created: Timestamp
    currency: str
    interval: str
    interval_count: int
    nickname: str | None
    product: str  # product ID
    active: bool
    metadata: dict[str, Any]


class Price(TypedDict):
    """The price of an item."""
    id: str
    object: Literal["price"]
    active: bool
    billing_scheme: str  # probably "per_unit"
    created: Timestamp
    currency: str
    nickname: str | None
    product: str  # product ID
    recurring: PriceRecurring
    type: str
    unit_amount: int
    unit_amount_decimal: str
    metadata: dict[str, Any]


class PriceRecurring(TypedDict):
    interval: str
    interval_count: int


class SubscriptionItem(TypedDict):
    """An item purchased in a Stripe subscription."""
    id: str
    object: Literal["subscription_item"]
    created: Timestamp
    plan: Plan
    price: Price
    quantity: int
    subscription: str  # subscription ID
    metadata: dict[str, Any]



class Subscription(TypedDict):
    """A user subscription from Stripe."""
    id: str
    object: Literal["subscription"]
    cancel_at: Timestamp | None
    cancel_at_period_end: bool
    canceled_at: Timestamp | None
    created: Timestamp
    currency: str
    current_period_end: Timestamp
    current_period_start: Timestamp
    customer: str  # customer ID
    description: str | None
    ended_at: Timestamp | None
    items: DataList[SubscriptionItem]
    latest_invoice: str  # invoice ID
    metadata: dict[str, Any]
    plan: Plan
    quantity: int
    start_date: Timestamp


class Refund(TypedDict):
    id: str
    object: Literal["refund"]
    amount: int
    balance_transaction: str  # transaction ID
    charge: str  # charge ID
    created: Timestamp
    currency: str
    metadata: dict[str, Any]
    payment_intent: str  # payment intent ID
    reason: str | None
    status: str


class Charge(TypedDict):
    id: str
    object: Literal["charge"]
    amount: int
    amount_captured: int
    amount_refunded: int
    balance_transaction: str  # transaction ID
    calculated_statement_descriptor: str  # What shows up in a bank statement
    captured: bool
    created: Timestamp
    currency: str
    customer: str  # customer ID
    description: str
    invoice: str  # invoice ID
    livemode: bool
    metadata: dict[str, Any]
    paid: bool
    payment_intent: str  # payment intent ID
    payment_method: str  # payment method ID
    receipt_email: str | None  # the email the receipt goes to
    receipt_url: str
    refunded: bool
    refunds: DataList[Refund]
    status: str


class CheckoutSession(TypedDict):
    id: str
    object: Literal["checkout.session"]
    amount_subtotal: int
    amount_total: int
    cancel_url: str
    created: Timestamp
    currency: str
    customer: str  # customer ID
    expires_at: Timestamp
    invoice: str  # invoice ID
    livemode: bool
    metadata: dict[str, Any]
    mode: str
    payment_intent: str  # payment intent ID
    subscription: str | None  # subscription ID
    success_url: str
    url: str


class Invoice(TypedDict):
    id: str
    object: Literal["invoice"]
    auto_advance: bool
    charge: str
    collection_method: Literal["charge_automatically", "send_invoice"]
    currency: str
    customer: str
    description: str  # "memo" in the dashboard
    hosted_invoice_url: str
    lines: DataList[InvoiceLineItem]
    metadata: dict[str, str]
    payment_intent: str
    period_end: Timestamp
    period_start: Timestamp
    status: Literal["draft", "open", "paid", "uncollectible", "void"]
    subscription: str
    total: int


class InvoiceLineItem(TypedDict):
    id: str
    object: Literal["line_item"]
    amount: int
    amount_excluding_tax: int
    currency: str
    description: str
    discountable: bool
    invoice_item: str  # invoice item ID
    livemode: bool
    metadata: dict[str, Any]
    price: Price
    quantity: int
    subscription: str | None  # subscription ID
    type: Literal["invoiceitem"]
    unit_amount_excluding_tax: str


class CheckoutSessionLineItem(TypedDict):
    id: str
    object: Literal["item"]
    amount_discount: int
    amount_subtotal: int
    amount_tax: int
    amount_total: int
    currency: str
    description: str
    price: Price
    quantity: int


class PaymentIntent(TypedDict):
    id: str
    object: Literal["payment_intent"]
    amount: int
    automatic_payment_methods: Unused
    client_secret: Unused
    currency: str
    customer: str
    description: str
    last_payment_error: Unused
    latest_charge: str
    metadata: dict[str, str]
    next_action: Unused
    payment_method: str
    receipt_email: str
    setup_future_usage: Unused
    shipping: Unused
    statement_descriptor: str
    statement_descriptor_suffix: str
    status: Literal["requires_payment_method", "requires_confirmation", "requires_action", "processing", "requires_capture", "canceled", "succeeded"]
    invoice: str
