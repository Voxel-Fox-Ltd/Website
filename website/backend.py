import json
from datetime import datetime as dt
from urllib.parse import unquote, parse_qs
import hmac
from hashlib import sha1

import aiohttp
from aiohttp.web import HTTPFound, Request, RouteTableDef, Response
from voxelbotutils import web as webutils
import aiohttp_session
import discord
from aiohttp_jinja2 import template, render_template
import htmlmin
import pytz


routes = RouteTableDef()


@routes.get('/login_processor')
async def login_processor(request:Request):
    """
    Page the discord login redirects the user to when successfully logged in with Discord.
    """

    v = await webutils.process_discord_login(request)
    if isinstance(v, Response):
        return v
    session = await aiohttp_session.get_session(request)
    return HTTPFound(location=session.pop('redirect_on_login', '/'))


@routes.get('/logout')
async def logout(request:Request):
    """
    Destroy the user's login session.
    """

    session = await aiohttp_session.get_session(request)
    session.invalidate()
    return HTTPFound(location='/')


@routes.get('/login')
async def login(request:Request):
    """
    Direct the user to the bot's Oauth login page.
    """

    return HTTPFound(location=webutils.get_discord_login_url(request, "/login_processor"))


@routes.post('/discord/chatlog')
async def discord_handler(request:Request):
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
async def webhook_handler(request:Request):
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
