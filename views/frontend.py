import re as regex
import toml

from aiohttp.web import RouteTableDef, Request
from aiohttp_jinja2 import template


routes = RouteTableDef()


image_matcher = regex.compile(r'!\[(.+?)?\]\((.+?)\)')
url_matcher = regex.compile(r'\[(.+?)\]\((.+?) \"(.+?)\"\)')
italics_matcher = regex.compile(r'_(.+)_')


def get_projects_page(filename:str) -> dict:
    """
    Returns a nice ol dict that can be passed to projects.j2.
    """

    with open(f"projects/{filename}.toml") as a:
        data = toml.load(a)
    unchangeddata = [i for i in data['project'] if i['name'] != 'example']
    data = []
    for i in unchangeddata:
        i['description'] = italics_matcher.sub(lambda m: f'<i>{m.group(1)}</i>', i['description'])
        i['description'] = image_matcher.sub(lambda m: f'<img src="{m.group(2)}" />', i['description'])
        i['description'] = url_matcher.sub(lambda m: f'<a href="{m.group(2)}" alt="{m.group(3)}" target="_blank">{m.group(1)}</a>', i['description'])
        i['description'] = i['description'].strip()
        data.append(i)
    return {
        'projects': data
    }


@routes.get("/")
@template("projects.html.j2")
async def index(request:Request):
    """
    Index page for the website.
    """

    return get_projects_page('index')


@routes.get("/gforms")
async def gforms(request:Request):
    pass
