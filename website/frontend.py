# import re
import toml
from urllib.parse import quote
import asyncio

import aiohttp
from aiohttp.web import RouteTableDef, Request, HTTPFound, Response
from aiohttp_jinja2 import template
import aiohttp_session
from voxelbotutils import web as webutils
import markdown2


routes = RouteTableDef()


# image_matcher = re.compile(r'!\[(.+?)?\]\((.+?)(?: \"(.+?)\")?\)', re.MULTILINE)
# url_matcher = re.compile(r'\[(.+?)\]\((.+?)(?: \"(.+?)\")?\)', re.MULTILINE)
# italics_matcher = re.compile(r'_(.+?)_', re.MULTILINE)
# bold_matcher = re.compile(r'\*\*(.+?)\*\*', re.MULTILINE)
# code_matcher = re.compile(r'`(.+?)`', re.MULTILINE)
# italics2_matcher = re.compile(r'\*(.+?)\*', re.MULTILINE)
# header_matcher = re.compile(r'^(#+) (.+)$', re.MULTILINE)


# def get_html_from_markdown(text:str) -> str:
#     """
#     Takes in some markdown text and returns rendered HTML.
#     """

#     new_text = []
#     for line in text.strip().split("\n"):
#         line = line.strip()
#         if not line:
#             continue
#         line = image_matcher.sub(lambda m: f'<img src="{m.group(2)}" alt="{m.group(3) or ""}" />', line)
#         line = url_matcher.sub(lambda m: f'<a href="{m.group(2)}" alt="{m.group(3) or ""}" target="_blank">{m.group(1)}</a>', line)
#         line = italics_matcher.sub(lambda m: f'<i>{m.group(1)}</i>', line)
#         line = bold_matcher.sub(lambda m: f'<b>{m.group(1)}</b>', line)
#         line = code_matcher.sub(lambda m: f'<code>{m.group(1)}</code>', line)
#         line = italics2_matcher.sub(lambda m: f'<i>{m.group(1)}</i>', line)
#         line = header_matcher.sub(lambda m: f'<h{len(m.group(1))}>{m.group(2)}</h{len(m.group(1))}>', line)
#         if not line.startswith(("<h", "<img",)):
#             line = f"<p>{line}</p>"
#         new_text.append(line)
#     return "".join(new_text).strip()


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

    session = await aiohttp_session.get_session(request)
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
        f"entry.{rows[0].get('username_field_id', 0)}={quote(session['user_info']['username'] + '#' + str(session['user_info']['discriminator']))}&"
        f"entry.{rows[0].get('user_id_field_id', 0)}={quote(str(session['user_id']))}"
    ))
