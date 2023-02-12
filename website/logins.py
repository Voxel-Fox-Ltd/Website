import json
from urllib.parse import urlencode
import logging
from typing import Any
import time

import aiohttp
from aiohttp.web import HTTPFound, Request, RouteTableDef, StreamResponse
import aiohttp_session
from aiohttp_jinja2 import template
from discord.ext import vbu
import asyncpg


routes = RouteTableDef()
log = logging.getLogger("vbu.voxelfox.login")
dump = json.dumps


"""
User Session
============
{
    "id?": str,
    "redirect_on_login?": str,
    "discord?": {
        "id": str,
        "refresh_token": str,
        "access_token?": str,
    },
    "google?": {
        "id": str,
        "refresh_token": str,
    },
    "everlasting?": {
        "id": str,
    },
}
"""


async def store_information(
        db: vbu.Database,
        storage: dict[str, str | dict[str, str]],
        identity: str,
        user_id: str,
        refresh_token: str | None) -> None:
    """
    Store given token information in database and cache.
    """

    # Get current ID
    current_id: str | None = storage.get('id')  # pyright: ignore
    oauth_identities = [
        "discord",
        "google",
        "facebook",
    ]

    # See if a user exists already
    if current_id is not None and refresh_token is not None:

        # Try and add this identity to the given user
        try:
            user_rows = await db.call(
                """
                UPDATE
                    login_users
                SET
                    {0}_user_id = $2,
                    {0}_refresh_token = $3
                WHERE
                    id = $1
                RETURNING
                    *
                """.format(identity),
                current_id,
                user_id,
                refresh_token,
            )

        # That identity exists for another user - try and merge
        except asyncpg.UniqueViolationError:

            # Delete existing
            conflict_row = await db.call(
                """
                DELETE FROM login_users WHERE {0}_user_id = $1 RETURNING *
                """.format(identity),
                user_id,
            )

            # Update
            for oid in oauth_identities:
                if conflict_row[0][f"{oid}_user_id"]:
                    await store_information(
                        db,
                        storage,
                        oid,
                        conflict_row[0][f"{oid}_user_id"],
                        conflict_row[0][f"{oid}_refresh_token"],
                    )
            return

    # No current ID or no refresh token
    else:

        # If there's no refresh token, an account must exist
        user_rows = None
        if refresh_token is None:
            user_rows = await db.call(
                """
                SELECT * FROM login_users WHERE {0}_user_id = $1
                """.format(identity),
                user_id,
            )

        # Create new account if we got nothing
        if not user_rows:
            user_rows = await db.call(
                """
                INSERT INTO
                    login_users
                    (
                        {0}_user_id,
                        {0}_refresh_token
                    )
                VALUES
                    (
                        $1,
                        $2
                    )
                ON CONFLICT
                    ({0}_user_id)
                DO UPDATE
                SET
                    {0}_refresh_token = excluded.{0}_refresh_token
                RETURNING
                    *
                """.format(identity),
                user_id,
                refresh_token,
            )

    # Work out our cache
    storage['id'] = str(user_rows[0]['id'])
    for oid in oauth_identities:
        user_oid = user_rows[0][f"{oid}_user_id"]
        if user_oid is None:
            continue
        storage[oid] = {
            "id": user_rows[0][f"{oid}_user_id"],
            "refresh_token": user_rows[0][f"{oid}_refresh_token"],
        }


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
    Process Discord login.
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
        log.info("Got Discord token information %s" % dump(token_json))

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
        log.info("Got Discord user information %s" % dump(user_json))

    # Store the data in database
    storage = await aiohttp_session.get_session(request)
    async with vbu.Database() as db:
        await store_information(
            db,
            storage,
            'discord',
            user_json['id'],
            token_json['refresh_token'],
        )
    storage['discord']['access_token'] = (
        f"{token_json['expires_in'] + int(time.time() - 60)}:"
        f"{token_json['access_token']}"
    )


