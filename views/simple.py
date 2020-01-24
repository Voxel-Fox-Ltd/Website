from aiohttp.web import RouteTableDef, Request
from aiohttp_jinja2 import template


routes = RouteTableDef()


@routes.get("/")
@template("index.j2")
async def index(request:Request):
    """Index page for the website"""

    return {}

