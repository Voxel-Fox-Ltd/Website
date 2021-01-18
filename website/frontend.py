import re as regex
import toml
from urllib.parse import quote

from aiohttp.web import RouteTableDef, Request, HTTPFound, Response
from aiohttp_jinja2 import template
import aiohttp_session
from voxelbotutils import web as webutils


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
    """
    Redirect to Google forms with given items filled in with session data.
    """

    session = await aiohttp_session.get_session(request)
    if session.get("logged_in", False) is False:
        return HTTPFound("/login")

    alias = request.query.get('a')
    form_id = request.query.get('f')
    async with request.app['database']() as db:
        if alias:
            rows = await db("SELECT * FROM google_forms_redirects WHERE alias=$1", alias)
        else:
            rows = await db("SELECT * FROM google_forms_redirects WHERE form_id=$1", form_id)
    if not rows:
        return Response("No relevant form found.", status=404)
    # https://docs.google.com/forms/d/e/1FAIpQLSc0Aq9H6SOArocMT7QKa4APbTwAFgfbzLb6pryY0u-MWfO1-g/viewform?usp=pp_url&entry.2031777926=owo&entry.1773918586=uwu
    return HTTPFound((
        f"https://docs.google.com/forms/d/e/{rows[0]['form_id']}/viewform?"
        f"entry.{rows[0]['username_field_id']}={quote(session['user_info']['username'] + '#' + session['user_info']['discriminator'])}&"
        f"entry.{rows[0]['user_id_field_id']}={quote(session['user_id'])}"
    ))
