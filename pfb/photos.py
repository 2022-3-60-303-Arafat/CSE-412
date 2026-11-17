"""Listing photos: owners upload pictures of a house or flat, and buyers see them in a gallery.

Each photo is sent as the raw body of one request, like the legal papers, so no multipart
parser is needed. Photos are public: they are saved under config.photo_dir (inside public/)
as <property id>/<random name>.<jpg|png|webp>. The name the owner gave the file is never used.

Only the listing's owner or an admin can add, delete or change photos. A listing has at most
MAX_PHOTOS photos and one cover photo, which search cards show.
"""

import hashlib
import uuid

from .api import fetch_property, router
from .db import audit, utc_now
from .web import PHOTO_URL_PREFIX, ApiError, Response, accepts_upload

MAX_PHOTOS = 10
PHOTO_EXTENSIONS = {"jpg": "jpg", "jpeg": "jpg", "png": "png", "webp": "webp"}
# The Content-Type the browser sends must fit the extension.
PHOTO_MIME_TYPES = {
    "jpg": ("image/jpeg", "image/jpg", "image/pjpeg"),
    "png": ("image/png",),
    "webp": ("image/webp",),
}
TYPE_LABELS = {"jpg": "JPG", "png": "PNG", "webp": "WebP"}


def looks_like(file_type, body):
    """Check the first bytes of the file, so a renamed file of another kind is refused."""
    if file_type == "jpg":
        return body.startswith(b"\xff\xd8\xff")
    if file_type == "png":
        return body.startswith(b"\x89PNG\r\n\x1a\n")
    return len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP"


def image_json(row):
    return {
        "id": row["id"],
        "url": row["image_url"],
        "caption": row["caption"],
        "isCover": bool(row["is_cover"]),
        "uploaded": row["file_path"] is not None,
        "uploadedAt": row["uploaded_at"],
    }


def list_images(connection, property_id):
    """All photos of a listing, the cover first, then in upload order."""
    rows = connection.execute(
        "SELECT * FROM property_images WHERE property_id = ? ORDER BY is_cover DESC, id", (property_id,)
    ).fetchall()
    return [image_json(row) for row in rows]


def photo_listing(request):
    """Load a listing whose photos the signed-in user may change: their own listing, or any listing for an admin."""
    user = request.require("owner", "admin")
    row = fetch_property(request.connection, request.params["id"])
    if row is None or row["listing_status"] == "removed":
        raise ApiError(404, "This listing does not exist.")
    if user["role"] == "owner" and row["owner_id"] != user["id"]:
        raise ApiError(403, "You can only change the photos of your own listings.")
    return user, row


def load_image(connection, property_id, image_id):
    image = connection.execute(
        "SELECT * FROM property_images WHERE id = ? AND property_id = ?", (image_id, property_id)
    ).fetchone()
    if image is None:
        raise ApiError(404, "This photo does not exist.")
    return image


def photo_path(config, file_path):
    """The file on disk for a stored file_path, or None if it would point outside the photo folder."""
    root = config.photo_dir.resolve()
    target = (root / file_path).resolve()
    return target if root in target.parents else None


@router.route("POST", "/api/properties/{id}/images")
@accepts_upload
def upload_image(request):
    user, row = photo_listing(request)
    connection = request.connection

    name = (request.query.get("name") or "").strip()
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    file_type = PHOTO_EXTENSIONS.get(extension)
    if file_type is None:
        raise ApiError(400, "Only JPG, PNG and WebP photos are accepted.")
    if request.headers.get_content_type() not in PHOTO_MIME_TYPES[file_type]:
        raise ApiError(400, f"This file does not look like a {TYPE_LABELS[file_type]} photo.")
    body = request.body
    if not body:
        raise ApiError(400, "The file is empty.")
    if not looks_like(file_type, body):
        raise ApiError(400, f"This file is not a real {TYPE_LABELS[file_type]} photo.")

    count, has_cover = connection.execute(
        "SELECT COUNT(*), COALESCE(MAX(is_cover), 0) FROM property_images WHERE property_id = ?", (row["id"],)
    ).fetchone()
    if count >= MAX_PHOTOS:
        raise ApiError(409, f"A listing can have at most {MAX_PHOTOS} photos. Delete one before adding another.")

    file_path = f"{row['id']}/{uuid.uuid4().hex}.{file_type}"
    path = request.config.photo_dir / file_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    try:
        file_hash = hashlib.sha256(body).hexdigest()
        cursor = connection.execute(
            """INSERT INTO property_images (property_id, image_url, caption, is_cover, file_path, file_hash, uploaded_at)
               VALUES (?, ?, '', ?, ?, ?, ?)""",
            (row["id"], PHOTO_URL_PREFIX + file_path, 0 if has_cover else 1, file_path, file_hash, utc_now()),
        )
        from .sprint5 import check_duplicate_photo   # PB-39: the same photo on another owner's listing is flagged
        check_duplicate_photo(connection, row, file_hash)
        audit(connection, user["id"], "photo_added", "property", row["id"], None, f"photo #{cursor.lastrowid}")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    image = connection.execute("SELECT * FROM property_images WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return Response(201, {"image": image_json(image), "images": list_images(connection, row["id"])})


@router.route("DELETE", "/api/properties/{id}/images/{image_id}")
def delete_image(request):
    user, row = photo_listing(request)
    connection = request.connection
    image = load_image(connection, row["id"], request.params["image_id"])
    connection.execute("DELETE FROM property_images WHERE id = ?", (image["id"],))
    # If the cover was deleted, the oldest remaining photo becomes the cover.
    if image["is_cover"]:
        connection.execute(
            """UPDATE property_images SET is_cover = 1
               WHERE id = (SELECT id FROM property_images WHERE property_id = ? ORDER BY id LIMIT 1)""",
            (row["id"],),
        )
    audit(connection, user["id"], "photo_deleted", "property", row["id"], f"photo #{image['id']}", None)
    # Demo photos are links and have no file. The file goes last, once the database changes have worked.
    if image["file_path"]:
        path = photo_path(request.config, image["file_path"])
        if path is not None:
            path.unlink(missing_ok=True)
    return {"images": list_images(connection, row["id"])}


@router.route("POST", "/api/properties/{id}/images/{image_id}/cover")
def set_cover_image(request):
    user, row = photo_listing(request)
    connection = request.connection
    image = load_image(connection, row["id"], request.params["image_id"])
    if not image["is_cover"]:
        # Clear the old cover first: the database allows only one cover per listing.
        connection.execute("UPDATE property_images SET is_cover = 0 WHERE property_id = ? AND is_cover = 1", (row["id"],))
        connection.execute("UPDATE property_images SET is_cover = 1 WHERE id = ?", (image["id"],))
        audit(connection, user["id"], "photo_cover_changed", "property", row["id"], None, f"photo #{image['id']}")
    return {"images": list_images(connection, row["id"])}
