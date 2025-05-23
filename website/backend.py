import functools
import io
from typing import Literal, Tuple
import asyncio
import aiohttp
import re
from datetime import datetime

from aiohttp.web import Request, RouteTableDef, Response
from aiohttp_jinja2 import render_string
import htmlmin
from PIL import Image
from bs4 import BeautifulSoup, Tag
import imgkit
import ics


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
        "project-pages/discord_page.html.j2",
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


def calendar_names_are_similar(name1: str, name2: str) -> Literal[False] | str:
    """
    Return whether or not two calendar event names are "similar" (mostly according to Dylan's
    Rotacloud rules)
    """

    if name1 == name2:
        return name1

    regex = r"(.+) \((.+)\)"
    match1 = re.search(regex, name1)
    if match1 is None:
        return False
    match2 = re.search(regex, name2)
    if match2 is None:
        return False
    if match1.group(1) != match2.group(1):
        return False

    # everything from now will have the same group 1

    universal_shifts = set(["Meeting", "Auditorium Turnaround", "Training"])
    tech_shifts = set(["Tech", "Tech projection", "Tech Usher", "Followspot", "Outside Steward"])
    dm_shifts = set(["Duty Manager"])
    shift1 = set([i.strip() for i in match1.group(2).split(",")])
    shift2 = set([i.strip() for i in match2.group(2).split(",")])

    joined_shift = [i.strip() for i in match1.group(2).split(",")]
    for i in [i.strip() for i in match2.group(2).split(",")]:
        if i not in joined_shift:
            joined_shift.append(i)
    joined_name = f"{match1.group(1)} ({', '.join(joined_shift)})"

    if tech_shifts.union(universal_shifts).intersection(shift1) and tech_shifts.union(universal_shifts).intersection(shift2):
        return joined_name
    if dm_shifts.union(universal_shifts).intersection(shift1) and dm_shifts.union(universal_shifts).intersection(shift2):
        return joined_name
    if universal_shifts.intersection(shift1) and tech_shifts.union(dm_shifts).intersection(shift2):
        return joined_name

    return False


@routes.get("/calendar_filter")
async def calendar_filter(request: Request):
    """
    Filter certain things within a calendar.
    """

    url = request.query.get("url")
    if url is None:
        return Response(
            body="Missing URL param.",
            status=400,
            headers={"Access-Control-Allow-Origin": "*"},
        )

    async with aiohttp.ClientSession() as session:
        headers = {"User-Agent": "Voxel Fox calendar filter kae@voxelfox.co.uk"}
        site = await session.get(url, headers=headers)
        calendar_raw = await site.text()
    calendar = ics.Calendar(calendar_raw)

    filters = request.query.getall("filter")
    if filters:
        new_calendar = ics.Calendar()
        for event in calendar.events:
            add = True
            for f in filters:
                if f.casefold() in event.name.casefold():
                    add = False
                    break
            if not add:
                continue
            new_calendar.events.add(event)
        calendar = new_calendar

    combine_similar = request.query.get("combine_similar") is not None
    if combine_similar:
        new_calendar = ics.Calendar()
        previous: ics.Event | None = None
        for event in sorted(calendar.events, key=lambda e: e.begin):
            if previous is None:
                previous = event
                continue
            assert previous is not None
            new_name = calendar_names_are_similar(previous.name, event.name)
            if new_name is not False and previous.end == event.begin:
                if not isinstance(previous.description, str):
                    previous.description = ""
                previous.name = new_name
                previous.description += "\n----------\n" + (event.description or "")
                previous.end = event.end
            else:
                new_calendar.events.add(previous)
                previous = event
        if previous is not None:
            new_calendar.events.add(previous)
        calendar = new_calendar

    return Response(
        body=calendar.serialize(),
        headers={
            "Content-Type": "text/calendar",
            "Access-Control-Allow-Origin": "*",
        },
    )
