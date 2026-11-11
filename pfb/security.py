"""Password hashing, session tokens and login throttling."""

import hashlib
import hmac
import secrets
import threading
import time

PBKDF2_ITERATIONS = 240_000
SESSION_DAYS = 7
LOGIN_WINDOW_SECONDS = 10 * 60
LOGIN_MAX_FAILURES = 5


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# Used to spend the same time on unknown emails as on real ones.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_hex(8))


def new_session_token():
    return secrets.token_urlsafe(32)


def token_digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoginThrottle:
    """Blocks an email + address pair for a while after repeated failed logins."""

    def __init__(self):
        self._failures = {}
        self._lock = threading.Lock()

    def _recent(self, key, now):
        return [t for t in self._failures.get(key, []) if now - t < LOGIN_WINDOW_SECONDS]

    def is_blocked(self, key):
        with self._lock:
            return len(self._recent(key, time.monotonic())) >= LOGIN_MAX_FAILURES

    def record_failure(self, key):
        with self._lock:
            now = time.monotonic()
            self._failures[key] = self._recent(key, now) + [now]

    def reset(self, key):
        with self._lock:
            self._failures.pop(key, None)
