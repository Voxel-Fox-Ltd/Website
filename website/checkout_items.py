import toml
from urllib.parse import urlencode
import asyncio

import aiohttp
from aiohttp.web import RouteTableDef, Request, HTTPFound, Response
from aiohttp_jinja2 import template
import aiohttp_session
from voxelbotutils import web as webutils
import markdown2

routes = RouteTableDef()


@routes.get('/checkout_items')
@webutils.requires_login()
@template("data.htm.j2")
async def invite(request:Request):

    session = await aiohttp_session.get_session(request)
    if session['user_id'] not in [141231597155385344, 263691006120165387]:
        return HTTPFound('/')

    async with request.app['database']() as db:
        rows = await db("SELECT * FROM checkout_items")
        return {
            'data': rows
        }