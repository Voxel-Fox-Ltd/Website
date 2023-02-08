from __future__ import annotations

from aiohttp.web import Request, StreamResponse, HTTPFound
import aiohttp_session

__all__ = (
    '_require_login_wrapper',
    'requires_login',
)


async def _require_login_wrapper(request: Request) -> StreamResponse | None:
    session = await aiohttp_session.get_session(request)
    if session.get('id') is None:
        session['redirect_on_login'] = str(request.url)
        return HTTPFound("/login")


def requires_login():
    def inner(func):
        async def wrapper(request: Request) -> StreamResponse:
            if (x := await _require_login_wrapper(request)):
                return x
            return await func(request)
        return wrapper
    return inner
