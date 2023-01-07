from __future__ import annotations
import logging

from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from .db_util import CheckoutItem

log = logging.getLogger("vbu.voxelfox.webhook")


async def send_webhook(
    item: CheckoutItem,
    data: dict[str, Any]) -> None:
    """
    Send a webhook to the given URL with the given data.
    """

    if not item.webhook:
        return
    headers = {"Authorization": item.webhook_auth}
    url = item.webhook
    async with aiohttp.ClientSession() as session:
        log.info(f"Sending POST {item.webhook} {data}")
        resp = await session.post(url, json=data, headers=headers)
        body = await resp.read()
        log.info(f"POST {item.webhook} returned {resp.status} {body}")