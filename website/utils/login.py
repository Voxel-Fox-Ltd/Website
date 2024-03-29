from __future__ import annotations
from typing import Callable, Awaitable, Any

from aiohttp.web import Request, StreamResponse, HTTPFound
import aiohttp_session
from discord.ext import vbu

__all__ = (
    '_require_login_wrapper',
    'requires_login',
    'requires_manager_login',
)


RouteOutput = StreamResponse | dict[Any, Any]
RouteFunc = Callable[[Request], Awaitable[RouteOutput]]
RouteWrapper = Callable[..., Callable[..., Awaitable[StreamResponse]]]


async def _require_login_wrapper(request: Request) -> StreamResponse | None:
    session = await aiohttp_session.get_session(request)
    if session.get('id') is None:
        session['redirect_on_login'] = str(request.url)
        return HTTPFound("/login")


def requires_login() -> RouteWrapper:
    def inner(func: RouteFunc):
        async def wrapper(request: Request) -> RouteOutput:
            if (x := await _require_login_wrapper(request)):
                return x
            return await func(request)
        return wrapper
    return inner  # pyright: ignore


def requires_manager_login(location: str = "/") -> RouteWrapper:
    """
    Check if the user is in the payment processor users.
    """

    def inner(func: RouteFunc):
        async def wrapper(request: Request) -> RouteOutput:
            if (x := await _require_login_wrapper(request)):
                return x
            session = await aiohttp_session.get_session(request)
            user_id = session['id']
            async with vbu.Database() as db:
                rows = await db.call(
                    """
                    SELECT
                        1
                    FROM
                        manager_users
                    WHERE
                        login_id = $1
                    """,
                    user_id,
                )
            if not rows:
                return HTTPFound(location)
            return await func(request)
        return wrapper
    return inner  # pyright: ignore
