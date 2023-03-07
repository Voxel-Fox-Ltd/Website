import functools
import io
from typing import Tuple
import smtplib
import asyncio
import html
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from aiohttp.web import Request, RouteTableDef, Response, json_response
from aiohttp_jinja2 import render_string
import htmlmin
from PIL import Image
from discord.ext import vbu
from bs4 import BeautifulSoup, Tag
import imgkit
import markdown2


routes = RouteTableDef()


@routes.post('/discord/chatlog')
async def discord_handler(request: Request):
    """
    Creates you a Discord chatlog you might be able to use.

    Acceptable JSON data:
    {
        "guild_name": str,
        "channel_name": str,
        "category_name": str,
        "users": {
            int: {
                "color": int,
                "display_name": str,
                "username": str,
                "bot": bool,
            },
        },
        "messages": [
            {
                "author_id": str | int,
                "timestamp": int,
                "content": str,
                "attachments": list[str],
                "embeds": [
                    {
                        "color": int,
                        "author": {
                            "icon_url": str,
                            "name": str,
                            "url": str,
                        },
                        "title": str,
                        "url": str,
                        "description": str,
                        "fields": [
                            {
                                "name": str,
                                "value": str,
                            },
                        ],
                        "thumbnail": {"url": str},
                        "image": {"url": str},
                        "footer": {
                            "icon_url": str,
                            "text": str,
                        },
                        "timestamp": int,
                    },
                ]
            },
        ],
    }
    """

    with open("website/static/css/discord/core.min.css") as a:
        core_css = a.read()
    with open("website/static/css/discord/dark.min.css") as a:
        dark_css = a.read()
    rendered_template: str = render_string(
        "discord_page.html.j2",
        request,
        {
            "data": (await request.json()),
            "core_css": core_css,
            "dark_css": dark_css,
        },
    )
    response_data = htmlmin.minify(
        rendered_template,
        remove_comments=True,
        remove_empty_space=True,
        reduce_boolean_attributes=True
    )
    headers = {"Content-Type": "text/html"}
    if "image" in request.query:
        soup = BeautifulSoup(response_data, "html.parser")
        pre = soup.find(class_="preamble")
        assert isinstance(pre, Tag)
        try:
            pre.decompose()  # Remove from the containing page
        except Exception:
            pass
        subset = str(soup)

        loop = asyncio.get_running_loop()
        partial = functools.partial(
            imgkit.from_string,
            subset,
            None,
            options={"format": "png"},
        )
        response_data = await loop.run_in_executor(None, partial)
        headers = {"Content-Type": "image/png"}
    return Response(
        body=response_data,
        headers=headers,
    )


@routes.get("/colour")
async def colour(request: Request):
    """
    A HTTP get that produces a png of given HEX or RGB colour.

        /****** Colours *****/

        /colour?hex=ff00ff
        /colour?r=255&g=000&b=255

        - If not given enough arguments for R/G/B, it will assume missing tag
        is 255.
        - If both tags exist, hex is prioritised.
        - If no tags are given, image will be white.

        /****** Size *****/

        /colour?width=200&height=1000
        /colour?w=200&h=1000

        - Short and normal tags can be used mixed.
        - If dimensions not specified, image is 100px to 100px.
    """

    size_limit: Tuple[int, int] = (1000, 1000,)  # Maximum width and height of PNG
    image_size: Tuple[int, int] = (100, 100,)  # Base size values

    # Simple clamp function
    def clamp(numb: int, min_num: int, max_num: int) -> int:
        return max(min_num, min(numb, max_num))

    # I wish there was actual switch case ;w;
    image_colour: Tuple[int, int, int]
    if "hex" in request.query:
        value = request.query["hex"].lstrip("#")
        r, g, b = value[0:2], value[2:4], value[4:6]
        image_colour = (
            int(r, 16),
            int(g, 16),
            int(b, 16),
        )
    else:
        image_colour = (
            int(request.query.get("r", 255)),
            int(request.query.get("g", 255)),
            int(request.query.get("b", 255)),
        )

    # Work out the size
    width_req = request.query.get(
        "width",
        request.query.get("w", image_size[0]),
    )
    height_req = request.query.get(
        "height",
        request.query.get("h", image_size[1]),
    )
    image_size = (
        clamp(int(width_req), 1, size_limit[0]),
        clamp(int(height_req), 1, size_limit[1]),
    )

    # Image processing  m a g i c
    img = Image.new("RGB", image_size, color=image_colour)
    file = io.BytesIO()
    img.save(file, format="PNG")
    file.seek(0)

    # And respond
    headers = {
        "Content-Type": "image/png",
        "Cache-Control": "public, max-age=604800, immutable",
    }
    return Response(body=file.read(), headers=headers)


@routes.post("/send_email/commission")
async def send_email(request: Request):
    """
    Send an email over to Kae.
    """

    # Get body
    try:
        data = await request.json()
        if not data:
            raise ValueError()
    except Exception:
        return json_response(
            {
                "message": "Missing data.",
            },
            status=400,
        )

    # Make sure we have everything necessary
    required_keys: set[str] = {
        "from",
        "type",
        "content",
    }
    missing: set[str] = set()
    for requirement in required_keys:
        if requirement not in data:
            missing.add(requirement)
    if missing:
        return json_response(
            {
                "message": f"Missing keys: {', '.join(missing)}",
            },
            status=400,
        )

    # Build email
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Commission Enquiry via VoxelFox.co.uk"
    msg["To"] = "kae@voxelfox.co.uk"
    msg["From"] = "commissions.voxelfox.co.uk"
    msg["Reply-To"] = data['from']
    data_content_raw = data['content']
    data_content_str = data_content_raw.replace("\n", "\n\n")
    data_content = markdown2.markdown(data_content_str)
    content: str = (
        f'''<html>'''
        f'''<head>'''
        f'''  <style>'''
         '''    body {font-family: 'Century Gothic', 'Helvetica', sans-serif;}'''
         '''    #c {margin-left: 1em; padding-left: 1em; border-left: 2px solid black;}'''
         '''    #c p {margin: 0;}'''
         '''    #c blockquote {margin-left: 0; font-style: italic;}'''
         '''    #c blockquote:before {content: ">"; float: left; margin-right: 0.5em;}'''
        f'''  </style>'''
        f'''</head>'''
        f'''<body>'''
        f'''  <p>'''
        f'''    Commission type: <b>{data['type']}</b><br />'''
        f'''    Reply to: <b>{data['from']}</b>'''
        f'''  </p>'''
        f'''  <div id="c">{data_content}</div>'''
        f'''</body>'''
        f'''</html>'''
    )
    part1 = MIMEText(content, "plain")
    part2 = MIMEText(content, "html")
    msg.attach(part1)
    msg.attach(part2)

    # Send email
    s = smtplib.SMTP('localhost')
    task = (
        asyncio.get_running_loop()
        .run_in_executor(None, s.send_message, msg)
    )
    await asyncio.wait([task])
    s.quit()
    return json_response(
        {
            "message": f"Email sent!",
        },
        status=200,
    )
