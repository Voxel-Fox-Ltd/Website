import time
import io
import json

import aiohttp
from aiohttp.web import HTTPFound, Request, RouteTableDef, Response
from voxelbotutils import web as webutils
import aiohttp_session
from aiohttp_jinja2 import render_template
import htmlmin
from PIL import Image


routes = RouteTableDef()


@routes.get('/login_processor')
async def login_processor(request: Request):
    """
    Page the discord login redirects the user to when successfully logged in with Discord.
    """

    v = await webutils.process_discord_login(request)
    if isinstance(v, Response):
        return v
    session = await aiohttp_session.get_session(request)
    return HTTPFound(location=session.pop('redirect_on_login', '/'))


@routes.get('/logout')
async def logout(request: Request):
    """
    Destroy the user's login session.
    """

    session = await aiohttp_session.get_session(request)
    session.invalidate()
    return HTTPFound(location='/')


@routes.get('/login')
async def login(request: Request):
    """
    Direct the user to the bot's Oauth login page.
    """

    return HTTPFound(location=webutils.get_discord_login_url(request, "/login_processor"))


@routes.post('/discord/chatlog')
async def discord_handler(request: Request):
    """
    Creates you a Discord chatlog you might be able to use.
    """

    with open('website/static/css/discord/core.min.css') as a:
        core_css = a.read()
    with open('website/static/css/discord/dark.min.css') as a:
        dark_css = a.read()
    rendered_template: Response = render_template('discord_page.html.j2', request, {
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


@routes.post('/webhooks/topgg/vote_added')
async def webhook_handler(request: Request):
    """
    Sends a PM to the user with the webhook attached if user in owners.
    """

    # See if we can get it
    try:
        request_data = await request.json()
    except Exception:
        request.app['logger'].info("Error parsing TopGG webhook")
        return Response(status=400)

    # See if it's all valid
    keys = set(['bot', 'user', 'type'])
    if not set(request_data.keys()).issuperset(keys):
        request.app['logger'].info("Error parsing TopGG webhook - invalid keys")
        return Response(status=400)

    # Get the bot's ID
    try:
        bot_id = int(request_data['bot'])
    except ValueError:
        request.app['logger'].info("Error parsing TopGG webhook - invalid bot")
        return Response(status=400)

    # Get the user's ID
    try:
        user_id = int(request_data['user'])
    except ValueError:
        request.app['logger'].info("Error parsing TopGG webhook - invalid user")
        return Response(status=400)

    # Grab data from the config
    try:
        webhook_data = [i for i in request.app['config']['topgg_bot_webhooks'] if i['bot_id'] == bot_id][0]
    except IndexError:
        request.app['logger'].info(f"No TopGG passthrough webhook set for bot ID {bot_id}")
        return Response(status=400)

    # Check type
    if request_data['type'] not in ['upvote', 'test']:
        request.app['logger'].info("Error parsing TopGG webhook - invalid webhook type")
        return Response(status=400)

    # Check auth token from topgg
    if request.headers.get('Authorization') != webhook_data['authorization']:
        request.app['logger'].info("Error parsing TopGG webhook - invalid authorization")
        return Response(status=400)

    # Generate webhook ping data
    response_data = {
        'bot_id': bot_id,  # Doesn't need to be present but eh why not
        'user_id': user_id,
        'type': request_data['type']
    }

    # Ping the webhook
    url = webhook_data['webhook_url']
    async with aiohttp.ClientSession(loop=request.app.loop) as session:
        headers = {"Authorization": webhook_data['authorization']}
        async with session.post(url, headers=headers, json=response_data):
            pass
    request.app['logger'].info(f"Pinged TopGG webhook data to {url}")

    return Response(status=200)


@routes.get("/colour")
async def colour(request: Request):
    """
    A HTTP get that produces a png of given HEX or RGB colour.

        /****** Colours *****/

        /colour?hex=#ff00ff
        /colour?r=255&g=000&b=255

        - If not given enough arguments for R/G/B, it will assume missing tag is 255.
        - If both tags exist, hex is prioritised.
        - If no tags are given, image will be white.

        /****** Size *****/

        /colour?width=200&height=1000
        /colour?w=200&h=1000

        - Short and normal tags can be used mixed.
        - If diementions not specified, image is 100px to 100px.
    """

    size_limit: list[int] = [1000, 1000]  # Maximum width and height of PNG
    image_size: list[int] = [100, 100]  # Base size values

    # Simple clamp function
    def clamp(numb: int, min_num: int, max_num: int) -> int:
        return max(min_num, min(int(numb), max_num))

    # I wish there was actual switch case ;w;
    image_colour: list[int] = None
    if "hex" in request.query:
        value = request.query["hex"].lstrip("#")
        r, g, b = value[0:2], value[2:4], value[4:6]    # value="ff00ff" -> r="ff, g="00", b="ff"
        image_colour = (int(r, 16), int(g, 16), int(b, 16))
    else:
        image_colour = (
            int(request.query.get("r", 255)),
            int(request.query.get("g", 255)),
            int(request.query.get("b", 255)),
        )

    # Work out the size
    if (value := request.query.get("width", request.query.get("w"))):
        image_size[0] = clamp(value, 1, size_limit[0])
    if (value := request.query.get("height", request.query.get("h"))):
        image_size[1] = clamp(value, 1, size_limit[1])

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


@routes.get("/bot_guild_count")
async def bot_guild_count(request: Request):
    """
    Get the guild counts for many bots
    """

    # Make our request
    headers = {
        "DD-API-KEY": request.app['config']['datadog']['api_key'],
        "DD-APPLICATION-KEY": request.app['config']['datadog']['application_key'],
    }
    params = {
        "to": time.time(),
        "from": time.time() - 100,
        "query": "max:discord.stats.guild_count{*} by {service}",
    }
    url = "https://api.datadoghq.com/api/v1/query"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as r:
            data = await r.json()
    bot_guilds = {i['scope'].split(":")[-1]: int(max(i['pointlist'])[1]) for i in data['series']}

    # And respond
    response_headers = {
        "Content-Type": "application/json",
        "Cache-Control": "public, max-age=3600, immutable",
    }
    return Response(body=json.dumps(bot_guilds).encode(), headers=response_headers)
