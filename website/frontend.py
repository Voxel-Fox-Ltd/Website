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


async def get_github_readme_html(session, url:str) -> str:
    """
    Get the README text from a Github page as rendered HTML.
    """

    site = await session.get(url.rstrip("/").replace("://github.com", "://raw.githubusercontent.com") + "/master/README.md")
    if 300 > site.status >= 200:
        git_text = await site.text()
    else:
        return ""
    v = markdown2.markdown(git_text)
    return v.replace("\n", "").replace("<p></p>", "")


async def fill_git_text_field(session, project) -> None:
    """
    Fills the git_text attr of the given project dict.
    """

    git_url = project.get("github")
    project['git_text'] = ""
    if git_url:
        project['git_text'] = await get_github_readme_html(session, git_url)


async def get_projects_page(filename:str) -> dict:
    """
    Returns a nice ol dict that can be passed to projects.j2.
    """

    with open(f"projects/{filename}.toml") as a:
        data = toml.load(a)
    projects = data['project']
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*[fill_git_text_field(session, i) for i in projects])
    return {
        'projects': projects
    }


@routes.get("/")
@template("projects.html.j2")
async def index(request:Request):
    """
    Index page for the website.
    """

    x = await get_projects_page('index')
    x.update({'field': 'git_text', 'include_contact_details': True})
    return x


@routes.get("/gforms")
@webutils.requires_login()
async def gforms(request:Request):
    """
    Redirect to Google forms with given items filled in with session data.
    """

    # Get our login info
    session = await aiohttp_session.get_session(request)

    # Get the form info
    alias = request.query.get('a')
    form_id = request.query.get('f')
    username = request.query.get('u')
    user_id = request.query.get('i')

    # See if we need to grab it from the database
    if alias:
        async with request.app['database']() as db:
            rows = await db("SELECT * FROM google_forms_redirects WHERE alias=$1", alias)
        if not rows:
            return Response(text="No relevant form found.", status=404)
        username = rows[0].get('username_field_id', 0)
        user_id = rows[0].get('user_id_field_id', 0)
        form_id = rows[0]['form_id']
    elif None in [form_id, username, user_id]:
        return Response(text="Missing 'f', 'u', or 'i' param.", status=400)

    # Redirect them
    params = {
        f"entry.{username}": session['user_info']['username'] + '#' + str(session['user_info']['discriminator']),
        f"entry.{user_id}": str(session['user_id']),
    }
    return HTTPFound(f"https://docs.google.com/forms/d/e/{form_id}/viewform?{urlencode(params)}")

    # https://docs.google.com/forms/d/e/1FAIpQLSc0Aq9H6SOArocMT7QKa4APbTwAFgfbzLb6pryY0u-MWfO1-g/viewform?
    # usp=pp_url&entry.2031777926=owo&entry.1773918586=uwu


@routes.get("/invite")
@template('invite.j2')
async def invite(request:Request):
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
