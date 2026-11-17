"""My profile: name, phone, a short bio, occupation, a profile picture and the password.

The profile picture is public (it shows in the header and next to the owner's name on listings), so it is
saved under config.avatar_dir (inside public/) with a random name, like listing photos.
"""

import uuid

from .api import load_user, router, user_json
from .db import audit, utc_now
from .photos import PHOTO_EXTENSIONS, PHOTO_MIME_TYPES, TYPE_LABELS, looks_like
from .security import hash_password, token_digest, verify_password
from .validation import Checker, check_new_password, check_phone
from .web import AVATAR_URL_PREFIX, SESSION_COOKIE, ApiError, Response, accepts_upload

MAX_AVATAR_BYTES = 2 * 1024 * 1024


def profile_json(connection, user):
    data = user_json(user)
    data["bio"] = user["bio"] or ""
    data["occupation"] = user["occupation"] or ""
    counts = {}
    if user["role"] == "owner":
        counts["listings"] = connection.execute(
            "SELECT COUNT(*) FROM properties WHERE owner_id = ? AND listing_status != 'removed'", (user["id"],)).fetchone()[0]
    if user["role"] == "buyer_tenant":
        counts["savedHomes"] = connection.execute("SELECT COUNT(*) FROM favorites WHERE user_id = ?", (user["id"],)).fetchone()[0]
        counts["visits"] = connection.execute("SELECT COUNT(*) FROM site_visits WHERE tenant_id = ?", (user["id"],)).fetchone()[0]
    if user["role"] in ("buyer_tenant", "advocate"):
        column = "client_id" if user["role"] == "buyer_tenant" else "advocate_id"
        counts["consultations"] = connection.execute(
            f"SELECT COUNT(*) FROM consultations WHERE {column} = ?", (user["id"],)).fetchone()[0]
    data["counts"] = counts
    return data


def remove_avatar_file(config, avatar_path):
    if not avatar_path:
        return
    root = config.avatar_dir.resolve()
    target = (root / avatar_path).resolve()
    if root in target.parents:
        target.unlink(missing_ok=True)


@router.route("GET", "/api/profile")
def get_profile(request):
    user = request.require()
    return profile_json(request.connection, user)


@router.route("PUT", "/api/profile")
def update_profile(request):
    user = request.require()
    checker = Checker(request.json())
    checker.text("fullName", "Full name", min_length=2, max_length=80)
    check_phone(checker)
    checker.text("occupation", "Occupation", max_length=80, required=False)
    checker.text("bio", "About me", max_length=500, required=False)
    data = checker.done()
    connection = request.connection
    phone_changed = data["phone"] != user["phone"]
    connection.execute(
        "UPDATE users SET full_name = ?, phone = ?, occupation = ?, bio = ? WHERE id = ?",
        (data["fullName"], data["phone"], data.get("occupation") or None, data.get("bio") or None, user["id"]),
    )
    if phone_changed and user["phone_verified_at"]:
        # PB-35: a new number has to be confirmed again before the owner publishes another listing.
        connection.execute("UPDATE users SET phone_verified_at = NULL WHERE id = ?", (user["id"],))
    changed = [name for name, old, new in (("name", user["full_name"], data["fullName"]), ("phone", user["phone"], data["phone"]),
                                           ("occupation", user["occupation"] or "", data.get("occupation") or ""),
                                           ("bio", user["bio"] or "", data.get("bio") or "")) if old != new]
    if changed:
        audit(connection, user["id"], "profile_updated", "user", user["id"], None, None, "Changed: " + ", ".join(changed))
    return profile_json(connection, load_user(connection, user["id"]))


@router.route("POST", "/api/profile/avatar")
@accepts_upload
def upload_avatar(request):
    user = request.require()
    name = (request.query.get("name") or "").strip()
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    file_type = PHOTO_EXTENSIONS.get(extension)
    if file_type is None:
        raise ApiError(400, "Only JPG, PNG and WebP pictures are accepted.")
    if request.headers.get_content_type() not in PHOTO_MIME_TYPES[file_type]:
        raise ApiError(400, f"This file does not look like a {TYPE_LABELS[file_type]} picture.")
    body = request.body
    if not body:
        raise ApiError(400, "The file is empty.")
    if len(body) > MAX_AVATAR_BYTES:
        raise ApiError(413, "A profile picture can be at most 2 MB.")
    if not looks_like(file_type, body):
        raise ApiError(400, f"This file is not a real {TYPE_LABELS[file_type]} picture.")
    avatar_path = f"{uuid.uuid4().hex}.{file_type}"
    path = request.config.avatar_dir / avatar_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    try:
        request.connection.execute("UPDATE users SET avatar_path = ? WHERE id = ?", (avatar_path, user["id"]))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    remove_avatar_file(request.config, user["avatar_path"])   # the old picture is no longer needed
    return Response(201, profile_json(request.connection, load_user(request.connection, user["id"])))


@router.route("DELETE", "/api/profile/avatar")
def delete_avatar(request):
    user = request.require()
    request.connection.execute("UPDATE users SET avatar_path = NULL WHERE id = ?", (user["id"],))
    remove_avatar_file(request.config, user["avatar_path"])
    return profile_json(request.connection, load_user(request.connection, user["id"]))


@router.route("POST", "/api/profile/password")
def change_password(request):
    user = request.require()
    data = request.json()
    if not verify_password(str(data.get("currentPassword", "")), user["password_hash"]):
        raise ApiError(400, "Please fix the highlighted fields.", {"currentPassword": "This is not your current password."})
    checker = Checker({"newPassword": data.get("newPassword")})
    check_new_password(checker, "newPassword")
    checker.done()
    connection = request.connection
    connection.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(data["newPassword"]), user["id"]))
    # Signed in elsewhere (another phone or computer)? Those sessions end; this one stays.
    current = token_digest(request.cookie(SESSION_COOKIE) or "")
    ended = connection.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user["id"], current)).rowcount
    audit(connection, user["id"], "password_changed", "user", user["id"], None, None, f"{ended} other sessions ended")
    return {"status": "changed", "otherSessionsEnded": ended, "changedAt": utc_now()}
