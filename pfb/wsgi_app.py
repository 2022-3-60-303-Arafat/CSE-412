"""WSGI version of the site, for hosting services such as PythonAnywhere.

It serves the files in public/ and sends every /api/ request through the same
dispatch_api() the local server uses, so both behave the same.
"""

import logging
from email.message import Message
from http import HTTPStatus

from .web import SECURITY_HEADERS, Response, dispatch_api, response_headers

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}
log = logging.getLogger("pfb")


def environ_headers(environ):
    """Rebuild the request headers from the WSGI environ (look-ups are case-insensitive)."""
    headers = Message()
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            headers[key[5:].replace("_", "-")] = value
    if environ.get("CONTENT_TYPE"):
        headers["Content-Type"] = environ["CONTENT_TYPE"]
    if environ.get("CONTENT_LENGTH"):
        headers["Content-Length"] = environ["CONTENT_LENGTH"]
    return headers


def static_file(public_dir, path):
    """Return a file from public/, or None. Paths outside public/ are never served."""
    if path == "/":
        path = "/index.html"
    root = public_dir.resolve()
    target = (root / path.lstrip("/")).resolve()
    if root not in target.parents or not target.is_file() or target.suffix not in STATIC_TYPES:
        return None
    return Response(200, body=target.read_bytes(), content_type=STATIC_TYPES[target.suffix])


def make_wsgi_app(router, config):
    def application(environ, start_response):
        method = environ["REQUEST_METHOD"]
        path = environ.get("PATH_INFO") or "/"
        query = environ.get("QUERY_STRING")
        if path.startswith("/api/"):
            response = dispatch_api(
                router, config, method, path + (f"?{query}" if query else ""), environ_headers(environ),
                environ.get("REMOTE_ADDR", ""), environ["wsgi.input"].read, log.error,
            )
            headers = response_headers(response)
        else:
            if method in ("GET", "HEAD"):
                response = static_file(config.public_dir, path)
                response = response or Response(404, body=b"Not found", content_type="text/plain; charset=utf-8")
            else:
                response = Response(405, body=b"Method not allowed", content_type="text/plain; charset=utf-8")
            headers = [("Content-Type", response.content_type), ("Content-Length", str(len(response.body)))]
        headers += list(SECURITY_HEADERS.items())
        if config.secure_cookies:
            # Hosted over HTTPS: tell browsers to always use HTTPS for this site.
            headers.append(("Strict-Transport-Security", "max-age=31536000"))
        start_response(f"{response.status} {HTTPStatus(response.status).phrase}", headers)
        return [b"" if method == "HEAD" else response.body]

    return application
