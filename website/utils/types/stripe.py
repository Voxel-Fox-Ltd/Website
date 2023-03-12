from __future__ import annotations

from typing import Any, Generic, Literal, TypeAlias, TypeVar, TypedDict
from typing_extensions import NotRequired


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

    api_version: Unused
    livemode: Unused
    pending_webhooks: Unused
    request: Unused


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

    aggregate_usage: Unused
    livemode: Unused
    tiers: Unused
    tiers_mode: Unused
    transform_usage: Unused
    trial_period_days: Unused
    usage_type: Unused


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

    custom_unit_amount: Unused
    livemode: Unused
    lookup_key: Unused
    tax_behavior: Unused
    tiers_mode: Unused
    transform_quantity: Unused


class PriceRecurring(TypedDict):
    interval: str
    interval_count: int

    aggregate_usage: Unused
    trial_period_days: Unused
    usage_type: Unused


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

    billing_thresholds: Unused
    tax_rates: Unused


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

    application: Unused
    application_fee_percent: Unused
    automatic_tax: Unused
    billing_cycle_anchor: Unused
    billing_thresholds: Unused
    cancellation_details: Unused
    collection_method: Unused
    days_until_due: Unused
    default_payment_method: Unused
    default_source: Unused
    default_tax_rates: Unused
    discount: Unused
    livemode: Unused
    next_pending_invoice_item_invoice: Unused
    on_behalf_of: Unused
    pause_collection: Unused
    payment_settings: Unused
    pending_invoice_item_interval: Unused
    pending_setup_intent: Unused
    pending_update: Unused
    tax_percent: Unused
    test_clock: Unused
    transfer_data: Unused
    schedule: Unused
    status: Unused
    trial_end: Unused
    trial_settings: Unused
    trial_start: Unused


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
    receipt_number: Unused
    source_transfer_reversal: Unused
    status: str
    transfer_reversal: Unused


class Charge(TypedDict):
    id: str
    object: Literal["charge"]
    amount: int
    amount_captured: int
    amount_refunded: int
    application: Unused
    application_fee: Unused
    application_fee_amount: Unused
    balance_transaction: str  # transaction ID
    billing_details: Unused  # address, name, etc
    calculated_statement_descriptor: str  # What shows up in a bank statement
    captured: bool
    created: Timestamp
    currency: str
    customer: str  # customer ID
    description: str
    destination: Unused
    dispute: Unused
    disputed: Unused
    failure_balance_transaction: Unused
    failure_code: Unused
    failure_message: Unused
    fraud_details: Unused
    invoice: str  # invoice ID
    livemode: bool
    metadata: dict[str, Any]
    on_behalf_of: Unused
    order: Unused
    outcome: Unused
    paid: bool
    payment_intent: str  # payment intent ID
    payment_method: str  # payment method ID
    payment_method_details: Unused
    receipt_email: str | None  # the email the receipt goes to
    receipt_number: Unused
    receipt_url: str
    refunded: bool
    refunds: DataList[Refund]
    review: Unused
    shipping: Unused
    source: Unused
    source_transfer: Unused
    statement_descriptor: Unused
    statement_descriptor_suffix: Unused
    status: str
    transfer_data: Unused
    transfer_group: Unused
