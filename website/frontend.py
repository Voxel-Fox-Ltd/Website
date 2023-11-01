from urllib.parse import urlencode
import pathlib

from aiohttp.web import RouteTableDef, Request, HTTPFound, Response
from aiohttp_jinja2 import template
import aiohttp_session
from discord.ext import vbu

from .utils.login import requires_login


routes = RouteTableDef()


@routes.get("/")
@template("index.htm.j2")
async def index(_: Request):
    """
    Index page for the website.
    """

    target = pathlib.Path("./website/static/docs")
    markdown_files: dict[str, str] = {}
    if target.exists():
        for fn in target.rglob("*.md"):
            with fn.open() as a:
                markdown_files[fn.name.split(".")[0]] = a.read()

    return {
        "mdfiles": markdown_files,
    }


@routes.get("/gforms")
@requires_login()
async def gforms(request: Request):
    """
    Redirect to Google forms with given items filled in with session data.
    """

    # Get our login info
    session = await aiohttp_session.get_session(request)
    if "discord" not in session:
        session["login_message"] = "Discord login is required."
        return HTTPFound("/login")

    # Get the form info
    alias = request.query.get('a')
    form_id = request.query.get('f', None)
    username = request.query.getall('u', list())
    user_id = request.query.getall('i', list())

    # See if we need to grab it from the database
    if alias:
        async with vbu.Database() as db:
            rows = await db.call(
                """
                SELECT
                    *
                FROM
                    google_forms_redirects
                WHERE
                    alias = $1
                """,
                alias,
            )
        if not rows:
            return Response(
                text="No relevant form found.",
                status=404,
            )
        username = [rows[0].get('username_field_id', 0)]
        user_id = [rows[0].get('user_id_field_id', 0)]
        form_id = rows[0]['form_id']
    elif form_id is None:
        return Response(
            text="Missing 'f' param.",
            status=400,
        )

    # Redirect them
    uif = session["discord"]
    params = {
        **{
            f"entry.{i}": f"{uif['id']}"
            for i in user_id
        },
    }
    if "username" in uif:
        params.update({
            f"entry.{u}": uif['username']
            for u in username
        })
    return HTTPFound(
        f"https://docs.google.com/forms/d/e/{form_id}"
        f"/viewform?{urlencode(params)}"
    )


@routes.get("/18")
@template("18.html.j2")
async def over_18(_: Request):
    """
    A page that shows when a person must have been born to be 18 on this
    current day.
    """

    return {}


@routes.get("/tts")
@template("tts.htm.j2")
async def twitch_tts(_: Request):
    """
    Twitch TTS moment.
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
        if not target_file.exists():
            raise AssertionError
        if not filename.endswith(".md"):
            raise AssertionError
    except AssertionError:
        return Response(status=404)

    # And send
    with target_file.open() as a:
        content = a.read()
    return {
        "filename": filename.split("/")[-1][:-3],
        "content": content,
    }


@routes.get("/{_}")
@template("index.htm.j2")
async def index_double(_: Request):
    """
    Index page for the website. Fallback for missing `/`
    """

    target = pathlib.Path("./website/static/docs")
    markdown_files: dict[str, str] = {}
    if target.exists():
        for fn in target.rglob("*.md"):
            with fn.open() as a:
                markdown_files[fn.name.split(".")[0]] = a.read()

    return {
        "mdfiles": markdown_files,
    }