@routes.get('/login/google')
@always_return('/login')
async def google(request: Request):
    """
    Process Google login.
    """

    # Get the code
    code = request.query.get("code")
    if not code:
        return HTTPFound(location="/login")

    # Build the JSON response
    base_url = request.app['config']['website_base_url']
    google_config = request.app['config']['oauth']['google']
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": google_config['client_id'],
        "client_secret": google_config['client_secret'],
        "redirect_uri": base_url + google_config['redirect_uri'],
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "VoxelFox.co.uk Login Processor (kae@voxelfox.co.uk)",
    }

    # Perform our web requests
    async with aiohttp.ClientSession() as s:

        # Use code to get a token
        url = "https://oauth2.googleapis.com/token"
        r = await s.post(url, data=data, headers=headers)
        token_json = await r.json()
        if 'error' in token_json:
            log.error(token_json)
            return None
        log.info("Got Google token information %s" % dump(token_json))

        # Use token to get user ID
        url = "https://www.googleapis.com/oauth2/v1/userinfo"
        headers = {
            "Authorization": f"Bearer {token_json['access_token']}",
            "User-Agent": "VoxelFox.co.uk Login Processor (kae@voxelfox.co.uk)",
        }
        r = await s.get(url, headers=headers)
        user_json = await r.json()
        if 'error' in user_json:
            log.error(user_json)
            return None
        log.info("Got Google user information %s" % dump(user_json))

    # Store the data in database
    storage = await aiohttp_session.get_session(request)
    async with vbu.Database() as db:
        await store_information(
            db,
            storage,
            'google',
            user_json['id'],
            token_json.get('refresh_token'),
        )
    return None


@routes.get('/login/everlasting')
@always_return('/login')
async def everlasting(request: Request):
    """
    Process Everlasting login.
    """

    # Get the code
    code = request.query.get("access_token")
    if not code:
        return HTTPFound(location="/login")

    # Build the JSON response
    everlasting_config = request.app['config']['oauth']['everlasting']
    data = {
        "grant_type": "access_token",
        "access_token": code,
        "api_key": everlasting_config['api_key'],
    }
    headers = {
        "User-Agent": "VoxelFox.co.uk Login Processor (kae@voxelfox.co.uk)",
    }

    # Perform our web requests
    async with aiohttp.ClientSession() as s:

        # Use code to get a token
        url = "https://everlastingservers.companion.repl.co/auth/verify"
        r = await s.post(url, data=data, headers=headers)
        try:
            token_json = await r.json()
        except Exception:
            token_text = await r.text()
            log.error(token_text)
            return None
        if token_json.get("valid", False):
            log.error(token_json)
            return None
        log.info("Got Everlasting token information %s" % dump(token_json))

    # Store the data in database
    storage = await aiohttp_session.get_session(request)
    async with vbu.Database() as db:
        await store_information(
            db,
            storage,
            'everlasting',
            token_json['id'],
            None,
        )
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
    message = session.pop("login_message", None)
    base_url = request.app['config']['website_base_url']

    # Build Discord auth URL
    discord_config = request.app['config']['oauth']['discord']
    discord_url = (
        "https://discord.com/api/v9/oauth2/authorize?"
        + urlencode({
            "response_type": "code",
            "client_id": discord_config['client_id'],
            "redirect_uri": base_url + "/login/discord",
            "scope": "identify guilds",
        })
    )

    # Build Google auth URL
    google_config = request.app['config']['oauth']['google']
    google_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urlencode({
            "response_type": "code",
            "client_id": google_config['client_id'],
            "redirect_uri": base_url + "/login/google",
            "scope": "openid",
            "access_type": "offline",
        })
    )

    # Build Everlasting Auth URL
    # everlasting_config = request.app['config']['oauth']['everlasting']
    everlasting_url = (
        "https://everlastingservers.companion.repl.co/auth/login?"
        + urlencode({
            "redirect_uri": base_url + "/login/everlasting",
        })
    )

    # Return auth URLs
    return {
        "session": session,
        "message": message,

        "discord": discord_url,
        "google": google_url,
        "everlasting": everlasting_url,
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
