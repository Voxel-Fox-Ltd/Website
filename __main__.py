import asyncio
import os
import toml
import importlib
import argparse
import sys
import logging


class CascadingLogger(logging.getLoggerClass()):
    """
    A logger class that changes all of the handlers loglevels as well.
    Stdout will change to the loglevel set, and stderr will change to the max of what's
    been specified and WARNING.
    """

    def setLevel(self, level):
        for i in self.handlers:
            if isinstance(i, logging.StreamHandler):
                if i.stream.name == "<stdout>":
                    i.setLevel(level)
                elif i.stream.name == "<stderr>":
                    i.setLevel(max([level, logging.WARNING]))
        super().setLevel(level)


logging.setLoggerClass(CascadingLogger)
logger = logging.getLogger("website")


def run_website(args: argparse.Namespace) -> None:
    """
    Starts the website, connects the database, logs in the specified bots, runs the async loop forever.

    Parameters
    -----------
    args: :class:`argparse.Namespace`
        The arguments namespace that wants to be run.
    """

    # Load our imports here so we don't need to require them all the time
    from aiohttp.web import Application, AppRunner, TCPSite
    from aiohttp_jinja2 import setup as jinja_setup
    from aiohttp_session import setup as session_setup, SimpleCookieStorage
    from aiohttp_session.cookie_storage import EncryptedCookieStorage as ECS
    from jinja2 import FileSystemLoader
    import re
    import html
    from datetime import datetime as dt
    import markdown

    # Read config
    with open(args.config_file) as a:
        config = toml.load(a)

    # Create website object - don't start based on argv
    app = Application(loop=asyncio.get_event_loop(), debug=args.debug)
    app["static_root_url"] = "/static"
    for route in config["routes"]:
        module = importlib.import_module(f"website.{route}", "temp")
        app.router.add_routes(module.routes)
    app.router.add_static("/static", os.getcwd() + "/website/static", append_version=True)

    # Add middlewares
    if args.debug:
        session_setup(app, SimpleCookieStorage(max_age=int(1e6)))
    else:
        session_setup(app, ECS(os.urandom(32), max_age=int(1e6)))
    jinja_env = jinja_setup(app, loader=FileSystemLoader(os.getcwd() + "/website/templates"))

    # Add our jinja env filters
    def regex_replace(string, find, replace):
        return re.sub(find, replace, string, re.IGNORECASE | re.MULTILINE)

    def escape_text(string):
        return html.escape(string)

    def timestamp(string):
        return dt.fromtimestamp(float(string))

    def int_to_hex(string):
        return format(hex(int(string))[2:], "0>6")

    def to_markdown(string):
        return markdown.markdown(string, extensions=["extra"])

    def display_mentions(string, users):
        def get_display_name(group):
            user = users.get(group.group("userid"))
            if not user:
                return "unknown-user"
            return user.get("display_name") or user.get("username")
        return re.sub(
            "(?:<|(?:&lt;))@!?(?P<userid>\\d{16,23})(?:>|(?:&gt;))",
            lambda g: f'<span class="chatlog__mention">@{get_display_name(g)}</span>',
            string,
            re.IGNORECASE | re.MULTILINE,
        )

    def display_emojis(string):
        def get_html(group):
            return (
                f'<img class="discord_emoji" src="https://cdn.discordapp.com/emojis/{group.group("id")}'
                f'.{"gif" if group.group("animated") else "png"}" alt="Discord custom emoji: '
                f'{group.group("name")}" style="height: 1em; width: auto;">'
            )
        return re.sub(
            r"(?P<emoji>(?:<|&lt;)(?P<animated>a)?:(?P<name>\w+):(?P<id>\d+)(?:>|&gt;))",
            get_html,
            string,
            re.IGNORECASE | re.MULTILINE,
        )

    jinja_env.filters["regex_replace"] = regex_replace
    jinja_env.filters["escape_text"] = escape_text
    jinja_env.filters["timestamp"] = timestamp
    jinja_env.filters["int_to_hex"] = int_to_hex
    jinja_env.filters["markdown"] = to_markdown
    jinja_env.filters["display_mentions"] = display_mentions
    jinja_env.filters["display_emojis"] = display_emojis

    # Add our connections and their loggers
    app["database"] = DatabaseWrapper
    app["redis"] = RedisConnection
    app["logger"] = logger.getChild("route")
    app["stats"] = StatsdConnection

    # Add our config
    app['config'] = config

    loop = app.loop

    # Connect the database pool
    if app['config'].get('database', {}).get('enabled', False):
        db_connect_task = start_database_pool(app['config'])
        loop.run_until_complete(db_connect_task)

    # Connect the redis pool
    if app['config'].get('redis', {}).get('enabled', False):
        re_connect = start_redis_pool(app['config'])
        loop.run_until_complete(re_connect)

    # Add our bots
    app['bots'] = {}
    for index, (bot_name, bot_config_location) in enumerate(config.get('discord_bot_configs', dict()).items()):
        bot = Bot(f"./config/{bot_config_location}")
        app['bots'][bot_name] = bot
        if index == 0:
            set_default_log_levels(args)
        try:
            loop.run_until_complete(bot.login())
            bot.load_all_extensions()
        except Exception:
            logger.error(f"Failed to start bot {bot_name}", exc_info=True)
            exit(1)

    # Start the HTTP server
    logger.info("Creating webserver...")
    application = AppRunner(app)
    loop.run_until_complete(application.setup())
    webserver = TCPSite(application, host=args.host, port=args.port)

    # Start the webserver
    loop.run_until_complete(webserver.start())
    logger.info(f"Server started - http://{args.host}:{args.port}/")

    # This is the forever loop
    try:
        logger.info("Running webserver")
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    # We're now done running the bot, time to clean up and close
    loop.run_until_complete(application.cleanup())
    if config.get('database', {}).get('enabled', False):
        logger.info("Closing database pool")
        try:
            if DatabaseWrapper.pool:
                loop.run_until_complete(asyncio.wait_for(DatabaseWrapper.pool.close(), timeout=30.0))
        except asyncio.TimeoutError:
            logger.error("Couldn't gracefully close the database connection pool within 30 seconds")
    if config.get('redis', {}).get('enabled', False):
        logger.info("Closing redis pool")
        RedisConnection.pool.close()

    logger.info("Closing asyncio loop")
    loop.stop()
    loop.close()