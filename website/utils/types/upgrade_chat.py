from typing import Any, Literal, TypedDict


__all__ = (
    'UpgradeChatUser',
    'UpgradeChatProduct',
    'UpgradeChatOrderItem',
    'UpgradeChatOrder',
    'UpgradeChatWebhookEvent',
    'UpgradeChatValidation',
)


class UpgradeChatUser(TypedDict):
    discord_id: str | None
    username: str | None


class UpgradeChatProduct(TypedDict):
    uuid: str
    name: str


class UpgradeChatOrderItem(TypedDict):
    product: UpgradeChatProduct


class UpgradeChatOrder(TypedDict):
    uuid: str
    purchased_at: str
    payment_processor: Literal["PAYPAL", "STRIPE"]
    payment_processor_record_id: str
    user: UpgradeChatUser
    subtotal: float
    discount: float
    total: float
    coupon_code: str | None
    coupon: dict[str, Any]
    type: Literal["UPGRADE", "SHOP"]
    is_subscription: bool
    cancelled_at: str | None
    deleted: str | None
    order_items: list[UpgradeChatOrderItem]


class UpgradeChatWebhookEvent(TypedDict):
    id: str
    webhook_id: str
    type: Literal["order.created", "order.updated", "order.deleted"]
    attempts: int

    body: UpgradeChatOrder
    data: UpgradeChatOrder


class UpgradeChatValidation(TypedDict):
    valid: bool
