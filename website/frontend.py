from urllib.parse import urlencode

import aiohttp
from aiohttp.web import RouteTableDef, Request, HTTPFound, Response
from aiohttp.web_routedef import route
from aiohttp_jinja2 import template
import aiohttp_session
from voxelbotutils import web as webutils

import toml

routes = RouteTableDef()

@routes.get("/")
@template("index/display.htm.j2")
async def index(request: Request):
    """
    Index page for the website.
    """

    with open("projects/index.toml") as a:
        data = toml.load(a)
    return {
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

    if "https://discordapp.com" in request.headers.get("User-Agent"):
        async with aiohttp.ClientSession() as request:
            async with request.get(f"https://discord.com/api/oauth2/applications/{client_id}/rpc") as resp:
                json = await resp.json()
                if resp.status == 200:
                    return {**default_data, **json}
                return default_data
    return HTTPFound(redirect_link)
