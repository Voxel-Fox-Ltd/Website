import asyncio
import os

from aiohttp.web import Application, AppRunner, TCPSite
from aiohttp_jinja2 import setup as jinja_setup
from jinja2 import FileSystemLoader

from views.simple import routes as simple_routes

# Add routes and setups
app = Application(loop=asyncio.get_event_loop())
app['static_root_url'] = '/static'
jinja_setup(app, loader=FileSystemLoader(os.getcwd() + '/static/templates'))
app.router.add_static('/static', os.getcwd() + '/static', append_version=True)
app.router.add_routes(simple_routes)

if __name__ == '__main__':
    """Starts the bot (and webserver if specified) and runs forever"""

    loop = app.loop

    # HTTP server
    application = AppRunner(app)
    loop.run_until_complete(application.setup())
    webserver = TCPSite(application, port=5002)

    # Start server
    loop.run_until_complete(webserver.start())

    # This is the forever loop
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    # Clean up our shit
    loop.run_until_complete(application.cleanup())
