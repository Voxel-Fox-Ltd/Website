from urllib.parse import urlencode

import aiohttp
from aiohttp.web import RouteTableDef, Request, HTTPFound, Response
from aiohttp_jinja2 import template
import aiohttp_session
from voxelbotutils import web as webutils
import toml


routes = RouteTableDef()


def get_project_file(filename: str) -> list:
    with open(f"projects/{filename}.toml") as a:
        data = toml.load(a)
    return data  # type: ignore


@routes.get("/")
@template("index/display.htm.j2")
async def index(request: Request):
    """
    Index page for the website.
    """

    return {
        "include_back_button": False,
        "data": get_project_file("index"),
    }


@routes.get("/p/{project}")
@template("index/display.htm.j2")
async def project(request: Request):
    """
    Project page for the website.
    """

    try:
        request.match_info["project"]
        data = get_project_file(request.match_info["project"])
    except Exception:
        return HTTPFound("/")
    return {
        "include_back_button": True,
        "data": data,
    }


@routes.get("/gforms")
@webutils.requires_login()
async def gforms(request: Request):
    """
    Redirect to Google forms with given items filled in with session data.
    """

    # Get our login info
    session = await aiohttp_session.get_session(request)

    # Get the form info
    alias = request.query.get('a')
    form_id = request.query.get('f', None)
    username = request.query.getall('u', list())
    user_id = request.query.getall('i', list())

    # See if we need to grab it from the database
    if alias:
        async with request.app['database']() as db:
            rows = await db("SELECT * FROM google_forms_redirects WHERE alias=$1", alias)
        if not rows:
            return Response(text="No relevant form found.", status=404)
        username = [rows[0].get('username_field_id', 0)]
        user_id = [rows[0].get('user_id_field_id', 0)]
        form_id = rows[0]['form_id']
    elif form_id is None:
        return Response(text="Missing 'f' param.", status=400)

    # Redirect them
    params = {
        **{f"entry.{u}": session['user_info']['username'] + '#' + str(session['user_info']['discriminator']) for u in username},
        **{f"entry.{i}": str(session['user_id']) for i in user_id},
    }
    return HTTPFound(f"https://docs.google.com/forms/d/e/{form_id}/viewform?{urlencode(params)}")

    # https://docs.google.com/forms/d/e/1FAIpQLSc0Aq9H6SOArocMT7QKa4APbTwAFgfbzLb6pryY0u-MWfO1-g/viewform?
    # usp=pp_url&entry.2031777926=owo&entry.1773918586=uwu


@routes.get("/invite")
@template("invite.html.j2")
async def invite(request: Request):
    """
    The passthrough embedded invite link.
    """

    client_id = request.rel_url.query.get("client_id", None)
    redirect_link = f"https://discord.com/oauth2/authorize?{urlencode(request.rel_url.query)}"
    default_data = {"name": "Bot", "description": "", "redirect_link": redirect_link}
    if client_id is None:
        return default_data

    if "https://discordapp.com" in request.headers.get("User-Agent", ""):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://discord.com/api/oauth2/applications/{client_id}/rpc") as resp:
                json = await resp.json()
                if resp.status == 200:
                    return {**default_data, **json}
                return default_data
    return HTTPFound(redirect_link)


@routes.get("/18")
@template("18.html.j2")
async def over_18(request: Request):
    """
    A page that shows when a person must have been born to be 18 on this current day.
    """

    return {}
