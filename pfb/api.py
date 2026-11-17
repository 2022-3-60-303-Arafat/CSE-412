"""JSON API for Sprint 1 (roles, rent support, search) and Sprint 2 (legal verification).

Sprint 3 (consultations, chat, payments, notifications) is in consult.py and Sprint 4 (rent agreements,
saved searches, reports) is in sprint4.py. Both use the same router.

Each handler checks the caller's role on the server, so hiding a menu item in
the browser is never the only protection (PB-02, PB-03).
"""

import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from . import db, reports
from .db import (
    CHECKLIST_ITEMS, DOCUMENT_TYPES, OPEN_REQUEST_STATUSES, PROPERTY_TYPES, REQUIRED_DOCUMENT_TYPES, USER_SELECT, audit, notify, notify_advocates,
    utc_now,
)
from .security import (
    DUMMY_PASSWORD_HASH,
    SESSION_DAYS,
    hash_password,
    new_session_token,
    token_digest,
    verify_password,
)
from .places import LANDMARKS_BY_ID, LATITUDE_RANGE, LONGITUDE_RANGE
from .validation import CITIES, Checker, check_email, check_new_password, check_phone, clean_listing
from .web import AVATAR_URL_PREFIX, SESSION_COOKIE, ApiError, Response, Router, accepts_upload

router = Router()

DOCUMENT_LABELS = {
    "land_deed": "Land deed",
    "mutation": "Mutation paper",
    "tax_receipt": "Tax receipt",
    "ownership_history": "Ownership history",
}
FILE_SIGNATURES = {
    "pdf": (b"%PDF-",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
}
FILE_CONTENT_TYPES = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg"}
AREA_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 .'/-]{2,60}$")

# A listing is in a high-demand area when its area name equals the marked area
# or starts with it ("Gulshan 2" is in "Gulshan") (PB-17).
HIGH_DEMAND_SQL = """EXISTS (SELECT 1 FROM high_demand_areas h
    WHERE lower(p.area_name) = lower(h.area_name) OR lower(p.area_name) LIKE lower(h.area_name) || ' %')"""

PROPERTY_SELECT = """
SELECT p.*, u.full_name AS owner_name, u.phone_verified_at AS owner_phone_verified_at, u.avatar_path AS owner_avatar_path,
       rd.monthly_rent, rd.security_deposit, rd.available_from, rd.min_lease_months,
       rd.utilities_included, rd.tenant_preference,
       CASE WHEN p.listing_type = 'rent' THEN rd.monthly_rent ELSE p.price END AS amount,
       (SELECT i.image_url FROM property_images i WHERE i.property_id = p.id
        ORDER BY i.is_cover DESC, i.id LIMIT 1) AS primary_image
FROM properties p
JOIN users u ON u.id = p.owner_id
LEFT JOIN rent_details rd ON rd.property_id = p.id
"""


# ---------------------------------------------------------------- serializers

def user_json(row):
    """Expects a row from USER_SELECT (or one that also has advocate_status)."""
    data = {
        "id": row["id"],
        "fullName": row["full_name"],
        "email": row["email"],
        "phone": row["phone"],
        "role": row["role"],
        "accountStatus": row["account_status"],
        "createdAt": row["created_at"],
        "phoneVerified": bool(row["phone_verified_at"]),
        "avatarUrl": AVATAR_URL_PREFIX + row["avatar_path"] if row["avatar_path"] else None,
    }
    if row["role"] == "advocate":
        data["advocateStatus"] = row["advocate_status"]
    return data


def is_staff(user):
    """Admins and verified advocates can see listings and requests that are hidden from the public."""
    return user is not None and (
        user["role"] == "admin" or (user["role"] == "advocate" and user["advocate_status"] == "verified")
    )


def property_json(row, viewer=None):
    is_owner = viewer is not None and viewer["id"] == row["owner_id"]
    status = row["verification_status"]
    # The public only needs to know whether a listing is verified; issue details stay private.
    if status == "issue_found" and not (is_owner or is_staff(viewer)):
        status = "unverified"
    data = {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "listingType": row["listing_type"],
        "propertyType": row["property_type"],
        "price": row["price"],
        "amount": row["amount"],
        "areaName": row["area_name"],
        "city": row["city"],
        "address": row["address"],
        "sizeSqft": row["size_sqft"],
        "bedrooms": row["bedrooms"],
        "bathrooms": row["bathrooms"],
        "furnished": bool(row["furnished"]),
        "listingStatus": row["listing_status"],
        "verificationStatus": status,
        "badgeLevel": row["badge_level"],
        "image": row["primary_image"],
        "owner": {"id": row["owner_id"], "name": row["owner_name"], "phoneVerified": bool(row["owner_phone_verified_at"]),
                  "avatarUrl": AVATAR_URL_PREFIX + row["owner_avatar_path"] if row["owner_avatar_path"] else None},
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "isOwner": is_owner,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "rent": None,
    }
    if "distance_km" in row.keys() and row["distance_km"] is not None:
        data["distanceKm"] = round(row["distance_km"], 1)
    if row["listing_type"] == "rent" and row["monthly_rent"] is not None:
        data["rent"] = {
            "monthlyRent": row["monthly_rent"],
            "securityDeposit": row["security_deposit"],
            "moveInCost": row["monthly_rent"] + row["security_deposit"],
            "availableFrom": row["available_from"],
            "minLeaseMonths": row["min_lease_months"],
            "utilitiesIncluded": bool(row["utilities_included"]),
            "tenantPreference": row["tenant_preference"],
        }
    return data


def document_json(row):
    return {
        "id": row["id"],
        "documentType": row["document_type"],
        "label": DOCUMENT_LABELS[row["document_type"]],
        "fileName": row["file_name"],
        "fileType": row["file_type"],
        "fileSizeKb": row["file_size_kb"],
        "reviewStatus": row["review_status"],
        "isCurrent": bool(row["is_current"]),
        "uploadedAt": row["uploaded_at"],
    }


def audit_json(row):
    return {
        "id": row["id"],
        "actor": {"id": row["actor_id"], "name": row["actor_name"], "role": row["actor_role"]} if row["actor_id"] else None,
        "actionType": row["action_type"],
        "targetType": row["target_type"],
        "targetId": row["target_id"],
        "oldValue": row["old_value"],
        "newValue": row["new_value"],
        "details": row["details"],
        "createdAt": row["created_at"],
    }


AUDIT_SELECT = """SELECT a.*, u.full_name AS actor_name, u.role AS actor_role
                  FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id"""


# ---------------------------------------------------------------- helpers

def fetch_property(connection, property_id):
    return connection.execute(PROPERTY_SELECT + " WHERE p.id = ?", (property_id,)).fetchone()


def owned_property(request, user):
    """Load a listing the signed-in owner is allowed to change (PB-03)."""
    row = fetch_property(request.connection, request.params["id"])
    if row is None or row["listing_status"] == "removed":
        raise ApiError(404, "This listing does not exist.")
    if row["owner_id"] != user["id"]:
        raise ApiError(403, "You can only change your own listings.")
    return row


def start_session(request, user_id):
    token = new_session_token()
    now = datetime.now(timezone.utc)
    request.connection.execute(
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (
            token_digest(token),
            user_id,
            now.isoformat(timespec="seconds"),
            (now + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds"),
        ),
    )
    request.set_cookie(token, SESSION_DAYS * 24 * 3600)


def load_user(connection, user_id):
    return connection.execute(USER_SELECT + " WHERE u.id = ?", (user_id,)).fetchone()


def int_param(request, name, label, minimum, maximum):
    checker = Checker(request.query)
    value = checker.integer(name, label, minimum, maximum, required=False)
    checker.done("Please check the search filters.")
    return value


# ---------------------------------------------------------------- meta

@router.route("GET", "/api/health")
def health(request):
    return {"status": "ok"}


@router.route("GET", "/api/meta")
def meta(request):
    areas = [
        row[0]
        for row in request.connection.execute(
            "SELECT DISTINCT area_name FROM properties WHERE listing_status = 'active' ORDER BY area_name"
        )
    ]
    return {
        "cities": CITIES,
        "propertyTypes": PROPERTY_TYPES,
        "areas": areas,
        "documentTypes": [{"value": key, "label": DOCUMENT_LABELS[key], "required": key in REQUIRED_DOCUMENT_TYPES} for key in DOCUMENT_TYPES],
    }


# ---------------------------------------------------------------- accounts (PB-02)

@router.route("POST", "/api/auth/signup")
def signup(request):
    checker = Checker(request.json())
    checker.text("fullName", "Full name", min_length=2, max_length=80)
    check_email(checker)
    check_phone(checker)
    check_new_password(checker)
    # Advocates apply through /api/auth/advocate-signup and admins are created by the system.
    checker.choice("role", "Account type", ("buyer_tenant", "owner"))
    data = checker.done()

    connection = request.connection
    if connection.execute("SELECT 1 FROM users WHERE email = ?", (data["email"],)).fetchone():
        raise ApiError(409, "Please fix the highlighted fields.", {"email": "An account with this email already exists."})
    cursor = connection.execute(
        """INSERT INTO users (full_name, email, phone, password_hash, role, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (data["fullName"], data["email"], data["phone"], hash_password(data["password"]), data["role"], utc_now()),
    )
    audit(connection, cursor.lastrowid, "account_created", "user", cursor.lastrowid, None, data["role"])
    start_session(request, cursor.lastrowid)
    return Response(201, {"user": user_json(load_user(connection, cursor.lastrowid))})


def check_advocate_fields(checker):
    checker.text("fullName", "Full name", min_length=2, max_length=80)
    check_email(checker)
    check_phone(checker)
    check_new_password(checker)
    checker.text("barCouncilId", "Bar Council ID", min_length=3, max_length=40)
    checker.text("specialization", "Specialization", min_length=2, max_length=80)
    return checker.done()


DEFAULT_CONSULTATION_FEE = 500  # taka, for one paid consultation (PB-22)


def create_advocate(connection, data, verification_status, added_by=None):
    """Create an advocate account with its profile. Returns the new user id."""
    conflicts = {}
    if connection.execute("SELECT 1 FROM users WHERE email = ?", (data["email"],)).fetchone():
        conflicts["email"] = "An account with this email already exists."
    if connection.execute("SELECT 1 FROM advocate_profiles WHERE bar_council_id = ?", (data["barCouncilId"],)).fetchone():
        conflicts["barCouncilId"] = "This Bar Council ID is already registered."
    if conflicts:
        raise ApiError(409, "Please fix the highlighted fields.", conflicts)
    now = utc_now()
    cursor = connection.execute(
        """INSERT INTO users (full_name, email, phone, password_hash, role, created_at)
           VALUES (?, ?, ?, ?, 'advocate', ?)""",
        (data["fullName"], data["email"], data["phone"], hash_password(data["password"]), now),
    )
    connection.execute(
        """INSERT INTO advocate_profiles (user_id, bar_council_id, specialization, added_by, added_at, verification_status,
                                          consultation_fee)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (cursor.lastrowid, data["barCouncilId"], data["specialization"], added_by, now, verification_status,
         DEFAULT_CONSULTATION_FEE),
    )
    return cursor.lastrowid


@router.route("POST", "/api/auth/advocate-signup")
def advocate_signup(request):
    """An advocate applies for an account. It stays unverified until the admin has met them in person."""
    data = check_advocate_fields(Checker(request.json()))
    connection = request.connection
    user_id = create_advocate(connection, data, "pending")
    audit(connection, user_id, "advocate_applied", "user", user_id, None, "pending", data["fullName"])
    start_session(request, user_id)
    return Response(201, {"user": user_json(load_user(connection, user_id))})


@router.route("POST", "/api/auth/login")
def login(request):
    data = request.json()
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password")
    if not email or not isinstance(password, str) or not password:
        raise ApiError(400, "Enter your email and password.")

    throttle = request.config.login_throttle
    key = f"{request.client_ip}|{email}"
    if throttle.is_blocked(key):
        raise ApiError(429, "Too many failed attempts. Please wait 10 minutes and try again.")

    user = request.connection.execute(
        USER_SELECT + " WHERE u.email = ? AND u.account_status != 'removed'", (email,)
    ).fetchone()
    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)
        throttle.record_failure(key)
        raise ApiError(401, "Email or password is incorrect.")
    if not verify_password(password, user["password_hash"]):
        throttle.record_failure(key)
        raise ApiError(401, "Email or password is incorrect.")
    if user["account_status"] == "blocked":
        raise ApiError(403, "This account has been blocked. Please contact the admin.")

    throttle.reset(key)
    request.connection.execute("DELETE FROM sessions WHERE user_id = ? AND expires_at <= ?", (user["id"], utc_now()))
    start_session(request, user["id"])
    return {"user": user_json(user)}


@router.route("POST", "/api/auth/logout")
def logout(request):
    token = request.cookie(SESSION_COOKIE)
    if token:
        request.connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest(token),))
    request.set_cookie("", 0)
    return {"status": "logged_out"}


