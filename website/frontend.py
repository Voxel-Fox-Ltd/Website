from urllib.parse import urlencode
import pathlib

from aiohttp.web import RouteTableDef, Request, HTTPFound, Response
from aiohttp_jinja2 import template
import aiohttp_session
from discord.ext import vbu

from .utils.login import requires_login


routes = RouteTableDef()


def page_builder(page_name: str, template_name: str):
    @routes.get(page_name)
    @template(template_name)
    async def wrapped(_: Request):
        return {}
    return wrapped


page_builder("/", "index.htm.j2")
page_builder("/main", "index.htm.j2")
page_builder("/index", "index.htm.j2")
page_builder("/contact", "contact.htm.j2")
page_builder("/branding", "branding.htm.j2")
page_builder("/projects", "projects.htm.j2")

page_builder("/tts", "project-pages/tts.htm.j2")


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
        if ".." in filename:
            raise AssertionError
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
