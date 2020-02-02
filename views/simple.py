import toml

from aiohttp.web import RouteTableDef, Request
from aiohttp_jinja2 import template


routes = RouteTableDef()


@routes.get("/")
@template("index.j2")
async def index(request:Request):
    """Index page for the website"""

    try:
        with open("projects.toml") as a:
            data = toml.load(a)
    except Exception:
        data = {'project': []}
    return {
        'projects': [i for i in data['project'] if i['name'] != 'example']
    }