@router.route("GET", "/api/auth/me")
def me(request):
    return {"user": user_json(request.user) if request.user else None}


# ---------------------------------------------------------------- search (PB-07, PB-15)

# ---------------------------------------------------------------- browsing history

SEARCH_FILTER_KEYS = ("purpose", "area", "city", "type", "minPrice", "maxPrice", "bedrooms", "furnished", "verified",
                      "near", "radius")
SEARCH_PAGE_SIZE = 12
VIEW_SOURCES = ("search", "favorites", "history", "direct")
HISTORY_ROLES = ("buyer_tenant", "owner")
# Opening the same listing again (or repeating a search) within this time is not saved twice.
REPEAT_WINDOW_MINUTES = 30


def time_ago(**delta):
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat(timespec="seconds")


def record_view(request, row):
    """Save one listing view. Owners, advocates and admins checking listings are not counted."""
    viewer = request.user
    if viewer is not None and (viewer["role"] not in HISTORY_ROLES or viewer["id"] == row["owner_id"]):
        return
    source = request.query.get("from")
    source = source if source in VIEW_SOURCES else "direct"
    if viewer is not None and request.connection.execute(
        "SELECT 1 FROM property_views WHERE user_id = ? AND property_id = ? AND viewed_at > ?",
        (viewer["id"], row["id"], time_ago(minutes=REPEAT_WINDOW_MINUTES)),
    ).fetchone():
        return
    request.connection.execute(
        "INSERT INTO property_views (property_id, user_id, source, viewed_at) VALUES (?, ?, ?, ?)",
        (row["id"], viewer["id"] if viewer else None, source, utc_now()),
    )


def record_search(request, filters, result_count):
    """Save a signed-in user's search. Opening the plain list of all homes is not a search."""
    user = request.user
    if user is None or user["role"] not in HISTORY_ROLES or not filters:
        return
    encoded = json.dumps(filters, sort_keys=True)
    latest = request.connection.execute(
        "SELECT id, filters FROM search_history WHERE user_id = ? AND searched_at > ? ORDER BY id DESC LIMIT 1",
        (user["id"], time_ago(minutes=REPEAT_WINDOW_MINUTES)),
    ).fetchone()
    if latest and latest["filters"] == encoded:
        request.connection.execute(
            "UPDATE search_history SET result_count = ?, searched_at = ? WHERE id = ?", (result_count, utc_now(), latest["id"])
        )
        return
    request.connection.execute(
        "INSERT INTO search_history (user_id, filters, result_count, searched_at) VALUES (?, ?, ?, ?)",
        (user["id"], encoded, result_count, utc_now()),
    )


def view_counts(connection, property_id):
    row = connection.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(viewed_at > ?), 0) AS last_week FROM property_views WHERE property_id = ?",
        (time_ago(days=7), property_id),
    ).fetchone()
    return {"total": row["total"], "lastWeek": row["last_week"]}


def search_json(row):
    return {"id": row["id"], "filters": json.loads(row["filters"]), "resultCount": row["result_count"], "searchedAt": row["searched_at"]}


@router.route("GET", "/api/history")
def my_history(request):
    user = request.require(*HISTORY_ROLES)
    connection = request.connection
    viewed = connection.execute(
        """SELECT property_id, MAX(viewed_at) AS last_viewed, COUNT(*) AS times FROM property_views
           WHERE user_id = ? GROUP BY property_id ORDER BY last_viewed DESC LIMIT 30""",
        (user["id"],),
    ).fetchall()
    views = []
    for item in viewed:
        row = fetch_property(connection, item["property_id"])
        if row is None or row["listing_status"] != "active":
            continue
        data = property_json(row, user)
        data.update({"lastViewedAt": item["last_viewed"], "timesViewed": item["times"]})
        views.append(data)
    searches = connection.execute(
        "SELECT * FROM search_history WHERE user_id = ? ORDER BY searched_at DESC, id DESC LIMIT 20", (user["id"],)
    ).fetchall()
    return {"views": views, "searches": [search_json(row) for row in searches]}


