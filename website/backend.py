import io
from typing import Tuple

from aiohttp.web import HTTPFound, Request, RouteTableDef, Response
import aiohttp_session
from aiohttp_jinja2 import render_template
import htmlmin
from PIL import Image
from discord.ext import vbu


routes = RouteTableDef()


@routes.post('/discord/chatlog')
async def discord_handler(request: Request):
    """
    Creates you a Discord chatlog you might be able to use.
    """

    with open('website/static/css/discord/core.min.css') as a:
        core_css = a.read()
    with open('website/static/css/discord/dark.min.css') as a:
        dark_css = a.read()
    rendered_template: Response
    rendered_template = render_template('discord_page.html.j2', request, {
        'data': (await request.json()),
        'core_css': core_css,
        'dark_css': dark_css,
    })
    response_text = htmlmin.minify(
        rendered_template.text,
        remove_comments=True,
        remove_empty_space=True,
        reduce_boolean_attributes=True
    )
    rendered_template.text = response_text
    return rendered_template


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
