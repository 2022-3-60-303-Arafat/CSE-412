"""Entry point for WSGI hosting (PythonAnywhere and similar).

The host's WSGI configuration file imports `application` from here. The site is
served over HTTPS there, so session cookies are marked Secure unless
PFB_SECURE_COOKIES is set to 0.
"""

import os

from pfb.api import router
from pfb.wsgi_app import make_wsgi_app
from server import Config, prepare

config = Config(secure_cookies=os.environ.get("PFB_SECURE_COOKIES", "1") == "1")
prepare(config)
application = make_wsgi_app(router, config)