@router.route("DELETE", "/api/history")
def clear_history(request):
    user = request.require(*HISTORY_ROLES)
    # Views stay in the listing totals but are no longer linked to this person.
    views = request.connection.execute("UPDATE property_views SET user_id = NULL WHERE user_id = ?", (user["id"],)).rowcount
    searches = request.connection.execute("DELETE FROM search_history WHERE user_id = ?", (user["id"],)).rowcount
    return {"viewsCleared": views, "searchesCleared": searches}


@router.route("GET", "/api/admin/activity")
def admin_activity(request):
    request.require("admin")
    days = int_param(request, "days", "Days", 1, 365) or 7
    since = time_ago(days=days)
    connection = request.connection
    totals = connection.execute(
        """SELECT COUNT(*) AS views, COUNT(DISTINCT user_id) AS signed_in_viewers,
                  COALESCE(SUM(user_id IS NULL), 0) AS guest_views
           FROM property_views WHERE viewed_at > ?""",
        (since,),
    ).fetchone()
    searches = connection.execute("SELECT COUNT(*) FROM search_history WHERE searched_at > ?", (since,)).fetchone()[0]
    top_listings = connection.execute(
        """SELECT p.id, p.title, p.area_name, p.city, p.listing_type, COUNT(*) AS views
           FROM property_views v JOIN properties p ON p.id = v.property_id
           WHERE v.viewed_at > ? GROUP BY p.id ORDER BY views DESC, p.id LIMIT 10""",
        (since,),
    ).fetchall()
    top_areas = connection.execute(
        """SELECT json_extract(filters, '$.area') AS area, COUNT(*) AS searches FROM search_history
           WHERE searched_at > ? AND json_extract(filters, '$.area') IS NOT NULL
           GROUP BY lower(json_extract(filters, '$.area')) ORDER BY searches DESC LIMIT 10""",
        (since,),
    ).fetchall()
    recent_views = connection.execute(
        """SELECT v.viewed_at, v.source, p.id AS property_id, p.title, u.full_name, u.role
           FROM property_views v JOIN properties p ON p.id = v.property_id LEFT JOIN users u ON u.id = v.user_id
           ORDER BY v.viewed_at DESC, v.id DESC LIMIT 30"""
    ).fetchall()
    recent_searches = connection.execute(
        """SELECT s.*, u.full_name, u.role FROM search_history s JOIN users u ON u.id = s.user_id
           ORDER BY s.searched_at DESC, s.id DESC LIMIT 20"""
    ).fetchall()
    return {
        "days": days,
        "totals": {
            "views": totals["views"],
            "guestViews": totals["guest_views"],
            "signedInViewers": totals["signed_in_viewers"],
            "searches": searches,
        },
        "topListings": [
            {"id": row["id"], "title": row["title"], "areaName": row["area_name"], "city": row["city"],
             "listingType": row["listing_type"], "views": row["views"]}
            for row in top_listings
        ],
        "topAreas": [{"area": row["area"], "searches": row["searches"]} for row in top_areas],
        "recentViews": [
            {"viewedAt": row["viewed_at"], "source": row["source"], "property": {"id": row["property_id"], "title": row["title"]},
             "viewer": {"name": row["full_name"], "role": row["role"]} if row["full_name"] else None}
            for row in recent_views
        ],
        "recentSearches": [
            {**search_json(row), "user": {"name": row["full_name"], "role": row["role"]}} for row in recent_searches
        ],
    }


def search_conditions(request):
    """Check the search filters and build the SQL for them. Shared by the result pages and the map (PB-37).

    Returns (select, where, params, order, filters, near). `near` is the point distances are measured from, or None.
    """
    query = request.query
    checker = Checker(query)
    purpose = checker.choice("purpose", "Listing type", ("sale", "rent", "any"), required=False, default="any")
    property_type = checker.choice("type", "Property type", PROPERTY_TYPES, required=False)
    min_price = checker.integer("minPrice", "Minimum price", 0, 10**12, required=False)
    max_price = checker.integer("maxPrice", "Maximum price", 0, 10**12, required=False)
    bedrooms = checker.integer("bedrooms", "Bedrooms", 0, 20, required=False)
    city = checker.choice("city", "District", CITIES, required=False)
    furnished = checker.choice("furnished", "Furnished", ("yes", "no"), required=False)
    radius = checker.choice("radius", "Distance", ("1", "3", "5", "10"), required=False, default="5")
    near = None
    if query.get("near"):
        landmark = LANDMARKS_BY_ID.get(query["near"])
        if landmark is None:
            checker.fail("near", "Choose a place from the list.")
        else:
            near = {"lat": landmark["lat"], "lng": landmark["lng"], "name": landmark["name"], "radiusKm": int(radius or 5)}
    elif query.get("lat") or query.get("lng"):
        # "Use my location": the browser sends the point. It is used for this search only and never saved.
        try:
            lat, lng = float(query.get("lat", "")), float(query.get("lng", ""))
            if not (LATITUDE_RANGE[0] <= lat <= LATITUDE_RANGE[1] and LONGITUDE_RANGE[0] <= lng <= LONGITUDE_RANGE[1]):
                raise ValueError
            near = {"lat": lat, "lng": lng, "name": "Your location", "radiusKm": int(radius or 5)}
        except ValueError:
            checker.fail("near", "Your location is outside Bangladesh or could not be read.")
    sorts = ("recommended", "newest", "price_asc", "price_desc", "distance")
    sort = checker.choice("sort", "Sort order", sorts, required=False, default="distance" if near else "recommended")
    if sort == "distance" and near is None:
        checker.fail("sort", "Choose a place to sort by distance.")
    if min_price is not None and max_price is not None and min_price > max_price:
        checker.fail("maxPrice", "Maximum price must be higher than the minimum price.")
    checker.done("Please check the search filters.")

    if near:
        select = PROPERTY_SELECT.replace(
            "FROM properties p", ", distance_km(p.latitude, p.longitude, ?, ?) AS distance_km\nFROM properties p", 1)
        params = [near["lat"], near["lng"]]
    else:
        select = PROPERTY_SELECT.replace("FROM properties p", ", NULL AS distance_km\nFROM properties p", 1)
        params = []
    where = ["p.listing_status = 'active'"]
    if purpose in ("sale", "rent"):
        where.append("p.listing_type = ?")
        params.append(purpose)
    area = (query.get("area") or "").strip()[:60]
    if area:
        pattern = "%" + area.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(p.area_name LIKE ? ESCAPE '\\' OR p.city LIKE ? ESCAPE '\\' OR p.address LIKE ? ESCAPE '\\')")
        params += [pattern, pattern, pattern]
    if city:
        where.append("p.city = ?")
        params.append(city)
    if property_type:
        where.append("p.property_type = ?")
        params.append(property_type)
    if furnished:
        where.append("p.furnished = ?")
        params.append(1 if furnished == "yes" else 0)
    if min_price is not None:
        where.append("amount >= ?")
        params.append(min_price)
    if max_price is not None:
        where.append("amount <= ?")
        params.append(max_price)
    if bedrooms:
        where.append("p.bedrooms >= ?")
        params.append(bedrooms)
    if query.get("verified") in ("1", "true"):
        where.append("p.verification_status = 'document_verified'")
    if near:
        where.append("distance_km IS NOT NULL AND distance_km <= ?")
        params.append(near["radiusKm"])

    order = {
        "recommended": "(p.verification_status = 'document_verified') DESC, p.created_at DESC, p.id DESC",
        "newest": "p.created_at DESC, p.id DESC",
        "price_asc": "amount ASC, p.id",
        "price_desc": "amount DESC, p.id",
        "distance": "distance_km ASC, p.id",
    }[sort]
    filters = {key: str(query[key]).strip()[:60] for key in SEARCH_FILTER_KEYS if str(query.get(key, "")).strip()}
    if filters.get("purpose") == "any":
        del filters["purpose"]
    if not query.get("near"):
        filters.pop("radius", None)   # a distance means nothing without a place
    return select, where, params, order, filters, near


