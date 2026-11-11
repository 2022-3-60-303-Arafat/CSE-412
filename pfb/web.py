"""A small routing layer on top of http.server."""

import json
import re
import sqlite3
from http.cookies import CookieError, SimpleCookie
from http.server import SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from . import db
from .security import token_digest

MAX_JSON_BYTES = 64 * 1024
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
SESSION_COOKIE = "pfb_session"
# Browsers only send this header from our own pages; it blocks cross-site form posts (CSRF).
CSRF_HEADER = "X-PFB-Request"

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data: https://images.unsplash.com; "
        "connect-src 'self'"
    ),
}


class ApiError(Exception):
    def __init__(self, status, message, fields=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.fields = fields or {}


class Response:
    def __init__(self, status=200, payload=None, body=None, content_type="application/json; charset=utf-8", headers=None):
        self.status = status
        self.body = body if body is not None else json.dumps(payload if payload is not None else {}).encode("utf-8")
        self.content_type = content_type
        self.headers = headers or []


class Request:
    def __init__(self, method, raw_path, headers, client_ip, connection, config):
        parsed = urlparse(raw_path)
        self.method = method
        self.path = parsed.path
        self.query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        self.headers = headers
        self.client_ip = client_ip
        self.connection = connection
        self.config = config
        self.params = {}
        self.body = b""
        self.response_headers = []
        self._user = None
        self._user_loaded = False

    def json(self):
        if self.headers.get_content_type() != "application/json":
            raise ApiError(415, "Send the request as JSON.")
        try:
            payload = json.loads(self.body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ApiError(400, "The request is not valid JSON.") from None
        if not isinstance(payload, dict):
            raise ApiError(400, "The request must be a JSON object.")
        return payload

    def cookie(self, name):
        try:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        morsel = cookie.get(name)
        return morsel.value if morsel else None

    @property
    def user(self):
        if not self._user_loaded:
            self._user_loaded = True
            token = self.cookie(SESSION_COOKIE)
            if token:
                self._user = self.connection.execute(
                    """SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
                       WHERE s.token_hash = ? AND s.expires_at > ? AND u.account_status = 'active'""",
                    (token_digest(token), db.utc_now()),
                ).fetchone()
        return self._user

    def require(self, *roles):
        """Return the signed-in user, or stop with 401/403 if the role is not allowed."""
        if self.user is None:
            raise ApiError(401, "Please log in to continue.")
        if roles and self.user["role"] not in roles:
            raise ApiError(403, "Your account role cannot use this feature.")
        return self.user

    def set_cookie(self, value, max_age):
        secure = "; Secure" if self.config.secure_cookies else ""
        self.response_headers.append(
            ("Set-Cookie", f"{SESSION_COOKIE}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{secure}")
        )


class Router:
    def __init__(self):
        self.routes = []

    def route(self, method, pattern):
        regex = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[0-9]+)", pattern) + "$")

        def decorator(function):
            self.routes.append((method, regex, function))
            return function

        return decorator

    def resolve(self, method, path):
        allowed = False
        for route_method, regex, function in self.routes:
            match = regex.match(path)
            if match:
                if route_method == method:
                    return function, {key: int(value) for key, value in match.groupdict().items()}
                allowed = True
        if allowed:
            raise ApiError(405, "This method is not supported here.")
        raise ApiError(404, "This API endpoint does not exist.")


def accepts_upload(function):
    """Mark a route that receives a raw file body instead of JSON."""
    function.accepts_upload = True
    return function


def make_handler(router, config):
    class PfbHandler(SimpleHTTPRequestHandler):
        # Windows can map .js to text/plain in the registry, which breaks ES modules.
        extensions_map = {
            **SimpleHTTPRequestHandler.extensions_map,
            ".js": "text/javascript",
            ".css": "text/css",
            ".svg": "image/svg+xml",
            ".html": "text/html",
        }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(config.public_dir), **kwargs)

        def log_message(self, format, *args):
            if not config.quiet:
                super().log_message(format, *args)

        def end_headers(self):
            for name, value in SECURITY_HEADERS.items():
                self.send_header(name, value)
            super().end_headers()

        def list_directory(self, path):
            self.send_error(404, "Not found")
            return None

        def do_GET(self):
            if self.path.startswith("/api/"):
                self.handle_api("GET")
            else:
                super().do_GET()

        def do_POST(self):
            self.handle_api("POST")

        def do_PUT(self):
            self.handle_api("PUT")

        def do_DELETE(self):
            self.handle_api("DELETE")

        def handle_api(self, method):
            if not self.path.startswith("/api/"):
                self.send_api_response(Response(404, {"error": "Not found."}))
                return
            response = dispatch_api(
                router, config, method, self.path, self.headers, self.client_address[0],
                lambda size: self.rfile.read(size), self.log_error,
            )
            # A body that was too large was not read; close so its bytes are not parsed as a new request.
            if response.status == 413:
                self.close_connection = True
            self.send_api_response(response)

        def send_api_response(self, response):
            self.send_response(response.status)
            for name, value in response_headers(response):
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(response.body)

    return PfbHandler


def read_limited_body(headers, read, limit):
    length = headers.get("Content-Length")
    if not length:
        return b""
    try:
        size = int(length)
    except ValueError:
        raise ApiError(400, "Invalid request size.") from None
    if size < 0 or size > limit:
        raise ApiError(413, f"The request is too large (limit {limit // (1024 * 1024) or 1} MB).")
    return read(size)


def dispatch_api(router, config, method, raw_path, headers, client_ip, read, log_error):
    """Run one API request and return its Response. Shared by the local server and WSGI hosting."""
    connection = db.connect(config.database)
    request = Request(method, raw_path, headers, client_ip, connection, config)
    try:
        function, params = router.resolve(method, request.path)
        request.params = params
        if method != "GET" and headers.get(CSRF_HEADER) != "1":
            raise ApiError(403, "Request blocked: missing security header.")
        limit = MAX_UPLOAD_BYTES if getattr(function, "accepts_upload", False) else MAX_JSON_BYTES
        request.body = read_limited_body(headers, read, limit)
        result = function(request)
        connection.commit()
        response = result if isinstance(result, Response) else Response(200, result)
    except ApiError as error:
        connection.rollback()
        payload = {"error": error.message}
        if error.fields:
            payload["fields"] = error.fields
        response = Response(error.status, payload)
    except sqlite3.Error as error:
        connection.rollback()
        log_error("Database error: %s", error)
        response = Response(500, {"error": "The database could not complete this request."})
    except Exception as error:  # noqa: BLE001 - last line of defence for one request
        connection.rollback()
        log_error("Unexpected error: %r", error)
        response = Response(500, {"error": "Something went wrong on the server."})
    finally:
        connection.close()
    response.headers = request.response_headers + response.headers
    return response


def response_headers(response):
    """Headers for an API response (the local server adds SECURITY_HEADERS itself)."""
    return [
        ("Content-Type", response.content_type),
        ("Content-Length", str(len(response.body))),
        ("Cache-Control", "no-store"),
        *response.headers,
    ]
