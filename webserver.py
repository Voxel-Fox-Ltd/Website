import asyncio
import os
import argparse
import logging
import sys

import toml

from aiohttp.web import Application, AppRunner, TCPSite
from aiohttp_jinja2 import setup as jinja_setup
from jinja2 import FileSystemLoader

from views.frontend import routes as frontend_routes
from views.backend import routes as backend_routes
from utils.database import DatabaseConnection


# Set up loggers
logging.getLogger().setLevel(logging.INFO)
logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s: %(message)s', stream=sys.stdout)
logger = logging.getLogger(os.getcwd().split(os.sep)[-1].split()[-1].lower())
logger.setLevel(logging.INFO)

# Parse arguments
parser = argparse.ArgumentParser()
parser.add_argument("config_file", help="The configuration for the bot.")
parser.add_argument("--host", type=str, default='0.0.0.0', help="The host IP to run the webserver on.")
parser.add_argument("--port", type=int, default=8080, help="The port to run the webserver on.")
args = parser.parse_args()

# Read config
with open(args.config_file) as a:
    config = toml.load(a)

# Add routes and setups
app = Application(loop=asyncio.get_event_loop())
app['static_root_url'] = '/static'
jinja_setup(app, loader=FileSystemLoader(os.getcwd() + '/static/templates'))
app.router.add_static('/static', os.getcwd() + '/static', append_version=True)
app.router.add_routes(frontend_routes)
app.router.add_routes(backend_routes)

# Add our connections
app['database'] = DatabaseConnection
DatabaseConnection.logger = logger.getChild("db")

# Add our config
app['config'] = config
app['logger'] = logger


if __name__ == '__main__':
    """Starts the bot (and webserver if specified) and runs forever"""

    loop = app.loop

    # Connect the database pool
    logger.info("Creating database pool")
    try:
        db_connect_task = loop.create_task(DatabaseConnection.create_pool(config['database']))
        loop.run_until_complete(db_connect_task)
    except KeyError:
        raise Exception("KeyError creating database pool - is there a 'database' object in the config?")
    except ConnectionRefusedError:
        raise Exception("ConnectionRefusedError creating database pool - did you set the right information in the config, and is the database running?")
    except Exception:
        raise Exception("Error creating database pool")
    logger.info("Created database pool successfully")

    # HTTP server
    logger.info("Creating TCP app")
    application = AppRunner(app)
    loop.run_until_complete(application.setup())
    webserver = TCPSite(application, host=args.host, port=args.port)  # 5002
    logger.info("Created TCP app")

    # Start server
    loop.run_until_complete(webserver.start())

    # This is the forever loop
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    # Disconnect database
    logger.info("Closing database pool")
    loop.run_until_complete(DatabaseConnection.pool.close())

    # Clean up our shit
    loop.run_until_complete(application.cleanup())