@router.route("GET", "/api/properties")
def search_properties(request):
    select, where, params, order, filters, near = search_conditions(request)
    page = Checker(request.query).integer("page", "Page", 1, 100_000, required=False)
    if page is None and request.query.get("page") not in (None, ""):
        raise ApiError(400, "Please check the search filters.", {"page": "Page must be a whole number from 1 to 100000."})
    page = page or 1
    matching = select + " WHERE " + " AND ".join(where)
    total = request.connection.execute(f"SELECT COUNT(*) FROM ({matching})", params).fetchone()[0]
    # 12 homes per page. A page past the end shows the last page instead of nothing.
    pages = max(1, -(-total // SEARCH_PAGE_SIZE))
    page = min(page, pages)
    rows = request.connection.execute(
        matching + " ORDER BY " + order + " LIMIT ? OFFSET ?", (*params, SEARCH_PAGE_SIZE, (page - 1) * SEARCH_PAGE_SIZE)
    ).fetchall()
    # Turning to another page is the same search, so only the first page is saved in the history.
    if page == 1:
        record_search(request, filters, total)
    return {
        "properties": [property_json(row, request.user) for row in rows],
        "total": total,
        "page": page,
        "pages": pages,
        "pageSize": SEARCH_PAGE_SIZE,
        "near": near,
    }


@router.route("GET", "/api/properties/{id}")
def get_property(request):
    row = fetch_property(request.connection, request.params["id"])
    viewer = request.user
    visible = row is not None and (
        row["listing_status"] == "active"
        or (viewer is not None and (viewer["id"] == row["owner_id"] or is_staff(viewer)) and row["listing_status"] != "removed")
    )
    if not visible:
        raise ApiError(404, "This listing does not exist or has been removed.")
    data = property_json(row, viewer)
    data["images"] = photos.list_images(request.connection, row["id"])
    data["priceGuide"] = sprint5.price_position(request.connection, row)
    if viewer is not None and viewer["role"] == "buyer_tenant":
        data["isFavorite"] = request.connection.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND property_id = ?", (viewer["id"], row["id"])
        ).fetchone() is not None
    if data["isOwner"]:
        data["verificationRequest"] = latest_request_summary(request.connection, row["id"])
        data["views"] = view_counts(request.connection, row["id"])
    record_view(request, row)
    return data


# ---------------------------------------------------------------- owner listings (PB-03, PB-05, PB-09)

def latest_request_summary(connection, property_id):
    row = connection.execute(
        """SELECT vr.*, (SELECT COUNT(DISTINCT d.document_type) FROM legal_documents d
                         WHERE d.request_id = vr.id AND d.is_current = 1
                           AND d.document_type IN ('land_deed', 'mutation', 'tax_receipt')) AS required_uploaded
           FROM verification_requests vr WHERE vr.property_id = ? ORDER BY vr.id DESC LIMIT 1""",
        (property_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "status": row["status"],
        "advocateNotes": row["advocate_notes"],
        "submittedAt": row["submitted_at"],
        "requiredUploaded": row["required_uploaded"],
        "requiredTotal": len(REQUIRED_DOCUMENT_TYPES),
    }


def save_rent_details(connection, property_id, rent):
    connection.execute(
        """INSERT INTO rent_details (property_id, monthly_rent, security_deposit, available_from,
                                     min_lease_months, utilities_included, tenant_preference)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (property_id) DO UPDATE SET
               monthly_rent = excluded.monthly_rent, security_deposit = excluded.security_deposit,
               available_from = excluded.available_from, min_lease_months = excluded.min_lease_months,
               utilities_included = excluded.utilities_included, tenant_preference = excluded.tenant_preference""",
        (
            property_id,
            rent["monthlyRent"],
            rent["securityDeposit"],
            rent["availableFrom"],
            rent["minLeaseMonths"],
            int(rent["utilitiesIncluded"]),
            rent["tenantPreference"],
        ),
    )


def reject_verification_fields(data):
    if any(key in data for key in ("verificationStatus", "badgeLevel", "verification_status", "badge_level")):
        raise ApiError(403, "Only an advocate can change the verification status of a listing.")


@router.route("POST", "/api/properties")
def create_property(request):
    user = request.require("owner")
    sprint5.require_confirmed_phone(user)
    data = request.json()
    reject_verification_fields(data)
    listing, rent = clean_listing(data)
    sprint5.clean_location(data)   # a wrong map pin is refused before anything is saved
    connection = request.connection
    now = utc_now()
    # PB-09: the listing goes live at once and starts as 'unverified'.
    cursor = connection.execute(
        """INSERT INTO properties (owner_id, title, description, listing_type, property_type, price, area_name,
                                   city, address, size_sqft, bedrooms, bathrooms, furnished, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user["id"], listing["title"], listing["description"], listing["listingType"], listing["propertyType"],
            listing["price"], listing["areaName"], listing["city"], listing["address"], listing["sizeSqft"],
            listing["bedrooms"], listing["bathrooms"], int(listing["furnished"]), now, now,
        ),
    )
    property_id = cursor.lastrowid
    if rent:
        save_rent_details(connection, property_id, rent)
    sprint5.save_location(connection, property_id, data, listing)
    sprint5.check_duplicate_text(connection, property_id)
    audit(connection, user["id"], "listing_created", "property", property_id, None, "active / unverified", listing["title"])

    request_id = None
    if data.get("requestVerification") is True:
        request_id = create_verification_request(connection, user, fetch_property(connection, property_id))
    return Response(201, {"property": property_json(fetch_property(connection, property_id), user), "verificationRequestId": request_id})


@router.route("PUT", "/api/properties/{id}")
def update_property(request):
    user = request.require("owner")
    row = owned_property(request, user)
    data = request.json()
    reject_verification_fields(data)
    listing, rent = clean_listing(data, existing_available_from=row["available_from"])
    checker = Checker(data)
    listing_status = checker.choice("listingStatus", "Listing status", ("active", "sold_rented"), required=False, default=row["listing_status"])
    checker.done()

    connection = request.connection
    columns = {
        "title": "title", "description": "description", "listingType": "listing_type", "propertyType": "property_type",
        "price": "price", "areaName": "area_name", "city": "city", "address": "address", "sizeSqft": "size_sqft",
        "bedrooms": "bedrooms", "bathrooms": "bathrooms", "furnished": "furnished",
    }
    new_values = {column: (int(listing[key]) if key == "furnished" else listing[key]) for key, column in columns.items()}
    changed = [column for column, value in new_values.items() if row[column] != value]
    if rent and row["listing_type"] == "rent":
        old_rent = (row["monthly_rent"], row["security_deposit"], row["available_from"], row["min_lease_months"],
                    bool(row["utilities_included"]), row["tenant_preference"])
        new_rent = (rent["monthlyRent"], rent["securityDeposit"], rent["availableFrom"], rent["minLeaseMonths"],
                    rent["utilitiesIncluded"], rent["tenantPreference"])
        if old_rent != new_rent:
            changed.append("rent_details")

    connection.execute(
        "UPDATE properties SET " + ", ".join(f"{column} = ?" for column in new_values) + ", listing_status = ?, updated_at = ? WHERE id = ?",
        (*new_values.values(), listing_status, utc_now(), row["id"]),
    )
    if rent:
        save_rent_details(connection, row["id"], rent)
    else:
        connection.execute("DELETE FROM rent_details WHERE property_id = ?", (row["id"],))
    sprint5.save_location(connection, row["id"], data, listing, row)
    if "description" in changed:
        sprint5.check_duplicate_text(connection, row["id"])
    if changed:
        audit(connection, user["id"], "listing_updated", "property", row["id"], None, None, "Changed: " + ", ".join(changed))
    if listing_status != row["listing_status"]:
        audit(connection, user["id"], "listing_status_changed", "property", row["id"], row["listing_status"], listing_status)

    # A verified badge describes the papers for one place. Moving the listing to
    # another place or property type removes the badge until it is checked again.
    identity_columns = {"listing_type", "property_type", "area_name", "city", "address"}
    if row["verification_status"] == "document_verified" and identity_columns & set(changed):
        connection.execute(
            "UPDATE properties SET verification_status = 'unverified', badge_level = 'none' WHERE id = ?", (row["id"],)
        )
        audit(connection, user["id"], "verification_status_changed", "property", row["id"], "document_verified", "unverified",
              "Badge removed because the address or property type was changed by the owner.")
    return {"property": property_json(fetch_property(connection, row["id"]), user)}


@router.route("DELETE", "/api/properties/{id}")
def delete_property(request):
    user = request.require("owner")
    row = owned_property(request, user)
    request.connection.execute(
        "UPDATE properties SET listing_status = 'removed', updated_at = ? WHERE id = ?", (utc_now(), row["id"])
    )
    audit(request.connection, user["id"], "listing_status_changed", "property", row["id"], row["listing_status"], "removed", "Deleted by owner")
    return {"status": "removed"}


@router.route("GET", "/api/my/listings")
def my_listings(request):
    user = request.require("owner")
    rows = request.connection.execute(
        PROPERTY_SELECT + " WHERE p.owner_id = ? AND p.listing_status != 'removed' ORDER BY p.created_at DESC, p.id DESC",
        (user["id"],),
    ).fetchall()
    listings = []
    for row in rows:
        data = property_json(row, user)
        data["verificationRequest"] = latest_request_summary(request.connection, row["id"])
        data["views"] = view_counts(request.connection, row["id"])
        listings.append(data)
    return {"properties": listings}


# ---------------------------------------------------------------- favorites and inquiries (baseline features)

@router.route("GET", "/api/favorites")
def list_favorites(request):
    user = request.require("buyer_tenant")
    rows = request.connection.execute(
        PROPERTY_SELECT + """ JOIN favorites f ON f.property_id = p.id
           WHERE f.user_id = ? AND p.listing_status = 'active' ORDER BY f.saved_at DESC""",
        (user["id"],),
    ).fetchall()
    return {"properties": [property_json(row, user) for row in rows]}


@router.route("PUT", "/api/favorites/{id}")
def add_favorite(request):
    user = request.require("buyer_tenant")
    row = fetch_property(request.connection, request.params["id"])
    if row is None or row["listing_status"] != "active":
        raise ApiError(404, "This listing does not exist.")
    request.connection.execute(
        "INSERT OR IGNORE INTO favorites (user_id, property_id, saved_at) VALUES (?, ?, ?)", (user["id"], row["id"], utc_now())
    )
    return {"saved": True}


@router.route("DELETE", "/api/favorites/{id}")
def remove_favorite(request):
    user = request.require("buyer_tenant")
    request.connection.execute("DELETE FROM favorites WHERE user_id = ? AND property_id = ?", (user["id"], request.params["id"]))
    return {"saved": False}


@router.route("POST", "/api/properties/{id}/inquiries")
def send_inquiry(request):
    user = request.require("buyer_tenant")
    row = fetch_property(request.connection, request.params["id"])
    if row is None or row["listing_status"] != "active":
        raise ApiError(404, "This listing does not exist.")
    checker = Checker(request.json())
    checker.text("message", "Message", min_length=5, max_length=1000)
    check_phone(checker)
    data = checker.done()
    cursor = request.connection.execute(
        """INSERT INTO inquiries (property_id, sender_id, sender_name, sender_phone, message, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (row["id"], user["id"], user["full_name"], data["phone"], data["message"], utc_now()),
    )
    return Response(201, {"id": cursor.lastrowid})


@router.route("GET", "/api/inquiries")
def list_inquiries(request):
    user = request.require("buyer_tenant", "owner")
    column = "i.sender_id" if user["role"] == "buyer_tenant" else "p.owner_id"
    rows = request.connection.execute(
        f"""SELECT i.*, p.title AS property_title, p.area_name FROM inquiries i
            JOIN properties p ON p.id = i.property_id WHERE {column} = ? ORDER BY i.created_at DESC, i.id DESC""",
        (user["id"],),
    ).fetchall()
    return {
        "inquiries": [
            {
                "id": row["id"],
                "property": {"id": row["property_id"], "title": row["property_title"], "areaName": row["area_name"]},
                "senderName": row["sender_name"],
                "senderPhone": row["sender_phone"],
                "message": row["message"],
                "status": row["status"],
                "replyMessage": row["reply_message"],
                "createdAt": row["created_at"],
                "repliedAt": row["replied_at"],
            }
            for row in rows
        ]
    }


@router.route("POST", "/api/inquiries/{id}/reply")
def reply_inquiry(request):
    user = request.require("owner")
    row = request.connection.execute(
        "SELECT i.*, p.owner_id FROM inquiries i JOIN properties p ON p.id = i.property_id WHERE i.id = ?",
        (request.params["id"],),
    ).fetchone()
    if row is None:
        raise ApiError(404, "This inquiry does not exist.")
    if row["owner_id"] != user["id"]:
        raise ApiError(403, "You can only reply to inquiries about your own listings.")
    checker = Checker(request.json())
    checker.text("reply", "Reply", min_length=2, max_length=1000)
    data = checker.done()
    request.connection.execute(
        "UPDATE inquiries SET reply_message = ?, status = 'replied', replied_at = ? WHERE id = ?",
        (data["reply"], utc_now(), row["id"]),
    )
    return {"status": "replied"}


# ---------------------------------------------------------------- legal verification (PB-10 to PB-17)

REQUEST_SELECT = f"""
SELECT vr.*, p.title, p.area_name, p.city, p.address, p.listing_type, p.property_type, p.listing_status,
       p.badge_level, p.verification_status AS property_verification,
       o.full_name AS owner_name, a.full_name AS advocate_name,
       {HIGH_DEMAND_SQL} AS is_high_demand,
       (SELECT COUNT(DISTINCT d.document_type) FROM legal_documents d
        WHERE d.request_id = vr.id AND d.is_current = 1
          AND d.document_type IN ('land_deed', 'mutation', 'tax_receipt')) AS required_uploaded
FROM verification_requests vr
JOIN properties p ON p.id = vr.property_id
JOIN users o ON o.id = vr.owner_id
LEFT JOIN users a ON a.id = vr.advocate_id
"""


def request_summary_json(row):
    return {
        "id": row["id"],
        "status": row["status"],
        "submittedAt": row["submitted_at"],
        "assignedAt": row["assigned_at"],
        "completedAt": row["completed_at"],
        "isHighDemand": bool(row["is_high_demand"]),
        "resubmissionCount": row["resubmission_count"],
        "requiredUploaded": row["required_uploaded"],
        "requiredTotal": len(REQUIRED_DOCUMENT_TYPES),
        "property": {
            "id": row["property_id"],
            "title": row["title"],
            "areaName": row["area_name"],
            "city": row["city"],
            "listingStatus": row["listing_status"],
        },
        "owner": {"id": row["owner_id"], "name": row["owner_name"]},
        "advocate": {"id": row["advocate_id"], "name": row["advocate_name"]} if row["advocate_id"] else None,
    }


def load_request(connection, request_id):
    row = connection.execute(REQUEST_SELECT + " WHERE vr.id = ?", (request_id,)).fetchone()
    if row is None:
        raise ApiError(404, "This verification request does not exist.")
    return row


def can_view_request(user, row):
    if user["role"] == "admin":
        return True
    if user["role"] == "owner":
        return row["owner_id"] == user["id"]
    if user["role"] == "advocate" and is_staff(user):
        return row["advocate_id"] == user["id"] or (row["status"] == "pending" and row["advocate_id"] is None)
    return False


def can_open_files(user, row):
    """PB-11: only the owner, the assigned advocate and admins can open the papers."""
    return (
        user["role"] == "admin"
        or (user["role"] == "owner" and row["owner_id"] == user["id"])
        or (user["role"] == "advocate" and is_staff(user) and row["advocate_id"] == user["id"])
    )


def request_detail_json(connection, row, user):
    data = request_summary_json(row)
    data["property"].update(
        {"address": row["address"], "listingType": row["listing_type"], "propertyType": row["property_type"]}
    )
    data["advocateNotes"] = row["advocate_notes"]
    data["checklist"] = json.loads(row["checklist"]) if row["checklist"] else None
    # PB-19: the advocate who verified the listing can raise its badge level.
    is_current = row["status"] == "document_verified" and row["property_verification"] == "document_verified"
    data["badgeLevel"] = row["badge_level"] if is_current else None
    data["canSetBadgeLevel"] = is_current and user["role"] == "advocate" and row["advocate_id"] == user["id"]
    documents = connection.execute(
        "SELECT * FROM legal_documents WHERE request_id = ? ORDER BY uploaded_at DESC, id DESC", (row["id"],)
    ).fetchall()
    data["documents"] = [document_json(doc) for doc in documents if doc["is_current"]]
    data["replacedDocuments"] = [document_json(doc) for doc in documents if not doc["is_current"]]
    uploaded = {doc["document_type"] for doc in documents if doc["is_current"]}
    data["missingDocuments"] = [key for key in REQUIRED_DOCUMENT_TYPES if key not in uploaded]
    data["canOpenFiles"] = can_open_files(user, row)
    data["canUpload"] = user["id"] == row["owner_id"] and row["status"] in ("pending", "issue_found")
    data["history"] = [
        audit_json(entry)
        for entry in connection.execute(
            AUDIT_SELECT + " WHERE a.target_type = 'verification_request' AND a.target_id = ? ORDER BY a.id",
            (row["id"],),
        )
    ]
    return data


def create_verification_request(connection, user, property_row):
    if property_row["verification_status"] == "document_verified":
        raise ApiError(409, "This listing is already verified.")
    existing = connection.execute(
        "SELECT id FROM verification_requests WHERE property_id = ? AND status IN (?, ?, ?)",
        (property_row["id"], *OPEN_REQUEST_STATUSES),
    ).fetchone()
    if existing:
        raise ApiError(409, "This listing already has an open verification request.")
    cursor = connection.execute(
        "INSERT INTO verification_requests (property_id, owner_id, status, submitted_at) VALUES (?, ?, 'pending', ?)",
        (property_row["id"], user["id"], utc_now()),
    )
    audit(connection, user["id"], "verification_requested", "verification_request", cursor.lastrowid, None, "pending",
          f"Property #{property_row['id']}: {property_row['title']}")
    notify_advocates(connection, "verification_request", "New verification request",
                     f"{property_row['title']} in {property_row['area_name']} is waiting in the queue.",
                     f"/advocate/requests/{cursor.lastrowid}")
    return cursor.lastrowid


@router.route("POST", "/api/properties/{id}/verification-request")
def request_verification(request):
    user = request.require("owner")
    row = owned_property(request, user)
    if row["listing_status"] != "active":
        raise ApiError(409, "Only active listings can be verified.")
    request_id = create_verification_request(request.connection, user, row)
    return Response(201, {"requestId": request_id})


@router.route("GET", "/api/verification-requests/{id}")
def get_verification_request(request):
    user = request.require()
    row = load_request(request.connection, request.params["id"])
    if not can_view_request(user, row):
        raise ApiError(403, "You do not have access to this verification request.")
    return request_detail_json(request.connection, row, user)


def set_property_verification(connection, actor_id, property_id, new_status, details=None):
    old = connection.execute("SELECT verification_status FROM properties WHERE id = ?", (property_id,)).fetchone()[0]
    if old == new_status:
        return
    connection.execute(
        "UPDATE properties SET verification_status = ?, badge_level = ?, updated_at = ? WHERE id = ?",
        (new_status, "document_verified" if new_status == "document_verified" else "none", utc_now(), property_id),
    )
    audit(connection, actor_id, "verification_status_changed", "property", property_id, old, new_status, details)


@router.route("POST", "/api/verification-requests/{id}/documents")
@accepts_upload
def upload_document(request):
    user = request.require("owner")
    connection = request.connection
    row = load_request(connection, request.params["id"])
    if row["owner_id"] != user["id"]:
        raise ApiError(403, "You can only upload papers for your own listings.")
    if row["status"] == "in_review":
        raise ApiError(409, "The advocate is reviewing your papers now. You can upload again if an issue is found.")
    if row["status"] == "document_verified":
        raise ApiError(409, "This listing is already verified.")

    document_type = request.query.get("type")
    if document_type not in DOCUMENT_TYPES:
        raise ApiError(400, "Choose which paper you are uploading.")
    file_name = os.path.basename((request.query.get("name") or "").replace("\\", "/")).strip()
    file_name = re.sub(r"[\x00-\x1f\x7f]", "", file_name)[:120]
    extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    file_type = {"pdf": "pdf", "png": "png", "jpg": "jpg", "jpeg": "jpg"}.get(extension)
    if file_type is None:
        raise ApiError(400, "Only PDF, JPG and PNG files are accepted.")
    body = request.body
    if not body:
        raise ApiError(400, "The file is empty.")
    if not body.startswith(FILE_SIGNATURES[file_type]):
        raise ApiError(400, f"This file is not a real {file_type.upper()} file.")

    storage_name = f"{secrets.token_hex(16)}.{file_type}"
    path = request.config.upload_dir / storage_name
    path.write_bytes(body)
    try:
        connection.execute(
            "UPDATE legal_documents SET is_current = 0 WHERE request_id = ? AND document_type = ? AND is_current = 1",
            (row["id"], document_type),
        )
        cursor = connection.execute(
            """INSERT INTO legal_documents (request_id, document_type, file_name, file_type, file_size_kb,
                                            storage_name, uploaded_by, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (row["id"], document_type, file_name, file_type, max(1, round(len(body) / 1024)), storage_name, user["id"], utc_now()),
        )
        audit(connection, user["id"], "document_uploaded", "verification_request", row["id"], None,
              document_type, file_name)

        # PB-14: a corrected paper sends the request back to the queue.
        if row["status"] == "issue_found":
            connection.execute(
                """UPDATE verification_requests SET status = 'pending', advocate_id = NULL, assigned_at = NULL,
                       completed_at = NULL, resubmission_count = resubmission_count + 1 WHERE id = ?""",
                (row["id"],),
            )
            audit(connection, user["id"], "verification_status_changed", "verification_request", row["id"],
                  "issue_found", "pending", "Owner uploaded a corrected paper.")
            set_property_verification(connection, user["id"], row["property_id"], "unverified", "Corrected paper uploaded.")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    document = connection.execute("SELECT * FROM legal_documents WHERE id = ?", (cursor.lastrowid,)).fetchone()
    status = connection.execute("SELECT status FROM verification_requests WHERE id = ?", (row["id"],)).fetchone()[0]
    return Response(201, {"document": document_json(document), "requestStatus": status})


@router.route("GET", "/api/documents/{id}/file")
def download_document(request):
    user = request.require()
    document = request.connection.execute(
        """SELECT d.*, vr.owner_id, vr.advocate_id FROM legal_documents d
           JOIN verification_requests vr ON vr.id = d.request_id WHERE d.id = ?""",
        (request.params["id"],),
    ).fetchone()
    if document is None:
        raise ApiError(404, "This document does not exist.")
    if not can_open_files(user, document):
        raise ApiError(403, "Only the owner, the assigned advocate and admins can open this document.")
    path = request.config.upload_dir / document["storage_name"]
    if not path.is_file():
        raise ApiError(404, "The file is missing from storage.")
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", document["file_name"])
    return Response(
        200,
        body=path.read_bytes(),
        content_type=FILE_CONTENT_TYPES[document["file_type"]],
        headers=[("Content-Disposition", f'inline; filename="{safe_name}"')],
    )


@router.route("GET", "/api/advocate/application")
def advocate_application(request):
    """The advocate's own verification status, with the admin's appointment message."""
    user = request.require()
    if user["role"] != "advocate":
        raise ApiError(403, "Your account role cannot use this feature.")
    row = load_advocate(request.connection, user["id"])
    return {"application": advocate_json(row), "user": user_json(row)}


@router.route("GET", "/api/advocate/queue")
def advocate_queue(request):
    user = request.require("advocate")
    # PB-12 and PB-17: high-demand areas first, then the oldest request first.
    queue = request.connection.execute(
        REQUEST_SELECT + """ WHERE p.listing_status = 'active'
            AND ((vr.status = 'pending' AND vr.advocate_id IS NULL) OR (vr.status = 'in_review' AND vr.advocate_id = ?))
            ORDER BY is_high_demand DESC, vr.submitted_at ASC, vr.id ASC""",
        (user["id"],),
    ).fetchall()
    recent = request.connection.execute(
        REQUEST_SELECT + """ WHERE vr.advocate_id = ? AND vr.status IN ('document_verified', 'issue_found')
            ORDER BY vr.completed_at DESC LIMIT 10""",
        (user["id"],),
    ).fetchall()
    return {"queue": [request_summary_json(row) for row in queue], "recentDecisions": [request_summary_json(row) for row in recent]}


@router.route("POST", "/api/verification-requests/{id}/start-review")
def start_review(request):
    user = request.require("advocate")
    connection = request.connection
    row = load_request(connection, request.params["id"])
    if row["status"] != "pending" or row["advocate_id"] is not None:
        raise ApiError(409, "This request is no longer waiting in the queue.")
    if row["listing_status"] != "active":
        raise ApiError(409, "This listing is no longer active.")
    if row["required_uploaded"] < len(REQUIRED_DOCUMENT_TYPES):
        raise ApiError(409, "The owner has not uploaded all required papers yet.")
    cursor = connection.execute(
        """UPDATE verification_requests SET status = 'in_review', advocate_id = ?, assigned_at = ?
           WHERE id = ? AND status = 'pending' AND advocate_id IS NULL""",
        (user["id"], utc_now(), row["id"]),
    )
    if cursor.rowcount != 1:
        raise ApiError(409, "Another advocate picked up this request first.")
    audit(connection, user["id"], "verification_status_changed", "verification_request", row["id"], "pending", "in_review",
          f"Review started by {user['full_name']}")
    return request_detail_json(connection, load_request(connection, row["id"]), user)


@router.route("POST", "/api/verification-requests/{id}/decision")
def decide_request(request):
    user = request.require("advocate")
    connection = request.connection
    row = load_request(connection, request.params["id"])
    if row["advocate_id"] != user["id"]:
        raise ApiError(403, "Only the advocate reviewing this request can decide it.")
    if row["status"] != "in_review":
        raise ApiError(409, "This request is not in review.")

    data = request.json()
    checker = Checker(data)
    decision = checker.choice("decision", "Decision", ("document_verified", "issue_found"))
    checker.text("notes", "A note", min_length=10, max_length=2000)
    raw_checklist = data.get("checklist") if isinstance(data.get("checklist"), dict) else {}
    checklist = {}
    for item in CHECKLIST_ITEMS:
        value = raw_checklist.get(item)
        if value not in ("ok", "problem"):
            checker.fail(f"checklist.{item}", "Mark this check as OK or Problem.")
        else:
            checklist[item] = value
    if len(checklist) == len(CHECKLIST_ITEMS):
        if decision == "document_verified" and "problem" in checklist.values():
            checker.fail("decision", "Every check must be OK to mark the property Document Verified.")
        if decision == "issue_found" and "problem" not in checklist.values():
            checker.fail("decision", "Mark at least one check as Problem to report an issue.")
    cleaned = checker.done()

    connection.execute(
        """UPDATE verification_requests SET status = ?, completed_at = ?, advocate_notes = ?, checklist = ?
           WHERE id = ?""",
        (decision, utc_now(), cleaned["notes"], json.dumps(checklist), row["id"]),
    )
    for item, result in checklist.items():
        connection.execute(
            "UPDATE legal_documents SET review_status = ? WHERE request_id = ? AND document_type = ? AND is_current = 1",
            (result, row["id"], item),
        )
    audit(connection, user["id"], "verification_status_changed", "verification_request", row["id"], "in_review", decision,
          cleaned["notes"])
    set_property_verification(connection, user["id"], row["property_id"], decision, f"Decision on request #{row['id']}")
    if decision == "document_verified":
        reports.ensure_report(connection, row["id"])  # PB-18: the legal report is created with the decision
        sprint4.alert_saved_searches(connection, row["property_id"])  # PB-28: tell buyers whose saved search matches
        notify(connection, row["owner_id"], "verification_result", "Your property is Document Verified",
               f"{row['title']} now shows the Verified badge. Buyers can download its legal report.",
               f"/owner/verification/{row['id']}")
    else:
        notify(connection, row["owner_id"], "verification_result", "An issue was found in your papers",
               f"{row['title']}: read the advocate's notes and upload a corrected paper.",
               f"/owner/verification/{row['id']}")
    return request_detail_json(connection, load_request(connection, row["id"]), user)


@router.route("POST", "/api/verification-requests/{id}/badge-level")
def set_badge_level(request):
    """PB-19: the advocate who verified a listing sets how much checking was done."""
    user = request.require("advocate")
    connection = request.connection
    row = load_request(connection, request.params["id"])
    if row["advocate_id"] != user["id"]:
        raise ApiError(403, "Only the advocate who verified this listing can change its badge level.")
    if row["status"] != "document_verified" or row["property_verification"] != "document_verified":
        raise ApiError(409, "A badge level can only be set on a verified listing.")
    checker = Checker(request.json())
    level = checker.choice("level", "Badge level", reports.BADGE_LEVELS)
    checker.done()
    if level != row["badge_level"]:
        connection.execute("UPDATE properties SET badge_level = ?, updated_at = ? WHERE id = ?", (level, utc_now(), row["property_id"]))
        reports.set_report_level(connection, row["id"], level)
        audit(connection, user["id"], "badge_level_changed", "property", row["property_id"], row["badge_level"], level,
              f"Set on request #{row['id']}")
        notify(connection, row["owner_id"], "verification_result", f"Badge level: {reports.BADGE_LABELS[level]}",
               f"{row['title']} now shows the {reports.BADGE_LABELS[level]} badge.", f"/property/{row['property_id']}")
    return request_detail_json(connection, load_request(connection, row["id"]), user)


@router.route("GET", "/api/properties/{id}/legal-report")
def download_legal_report(request):
    """PB-18: anyone looking at a verified listing can download its plain-language report."""
    row = fetch_property(request.connection, request.params["id"])
    report = None
    if row is not None and row["listing_status"] == "active" and row["verification_status"] == "document_verified":
        report = reports.current_report(request.connection, row["id"])
    if report is None:
        raise ApiError(404, "This listing has no legal report. Reports are made when an advocate verifies a property.")
    return Response(
        body=reports.report_pdf(report),
        content_type="application/pdf",
        headers=[("Content-Disposition", f'inline; filename="PFB-legal-report-{row["id"]}.pdf"')],
    )


# ---------------------------------------------------------------- admin (PB-04, PB-16, PB-17)

def advocate_json(row):
    data = user_json(row)
    data.update(
        {
            "barCouncilId": row["bar_council_id"],
            "specialization": row["specialization"],
            "activeCases": row["active_cases"],
            "completedCases": row["completed_cases"],
            "appointment": {"at": row["appointment_at"], "place": row["appointment_place"]} if row["appointment_at"] else None,
            "adminMessage": row["admin_message"],
            "reviewedAt": row["reviewed_at"],
        }
    )
    return data


ADVOCATE_SELECT = """
SELECT u.*, ap.bar_council_id, ap.specialization, ap.verification_status AS advocate_status,
       ap.appointment_at, ap.appointment_place, ap.admin_message, ap.reviewed_at,
       (SELECT COUNT(*) FROM verification_requests vr WHERE vr.advocate_id = u.id AND vr.status = 'in_review') AS active_cases,
       (SELECT COUNT(*) FROM verification_requests vr WHERE vr.advocate_id = u.id
          AND vr.status IN ('document_verified', 'issue_found')) AS completed_cases
FROM users u JOIN advocate_profiles ap ON ap.user_id = u.id
WHERE u.role = 'advocate'"""


def load_advocate(connection, advocate_id):
    row = connection.execute(ADVOCATE_SELECT + " AND u.id = ? AND u.account_status != 'removed'", (advocate_id,)).fetchone()
    if row is None:
        raise ApiError(404, "This advocate does not exist.")
    return row


def release_cases(connection, actor_id, advocate_id, reason):
    """Return an advocate's open reviews to the queue so other advocates can pick them up."""
    for (request_id,) in connection.execute(
        "SELECT id FROM verification_requests WHERE advocate_id = ? AND status = 'in_review'", (advocate_id,)
    ).fetchall():
        connection.execute(
            "UPDATE verification_requests SET status = 'pending', advocate_id = NULL, assigned_at = NULL WHERE id = ?",
            (request_id,),
        )
        audit(connection, actor_id, "verification_status_changed", "verification_request", request_id, "in_review", "pending", reason)


@router.route("GET", "/api/admin/advocates")
def list_advocates(request):
    request.require("admin")
    rows = request.connection.execute(ADVOCATE_SELECT + " AND u.account_status != 'removed' ORDER BY u.full_name").fetchall()
    return {"advocates": [advocate_json(row) for row in rows]}


@router.route("POST", "/api/admin/advocates")
def add_advocate(request):
    admin = request.require("admin")
    data = check_advocate_fields(Checker(request.json()))
    connection = request.connection
    # The admin has already checked this advocate, so the account is verified from the start.
    advocate_id = create_advocate(connection, data, "verified", added_by=admin["id"])
    audit(connection, admin["id"], "advocate_added", "user", advocate_id, None, "active", data["fullName"])
    return Response(201, {"advocate": advocate_json(load_advocate(connection, advocate_id))})


BANGLADESH_TIME = timezone(timedelta(hours=6))
APPOINTMENT_MAX_DAYS = 90


@router.route("POST", "/api/admin/advocates/{id}/appointment")
def send_advocate_appointment(request):
    """Invite an advocate who applied to come in person. Sending again replaces the earlier appointment."""
    admin = request.require("admin")
    connection = request.connection
    row = load_advocate(connection, request.params["id"])
    if row["advocate_status"] == "verified":
        raise ApiError(409, "This advocate is already verified.")
    data = request.json()
    checker = Checker(data)
    checker.text("place", "Place", min_length=5, max_length=160)
    checker.text("message", "Message", max_length=500, required=False)
    when = None
    try:
        when = datetime.strptime(str(data.get("appointmentAt", "")), "%Y-%m-%dT%H:%M")
    except ValueError:
        checker.fail("appointmentAt", "Choose the appointment date and time.")
    else:
        now = datetime.now(BANGLADESH_TIME).replace(tzinfo=None)
        if when <= now:
            checker.fail("appointmentAt", "The appointment must be in the future.")
        elif when > now + timedelta(days=APPOINTMENT_MAX_DAYS):
            checker.fail("appointmentAt", f"The appointment must be within the next {APPOINTMENT_MAX_DAYS} days.")
    cleaned = checker.done()
    appointment_at = when.strftime("%Y-%m-%dT%H:%M")
    connection.execute(
        """UPDATE advocate_profiles SET verification_status = 'appointment_sent', appointment_at = ?, appointment_place = ?,
               admin_message = ?, reviewed_by = ?, reviewed_at = ? WHERE user_id = ?""",
        (appointment_at, cleaned["place"], cleaned["message"] or None, admin["id"], utc_now(), row["id"]),
    )
    audit(connection, admin["id"], "advocate_appointment_sent", "user", row["id"], row["advocate_status"], "appointment_sent",
          f"{row['full_name']}: {appointment_at.replace('T', ' ')} at {cleaned['place']}")
    notify(connection, row["id"], "advocate_account", "You have an appointment",
           f"{consult.nice_time(appointment_at)}, {cleaned['place']}", "/advocate/application")
    return {"advocate": advocate_json(load_advocate(connection, row["id"]))}


@router.route("POST", "/api/admin/advocates/{id}/verification")
def decide_advocate(request):
    """Verify an advocate after the in-person meeting, or reject the application."""
    admin = request.require("admin")
    connection = request.connection
    row = load_advocate(connection, request.params["id"])
    if row["advocate_status"] == "verified":
        raise ApiError(409, "This advocate is already verified.")
    checker = Checker(request.json())
    decision = checker.choice("decision", "Decision", ("verified", "rejected"))
    note = checker.text("note", "Reason", min_length=5, max_length=500, required=decision == "rejected")
    checker.done()
    if decision == "verified" and row["advocate_status"] != "appointment_sent":
        raise ApiError(409, "Send an appointment and meet the advocate in person before verifying them.")
    if decision == row["advocate_status"]:
        raise ApiError(409, "This application is already rejected.")
    connection.execute(
        "UPDATE advocate_profiles SET verification_status = ?, admin_message = ?, reviewed_by = ?, reviewed_at = ? WHERE user_id = ?",
        (decision, note or None, admin["id"], utc_now(), row["id"]),
    )
    audit(connection, admin["id"], "advocate_verification_changed", "user", row["id"], row["advocate_status"], decision,
          f"{row['full_name']}: {note}" if note else row["full_name"])
    if decision == "verified":
        notify(connection, row["id"], "advocate_account", "Your advocate account is verified",
               "You can now open the verification queue and answer consultations.", "/advocate")
    else:
        notify(connection, row["id"], "advocate_account", "Your application was not approved", note or "", "/advocate/application")
    return {"advocate": advocate_json(load_advocate(connection, row["id"]))}


@router.route("POST", "/api/admin/advocates/{id}/status")
def set_advocate_status(request):
    admin = request.require("admin")
    connection = request.connection
    row = load_advocate(connection, request.params["id"])
    checker = Checker(request.json())
    status = checker.choice("status", "Status", ("active", "blocked"))
    checker.done()
    if status != row["account_status"]:
        connection.execute("UPDATE users SET account_status = ? WHERE id = ?", (status, row["id"]))
        audit(connection, admin["id"], "account_status_changed", "user", row["id"], row["account_status"], status, row["full_name"])
        if status == "blocked":
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
            release_cases(connection, admin["id"], row["id"], "Advocate was blocked; request returned to the queue.")
    return {"advocate": advocate_json(load_advocate(connection, row["id"]))}


@router.route("DELETE", "/api/admin/advocates/{id}")
def remove_advocate(request):
    admin = request.require("admin")
    connection = request.connection
    row = load_advocate(connection, request.params["id"])
    # The account is kept (marked removed) so the audit log still shows who did past reviews.
    connection.execute("UPDATE users SET account_status = 'removed' WHERE id = ?", (row["id"],))
    connection.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
    audit(connection, admin["id"], "account_status_changed", "user", row["id"], row["account_status"], "removed", row["full_name"])
    release_cases(connection, admin["id"], row["id"], "Advocate was removed; request returned to the queue.")
    return {"status": "removed"}


@router.route("GET", "/api/admin/high-demand-areas")
def list_high_demand_areas(request):
    request.require("admin")
    rows = request.connection.execute(
        f"""SELECT h.*, (SELECT COUNT(*) FROM verification_requests vr JOIN properties p ON p.id = vr.property_id
                          WHERE vr.status = 'pending' AND (lower(p.area_name) = lower(h.area_name)
                             OR lower(p.area_name) LIKE lower(h.area_name) || ' %')) AS pending_requests
            FROM high_demand_areas h ORDER BY h.area_name"""
    ).fetchall()
    return {"areas": [{"id": row["id"], "areaName": row["area_name"], "pendingRequests": row["pending_requests"], "createdAt": row["created_at"]} for row in rows]}


@router.route("POST", "/api/admin/high-demand-areas")
def add_high_demand_area(request):
    admin = request.require("admin")
    checker = Checker(request.json())
    name = checker.text("areaName", "Area name", min_length=2, max_length=60)
    if name and not AREA_NAME_PATTERN.match(name):
        checker.fail("areaName", "Use letters, numbers, spaces and . ' / - only.")
    checker.done()
    if request.connection.execute("SELECT 1 FROM high_demand_areas WHERE area_name = ?", (name,)).fetchone():
        raise ApiError(409, "Please fix the highlighted fields.", {"areaName": "This area is already marked as high-demand."})
    cursor = request.connection.execute(
        "INSERT INTO high_demand_areas (area_name, added_by, created_at) VALUES (?, ?, ?)", (name, admin["id"], utc_now())
    )
    audit(request.connection, admin["id"], "high_demand_area_added", "high_demand_area", cursor.lastrowid, None, name)
    return Response(201, {"id": cursor.lastrowid})


@router.route("DELETE", "/api/admin/high-demand-areas/{id}")
def remove_high_demand_area(request):
    admin = request.require("admin")
    row = request.connection.execute("SELECT * FROM high_demand_areas WHERE id = ?", (request.params["id"],)).fetchone()
    if row is None:
        raise ApiError(404, "This area is not in the list.")
    request.connection.execute("DELETE FROM high_demand_areas WHERE id = ?", (row["id"],))
    audit(request.connection, admin["id"], "high_demand_area_removed", "high_demand_area", row["id"], row["area_name"], None)
    return {"status": "removed"}


@router.route("GET", "/api/admin/verification-requests")
def admin_requests(request):
    request.require("admin")
    status = request.query.get("status")
    where, params = "", []
    if status:
        if status not in ("pending", "in_review", "document_verified", "issue_found"):
            raise ApiError(400, "Unknown status filter.")
        where, params = " WHERE vr.status = ?", [status]
    rows = request.connection.execute(
        REQUEST_SELECT + where + " ORDER BY vr.submitted_at DESC, vr.id DESC", params
    ).fetchall()
    return {"requests": [request_summary_json(row) for row in rows]}


@router.route("GET", "/api/admin/audit-log")
def admin_audit_log(request):
    request.require("admin")
    where, params = [], []
    target_type = request.query.get("targetType")
    if target_type:
        where.append("a.target_type = ?")
        params.append(target_type)
    target_id = int_param(request, "targetId", "Target ID", 1, 10**12)
    if target_id is not None:
        where.append("a.target_id = ?")
        params.append(target_id)
    limit = int_param(request, "limit", "Limit", 1, 1000) or 300
    sql = AUDIT_SELECT + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY a.id DESC LIMIT ?"
    rows = request.connection.execute(sql, (*params, limit)).fetchall()
    return {"entries": [audit_json(row) for row in rows]}


# Sprint 3 routes register themselves on the router above. Imported last because consult.py uses the helpers here.
from . import consult, photos, profile, sprint4, sprint5  # noqa: E402, F401
