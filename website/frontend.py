from urllib.parse import urlencode
import pathlib

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
@template("index.htm.j2")
async def index(request: Request):
    """
    Index page for the website.
    """

    return {
        "include_back_button": False,
        "data": get_project_file("index"),
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


@routes.get("/18")
@template("18.html.j2")
async def over_18(request: Request):
    """
    A page that shows when a person must have been born to be 18 on this current day.
    """

    return {}


@routes.get("/md/{filename:.+}")
@template("markdown.htm.j2")
async def markdown(request: Request):
    """
    Project page for the website.
    """

    # Get the user's target file
    filename: str = request.match_info["filename"]

    # Get the user's target file as a path
    try:
        assert ".." not in filename
    except AssertionError:
        return Response(status=401)
    filename = filename.lstrip("/")
    target_file = pathlib.Path(f"./website/static/docs/{filename}")
    try:
        assert target_file.exists()  # Make sure it exists
        assert filename.endswith(".md")  # Make sure it's a markdown file
    except AssertionError:
        return Response(status=404)

    # And send
    with target_file.open() as a:
        content = a.read()
    return {
        "filename": filename.split("/")[-1][:-3],
        "content": content,
    }
