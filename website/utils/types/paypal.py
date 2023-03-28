from typing import TypedDict
from typing_extensions import NotRequired

__all__ = (
    'IPNMessage',
)


class IPNMessage(TypedDict):
    address_city: NotRequired[str]
    address_country: NotRequired[str]
    address_country_code: NotRequired[str]
    address_name: NotRequired[str]
    address_state: NotRequired[str]
    address_status: NotRequired[str]
    address_street: NotRequired[str]
    address_zip: NotRequired[str]
    btn_id: NotRequired[str]
    business: str
    charset: str
    custom: NotRequired[str]
    discount: str
    exchange_rate: NotRequired[str]
    first_name: str
    insurance_amount: str
    invoice: NotRequired[str]
    ipn_track_id: str
    item_name: str
    item_number: NotRequired[str]
    last_name: str
    mc_currency: str
    mc_fee: str
    mc_gross: str
    mp_currency: NotRequired[str]
    mp_custom: NotRequired[str]
    mp_cycle_start: NotRequired[str]
    mp_desc: NotRequired[str]
    mp_id: NotRequired[str]
    mp_status: NotRequired[str]
    notify_version: str
    payer_business_name: NotRequired[str]
    payer_email: str
    payer_id: str
    payer_status: str
    payment_date: str
    payment_fee: NotRequired[str]
    payment_gross: NotRequired[str]
    payment_status: str
    payment_type: str
    protection_eligibility: str
    quantity: str
    receiver_email: str
    receiver_id: str
    residence_country: str
    settle_amount: NotRequired[str]
    settle_currency: NotRequired[str]
    shipping: NotRequired[str]
    shipping_discount: str
    shipping_method: str
    transaction_subject: NotRequired[str]
    txn_id: str
    txn_type: str
    verify_sign: str
    recurring_payment_id: NotRequired[str]
