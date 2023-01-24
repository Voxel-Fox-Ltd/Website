from urllib.parse import urlencode
import logging

import aiohttp
from aiohttp.web import HTTPFound, Request, RouteTableDef, StreamResponse
import aiohttp_session
from aiohttp_jinja2 import template
from discord.ext import vbu


routes = RouteTableDef()
log = logging.getLogger("vbu.voxelfox.login")


"""
User Session
============
{
    "id?": str,
    "redirect_on_login?": str,
    "discord?": {
        "id": str,
        "refresh_token": str,
    },
}
"""


def always_return(location: str):
    def inner(func):
        async def wrapper(request: Request) -> StreamResponse:
            await func(request)
            return HTTPFound(location)
        return wrapper
    return inner


@routes.get('/login/discord')
@always_return('/login')
async def discord(request: Request):
    """
    Page the discord login redirects the user to when successfully logged in
    with Discord.
    """

    # Get the code
    code = request.query.get("code")
    if not code:
        return HTTPFound(location="/login")

    # Build the JSON response
    base_url = request.app['config']['website_base_url']
    discord_config = request.app['config']['oauth']['discord']
    data = {
        "grant_type": 'authorization_code',
        "code": code,
        "scope": "identify guilds",
        "client_id": discord_config['client_id'],
        "client_secret": discord_config['client_secret'],
        "redirect_uri": base_url + discord_config['redirect_uri'],
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "VoxelFox.co.uk Login Processor (kae@voxelfox.co.uk)",
    }

    # Perform our web requests
    async with aiohttp.ClientSession() as s:

        # Use code to get a token
        url = "https://discord.com/api/v9/oauth2/token"
        r = await s.post(url, data=data, headers=headers)
        token_json = await r.json()
        if 'error' in token_json:
            log.error(token_json)
            return None
        log.info("Got Discord token information %s" % token_json)

        # Use token to get user ID
        url = "https://discord.com/api/v9/users/@me"
        headers = {
            "Authorization": f"Bearer {token_json['access_token']}",
            "User-Agent": "VoxelFox.co.uk Login Processor (kae@voxelfox.co.uk)",
        }
        r = await s.get(url, headers=headers)
        user_json = await r.json()
        if 'error' in user_json:
            log.error(user_json)
            return None
        log.info("Got Discord user information %s" % user_json)

    # Store the data in database
    storage = await aiohttp_session.get_session(request)
    async with vbu.Database() as db:
        if storage.get('id') is not None:
            user_rows = await db.call(
                """
                UPDATE
                    login_users
                SET
                    discord_user_id = $2,
                    discord_refresh_token = $3
                WHERE
                    id = $1
                RETURNING
                    id
                """,
                storage['id'],
                user_json['id'],
                token_json['refresh_token'],
            )
        else:
            user_rows = await db.call(
                """
                INSERT INTO
                    login_users
                    (
                        discord_user_id,
                        discord_refresh_token
                    )
                VALUES
                    (
                        $1,
                        $2
                    )
                ON CONFLICT
                    (discord_user_id)
                DO UPDATE
                SET
                    discord_refresh_token = excluded.discord_refresh_token
                RETURNING
                    id
                """,
                user_json['id'],
                token_json['refresh_token'],
            )
        if not user_rows:
            user_rows = await db.call(
                """
                SELECT
                    id
                FROM
                    login_users
                WHERE
                    discord_user_id = $1
                """,
                user_json['id'],
            )

    # Store the data in session
    storage['id'] = str(user_rows[0]['id'])
    storage['discord'] = {
        "id": user_json['id'],
        "refresh_token": token_json['refresh_token'],
    }
    return None


@routes.get('/logout')
async def logout(request: Request):
    """
    Destroy the user's login session.
    """

    session = await aiohttp_session.get_session(request)
    session.invalidate()
    return HTTPFound(location='/')


@routes.get('/login')
@template('login.htm.j2')
async def login(request: Request):
    """
    Direct the user to the bot's Oauth login page.
    """

    # See if we're already logged in
    session = await aiohttp_session.get_session(request)
    # if session.get("id") is not None:
    #     login_keys = [
    #         "discord",
    #     ]
    #     if any(session.get(i) is None for i in login_keys):
    #     return HTTPFound(location=session.pop('redirect_on_login', '/'))
    base_url = request.app['config']['website_base_url']

    # Build Discord auth URL
    discord_config = request.app['config']['oauth']['discord']
    discord_url = (
        "https://discord.com/api/v9/oauth2/authorize?"
        + urlencode({
            "response_type": "code",
            "client_id": discord_config['client_id'],
            "redirect_uri": base_url + discord_config['redirect_uri'],
            "scope": "identify guilds",
        })
    )

    # Return auth URLs
    return {
        "session": session,
        "discord": discord_url,
    }


@routes.get('/login/done')
async def login_done(request: Request):
    """
    We are done linking the accounts.
    """

    session = await aiohttp_session.get_session(request)
    if session.get("id") is None:
        return HTTPFound(location='/login')
    return HTTPFound(location=session.pop('redirect_on_login', '/'))
