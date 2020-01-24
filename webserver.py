import os

from aiohttp.web import Application, run_app
from aiohttp_jinja2 import setup as jinja_setup
from jinja2 import FileSystemLoader

from views.simple import routes as simple_routes


# Add routes and setups
app = Application()
app['static_root_url'] = '/static'
jinja_setup(app, loader=FileSystemLoader(os.getcwd() + '/static/templates'))
app.router.add_static('/static', os.getcwd() + '/static', append_version=True)
app.router.add_routes(simple_routes)

# Run app
run_app(app)
