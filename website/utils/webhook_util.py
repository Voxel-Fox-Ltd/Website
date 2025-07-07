from __future__ import annotations
import logging

from typing import TYPE_CHECKING, Any

import aiohttp
import asyncpg

if TYPE_CHECKING:
    from .db_util import CheckoutItem

__all__ = (
    'send_webhook',
    'send_sql',
)

log = logging.getLogger("vbu.voxelfox.webhook")


async def send_webhook(
        item: CheckoutItem,
        data: dict[str, Any]) -> None:
    """
    Send a webhook to the given URL with the given data.
    """

    if not item.webhook:
        log.info(f"No webhook found for item {item} {data}")
        return
    headers = {"Authorization": item.webhook_auth}
    url = item.webhook
    async with aiohttp.ClientSession() as session:
        log.info(f"Sending POST {item.webhook} {data}")
        try:
            resp = await session.post(url, json=data, headers=headers)
            body = await resp.read()
        except Exception:
            log.info("Error sending webhook", exc_info=True)
            raise
        log.info(f"POST {item.webhook} returned {resp.status} {body}")


async def send_sql(
        item: CheckoutItem,
        data: dict[str, Any]) -> None:
    """
    Execute given SQL with the provided data.
    """

    if not item.dsn or not item.sql:
        log.info(f"No SQL found for item {item} {data}")
        return
    conn = await asyncpg.connect(item.dsn)
    log.info(f"Executing SQL for {item} {data}")
    try:
        await conn.execute(item.sql.format(**data))
    except Exception:
        log.info("Error executing SQL", exc_info=True)
        raise
    finally:
        await conn.close()
    log.info(f"Executed SQL for {item} successfully")
