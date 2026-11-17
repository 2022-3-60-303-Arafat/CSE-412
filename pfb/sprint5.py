"""Sprint 5 API (PB-34 to PB-43).

- Site visits (PB-34): a tenant books a one-hour slot to see a home; the owner confirms or declines.
- Phone confirmation (PB-35): an owner confirms their mobile number with a one-time code before publishing.
- Map and "near me" search (PB-37): listing positions and landmarks (the search itself is in api.py).
- Compare (PB-38), duplicate-listing flags (PB-39), the area price guide (PB-40),
  advocate reviews (PB-41) and monthly rent payments with reminders (PB-43).
bKash / Nagad payment (PB-36) is part of the consultation payment in consult.py.
"""

import hashlib
import hmac
import re
import secrets
import sqlite3
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher

from . import consult
from .api import PROPERTY_SELECT, USER_SELECT, fetch_property, property_json, router, user_json
from .db import audit, notify, utc_now
from .places import LANDMARKS, LATITUDE_RANGE, LONGITUDE_RANGE, default_location
from .sprint4 import agreement_role, bangladesh_today, load_agreement
from .validation import PHONE_PATTERN, Checker, normalize_phone
from .web import ApiError, Response

# ================================================================ site visits (PB-34)

VISIT_HOURS = range(10, 18)        # one-hour slots from 10 am to 6 pm, every day (Friday too: people visit on weekends)
VISIT_DAYS = 14
VISIT_SELECT = """
SELECT v.*, p.title AS property_title, p.area_name, p.city, p.address, p.listing_status,
       t.full_name AS tenant_name, t.phone AS tenant_phone, o.full_name AS owner_name, o.phone AS owner_phone
FROM site_visits v
JOIN properties p ON p.id = v.property_id
JOIN users t ON t.id = v.tenant_id
JOIN users o ON o.id = v.owner_id
"""
OPEN_VISIT = ("requested", "confirmed")


def visit_json(row, user):
    confirmed = row["status"] == "confirmed"
    data = {
        "id": row["id"],
        "slotStart": row["slot_start"],
        "note": row["note"],
        "status": row["status"],
        "ownerReply": row["owner_reply"],
        "createdAt": row["created_at"],
        "respondedAt": row["responded_at"],
        "isPast": row["slot_start"] <= consult.bangladesh_now().strftime("%Y-%m-%dT%H:%M"),
        "property": {"id": row["property_id"], "title": row["property_title"], "areaName": row["area_name"], "city": row["city"],
                     # The exact address is shared once the owner confirms the visit.
                     "address": row["address"] if confirmed else None},
        "tenant": {"id": row["tenant_id"], "name": row["tenant_name"]},
        "owner": {"id": row["owner_id"], "name": row["owner_name"]},
        "role": "tenant" if user["id"] == row["tenant_id"] else "owner",
    }
    if confirmed:
        # Both sides can call each other once the visit is agreed.
        data["tenant"]["phone"] = row["tenant_phone"]
        data["owner"]["phone"] = row["owner_phone"]
    return data


def free_visit_slots(connection, property_id):
    taken = {row[0] for row in connection.execute(
        "SELECT slot_start FROM site_visits WHERE property_id = ? AND status IN ('requested', 'confirmed')", (property_id,))}
    today = consult.bangladesh_now().date()
    return [
        slot
        for offset in range(1, VISIT_DAYS + 1)
        for hour in VISIT_HOURS
        if (slot := f"{(today + timedelta(days=offset)).isoformat()}T{hour:02d}:00") not in taken
    ]


def visitable_listing(request):
    row = fetch_property(request.connection, request.params["id"])
    if row is None or row["listing_status"] != "active":
        raise ApiError(404, "This listing does not exist or has been removed.")
    return row


def open_visit(connection, property_id, tenant_id):
    return connection.execute(
        VISIT_SELECT + " WHERE v.property_id = ? AND v.tenant_id = ? AND v.status IN ('requested', 'confirmed')",
        (property_id, tenant_id),
    ).fetchone()


def load_visit(request, user):
    row = request.connection.execute(VISIT_SELECT + " WHERE v.id = ?", (request.params["id"],)).fetchone()
    if row is None:
        raise ApiError(404, "This visit does not exist.")
    if user["id"] not in (row["tenant_id"], row["owner_id"]):
        raise ApiError(403, "You do not have access to this visit.")
    return row


def reload_visit(connection, visit_id):
    return connection.execute(VISIT_SELECT + " WHERE v.id = ?", (visit_id,)).fetchone()


@router.route("GET", "/api/properties/{id}/visit-slots")
def visit_slots(request):
    user = request.require("buyer_tenant")
    listing = visitable_listing(request)
    mine = open_visit(request.connection, listing["id"], user["id"])
    return {"slots": free_visit_slots(request.connection, listing["id"]), "myVisit": visit_json(mine, user) if mine else None}


@router.route("POST", "/api/properties/{id}/visits")
def book_visit(request):
    user = request.require("buyer_tenant")
    listing = visitable_listing(request)
    connection = request.connection
    checker = Checker(request.json())
    slot = checker.text("slotStart", "Time slot", min_length=16, max_length=16)
    note = checker.text("note", "Note", max_length=300, required=False)
    checker.done()
    if open_visit(connection, listing["id"], user["id"]):
        raise ApiError(409, "You already have a visit booked for this home. Cancel it to choose another time.")
    taken = ApiError(409, "This time is not free any more. Please choose another one.", {"slotStart": "Choose a free time."})
    if slot not in free_visit_slots(connection, listing["id"]):
        raise taken
    try:
        visit_id = connection.execute(
            """INSERT INTO site_visits (property_id, tenant_id, owner_id, slot_start, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (listing["id"], user["id"], listing["owner_id"], slot, note or None, utc_now()),
        ).lastrowid
    except sqlite3.IntegrityError:
        raise taken from None   # two tenants took the same slot at the same moment
    notify(connection, listing["owner_id"], "site_visit", "New visit request",
           f"{user['full_name']} wants to see {listing['title']} on {consult.nice_time(slot)}.", "/visits")
    return Response(201, {"visit": visit_json(reload_visit(connection, visit_id), user)})


@router.route("GET", "/api/visits")
def list_visits(request):
    user = request.require("buyer_tenant", "owner")
    column = "v.tenant_id" if user["role"] == "buyer_tenant" else "v.owner_id"
    rows = request.connection.execute(
        VISIT_SELECT + f""" WHERE {column} = ?
        ORDER BY (v.status IN ('requested', 'confirmed')) DESC, v.slot_start, v.id""", (user["id"],)).fetchall()
    return {"visits": [visit_json(row, user) for row in rows]}


@router.route("POST", "/api/visits/{id}/respond")
def respond_to_visit(request):
    user = request.require("owner")
    row = load_visit(request, user)
    if row["owner_id"] != user["id"]:
        raise ApiError(403, "Only the owner of the home answers a visit request.")
    if row["status"] != "requested":
        raise ApiError(409, "This visit request has already been answered.")
    checker = Checker(request.json())
    decision = checker.choice("decision", "Decision", ("confirmed", "declined"))
    reply = checker.text("reply", "Reply", min_length=5, max_length=300, required=decision == "declined")
    checker.done()
    connection = request.connection
    connection.execute("UPDATE site_visits SET status = ?, owner_reply = ?, responded_at = ? WHERE id = ?",
                       (decision, reply or None, utc_now(), row["id"]))
    when = consult.nice_time(row["slot_start"])
    if decision == "confirmed":
        notify(connection, row["tenant_id"], "site_visit", "Your visit is confirmed",
               f"{user['full_name']} expects you at {row['property_title']} on {when}.", "/visits")
    else:
        notify(connection, row["tenant_id"], "site_visit", "Your visit request was declined",
               f"{row['property_title']} on {when}: {reply}", "/visits")
    return {"visit": visit_json(reload_visit(connection, row["id"]), user)}


@router.route("POST", "/api/visits/{id}/cancel")
def cancel_visit(request):
    user = request.require("buyer_tenant")
    row = load_visit(request, user)
    if row["status"] not in OPEN_VISIT or visit_json(row, user)["isPast"]:
        raise ApiError(409, "This visit can no longer be cancelled.")
    connection = request.connection
    connection.execute("UPDATE site_visits SET status = 'cancelled', responded_at = ? WHERE id = ?", (utc_now(), row["id"]))
    notify(connection, row["owner_id"], "site_visit", "A visit was cancelled",
           f"{user['full_name']} cancelled the visit to {row['property_title']} on {consult.nice_time(row['slot_start'])}.", "/visits")
    return {"visit": visit_json(reload_visit(connection, row["id"]), user)}


# ================================================================ phone confirmation (PB-35)

CODE_MINUTES = 10
CODE_TRIES = 5
RESEND_SECONDS = 60


def code_digest(user_id, code):
    return hashlib.sha256(f"{user_id}:{code}".encode()).hexdigest()


def masked_phone(phone):
    return phone[:3] + "*" * (len(phone) - 6) + phone[-3:]


def require_confirmed_phone(user):
    """PB-35: an owner publishes only after confirming their mobile number."""
    if user["role"] == "owner" and not user["phone_verified_at"]:
        raise ApiError(403, "Confirm your mobile number before you publish a listing.",
                       {"phoneVerification": "Confirm your mobile number first."})


@router.route("POST", "/api/phone/send-code")
def send_phone_code(request):
    user = request.require("owner")
    data = request.json()
    phone = normalize_phone(str(data.get("phone") or user["phone"]))
    if not PHONE_PATTERN.match(phone):
        raise ApiError(400, "Please fix the highlighted fields.", {"phone": "Enter a Bangladeshi mobile number such as 01712345678."})
    phone = phone[-11:]   # store as 01XXXXXXXXX, without +88
    if user["phone_verified_at"] and user["phone"] == phone:
        raise ApiError(409, "This mobile number is already confirmed.")
    connection = request.connection
    last = connection.execute("SELECT created_at FROM phone_verifications WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                              (user["id"],)).fetchone()
    now = datetime.now(timezone.utc)
    if last and now - datetime.fromisoformat(last[0]) < timedelta(seconds=RESEND_SECONDS):
        raise ApiError(429, "A code was sent less than a minute ago. Please wait a moment before asking again.")
    code = f"{secrets.randbelow(10**6):06d}"
    expires = (now + timedelta(minutes=CODE_MINUTES)).isoformat(timespec="seconds")
    connection.execute(
        "INSERT INTO phone_verifications (user_id, phone, code_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
        (user["id"], phone, code_digest(user["id"], code), now.isoformat(timespec="seconds"), expires),
    )
    result = {"phone": masked_phone(phone), "expiresAt": expires, "minutes": CODE_MINUTES}
    # No SMS gateway in the demo: the code is shown on screen. A real launch would send it by SMS instead.
    if request.config.demo_sms:
        result["demoCode"] = code
    return result


@router.route("POST", "/api/phone/verify")
def verify_phone_code(request):
    user = request.require("owner")
    code = re.sub(r"\s", "", str(request.json().get("code", "")))
    connection = request.connection
    row = connection.execute(
        "SELECT * FROM phone_verifications WHERE user_id = ? AND verified_at IS NULL ORDER BY id DESC LIMIT 1", (user["id"],)
    ).fetchone()
    if row is None:
        raise ApiError(400, "Ask for a code first.")
    if row["attempts"] >= CODE_TRIES:
        raise ApiError(429, "Too many wrong codes. Ask for a new code.")
    if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        raise ApiError(400, "This code has expired. Ask for a new one.", {"code": "The code has expired."})
    if not re.fullmatch(r"\d{6}", code) or not hmac.compare_digest(code_digest(user["id"], code), row["code_hash"]):
        connection.execute("UPDATE phone_verifications SET attempts = attempts + 1 WHERE id = ?", (row["id"],))
        connection.commit()   # keep the count; the error below rolls back nothing else
        left = CODE_TRIES - row["attempts"] - 1
        if left <= 0:
            raise ApiError(429, "Too many wrong codes. Ask for a new code.")
        raise ApiError(400, f"Wrong code. {left} {'try' if left == 1 else 'tries'} left.", {"code": "This code is not right."})
    now = utc_now()
    connection.execute("UPDATE phone_verifications SET verified_at = ? WHERE id = ?", (now, row["id"]))
    connection.execute("UPDATE users SET phone = ?, phone_verified_at = ? WHERE id = ?", (row["phone"], now, user["id"]))
    audit(connection, user["id"], "phone_verified", "user", user["id"], user["phone"], row["phone"])
    return {"user": user_json(connection.execute(USER_SELECT + " WHERE u.id = ?", (user["id"],)).fetchone())}


# ================================================================ map positions and landmarks (PB-37)

def clean_location(data):
    """An owner's map pin, if they placed one: (lat, lng) or None. Wrong values are refused."""
    lat, lng = data.get("latitude"), data.get("longitude")
    if lat in (None, "") and lng in (None, ""):
        return None
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        raise ApiError(400, "Please fix the highlighted fields.", {"latitude": "Place the pin on the map again."}) from None
    if not (LATITUDE_RANGE[0] <= lat <= LATITUDE_RANGE[1] and LONGITUDE_RANGE[0] <= lng <= LONGITUDE_RANGE[1]):
        raise ApiError(400, "Please fix the highlighted fields.", {"latitude": "The pin must be inside Bangladesh."})
    return round(lat, 6), round(lng, 6)


def save_location(connection, property_id, data, listing, old_row=None):
    """Use the owner's pin; otherwise keep the old position unless the place changed; otherwise the area centre."""
    pin = clean_location(data)
    if pin is None and old_row is not None and old_row["latitude"] is not None \
            and (old_row["area_name"], old_row["city"]) == (listing["areaName"], listing["city"]):
        return
    pin = pin or default_location(listing["areaName"], listing["city"])
    connection.execute("UPDATE properties SET latitude = ?, longitude = ? WHERE id = ?",
                       (pin[0] if pin else None, pin[1] if pin else None, property_id))


@router.route("GET", "/api/landmarks")
def list_landmarks(request):
    return {"landmarks": LANDMARKS, "radii": [1, 3, 5, 10]}


@router.route("GET", "/api/properties/map")
def map_pins(request):
    """Every listing that matches the search filters, as pins (no pages)."""
    from .api import search_conditions
    select, where, params, order, _filters, near = search_conditions(request)
    rows = request.connection.execute(select + " WHERE " + " AND ".join(where) + " ORDER BY " + order + " LIMIT 500",
                                      params).fetchall()
    pins = [
        {"id": row["id"], "title": row["title"], "lat": row["latitude"], "lng": row["longitude"], "amount": row["amount"],
         "listingType": row["listing_type"], "areaName": row["area_name"], "city": row["city"],
         "verified": row["verification_status"] == "document_verified",
         "distanceKm": round(row["distance_km"], 1) if row["distance_km"] is not None else None}
        for row in rows if row["latitude"] is not None
    ]
    return {"pins": pins, "near": near}


# ================================================================ compare (PB-38)

MAX_COMPARE = 3


@router.route("GET", "/api/compare")
def compare(request):
    raw = [part for part in (request.query.get("ids") or "").split(",") if part.strip()]
    if not raw or not all(part.strip().isdigit() for part in raw):
        raise ApiError(400, "Choose the listings to compare.")
    ids = list(dict.fromkeys(int(part) for part in raw))
    if len(ids) > MAX_COMPARE:
        raise ApiError(400, f"You can compare up to {MAX_COMPARE} listings at a time.")
    connection = request.connection
    found = {}
    for row in connection.execute(
            PROPERTY_SELECT + f" WHERE p.id IN ({','.join('?' * len(ids))}) AND p.listing_status = 'active'", ids):
        data = property_json(row, request.user)
        data["pricePerSqft"] = round(row["amount"] / row["size_sqft"]) if row["amount"] and row["size_sqft"] else None
        data["deposit"] = data["rent"]["securityDeposit"] if data["rent"] else None
        data["moveInCost"] = data["rent"]["moveInCost"] if data["rent"] else None
        found[row["id"]] = data
    listings = [found[i] for i in ids if i in found]

    def best(key, lowest=True):
        values = [(item[key], item["id"]) for item in listings if item.get(key) is not None]
        if len(values) < 2:
            return None
        target = (min if lowest else max)(value for value, _ in values)
        return [item_id for value, item_id in values if value == target]

    same_kind = len({item["listingType"] for item in listings}) == 1
    best_values = {
        # A sale price and a monthly rent cannot be compared with each other.
        "amount": best("amount") if same_kind else None,
        "pricePerSqft": best("pricePerSqft") if same_kind else None,
        "deposit": best("deposit"),
        "moveInCost": best("moveInCost"),
        "sizeSqft": best("sizeSqft", lowest=False),
        "bedrooms": best("bedrooms", lowest=False),
        "bathrooms": best("bathrooms", lowest=False),
    }
    return {"properties": listings, "missing": [i for i in ids if i not in found], "best": best_values, "sameKind": same_kind}


# ================================================================ duplicate and scam listings (PB-39)

TEXT_SIMILARITY = 0.85
MIN_TEXT_LENGTH = 60      # short descriptions ("Nice flat") are alike by chance, so they are not compared


def normalized_text(text):
    return " ".join(re.findall(r"[a-z0-9ঀ-৿]+", (text or "").lower()))


def add_flag(connection, property_id, matched_id, kind, similarity):
    cursor = connection.execute(
        """INSERT OR IGNORE INTO duplicate_flags (property_id, matched_property_id, kind, similarity, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (property_id, matched_id, kind, similarity, utc_now()),
    )
    if cursor.rowcount:
        title = connection.execute("SELECT title FROM properties WHERE id = ?", (property_id,)).fetchone()[0]
        what = "uses the same photo as" if kind == "photo" else f"has text {similarity}% the same as"
        other = connection.execute("SELECT title FROM properties WHERE id = ?", (matched_id,)).fetchone()[0]
        for (admin_id,) in connection.execute("SELECT id FROM users WHERE role = 'admin' AND account_status = 'active'").fetchall():
            notify(connection, admin_id, "duplicate_flag", "Possible duplicate listing",
                   f"{title} {what} {other}.", "/admin?tab=duplicates")


def check_duplicate_photo(connection, listing, file_hash):
    """A photo already used on another owner's listing is flagged; reusing your own photos is fine."""
    for (matched_id,) in connection.execute(
        """SELECT DISTINCT i.property_id FROM property_images i JOIN properties p ON p.id = i.property_id
           WHERE i.file_hash = ? AND i.property_id != ? AND p.owner_id != ? AND p.listing_status != 'removed'""",
        (file_hash, listing["id"], listing["owner_id"]),
    ).fetchall():
        add_flag(connection, listing["id"], matched_id, "photo", 100)


def check_duplicate_text(connection, property_id):
    row = connection.execute("SELECT id, owner_id, description FROM properties WHERE id = ?", (property_id,)).fetchone()
    text = normalized_text(row["description"])
    if len(text) < MIN_TEXT_LENGTH:
        return
    for other in connection.execute(
        "SELECT id, description FROM properties WHERE owner_id != ? AND listing_status != 'removed' AND id != ?",
        (row["owner_id"], property_id),
    ).fetchall():
        other_text = normalized_text(other["description"])
        if len(other_text) < MIN_TEXT_LENGTH:
            continue
        matcher = SequenceMatcher(None, text, other_text, autojunk=False)
        if matcher.real_quick_ratio() < TEXT_SIMILARITY or matcher.quick_ratio() < TEXT_SIMILARITY:
            continue
        ratio = matcher.ratio()
        if ratio >= TEXT_SIMILARITY:
            add_flag(connection, property_id, other["id"], "text", int(ratio * 100))


FLAG_SELECT = """
SELECT f.*, a.title AS title_a, a.area_name AS area_a, a.city AS city_a, a.listing_status AS status_a, a.created_at AS created_a,
       ua.full_name AS owner_a, b.title AS title_b, b.area_name AS area_b, b.city AS city_b, b.listing_status AS status_b,
       b.created_at AS created_b, ub.full_name AS owner_b, r.full_name AS resolver_name
FROM duplicate_flags f
JOIN properties a ON a.id = f.property_id JOIN users ua ON ua.id = a.owner_id
JOIN properties b ON b.id = f.matched_property_id JOIN users ub ON ub.id = b.owner_id
LEFT JOIN users r ON r.id = f.resolved_by
"""


def flag_json(row):
    def listing(prefix, property_id):
        return {"id": property_id, "title": row[f"title_{prefix}"], "areaName": row[f"area_{prefix}"], "city": row[f"city_{prefix}"],
                "owner": row[f"owner_{prefix}"], "listingStatus": row[f"status_{prefix}"], "createdAt": row[f"created_{prefix}"]}
    return {
        "id": row["id"], "kind": row["kind"], "similarity": row["similarity"], "status": row["status"],
        "createdAt": row["created_at"], "resolvedAt": row["resolved_at"], "resolvedBy": row["resolver_name"],
        "listing": listing("a", row["property_id"]), "matchedListing": listing("b", row["matched_property_id"]),
    }


@router.route("GET", "/api/admin/duplicate-flags")
def admin_duplicate_flags(request):
    request.require("admin")
    status = request.query.get("status", "open")
    if status not in ("open", "dismissed", "removed", "all"):
        raise ApiError(400, "Choose open, dismissed, removed or all.")
    where = "" if status == "all" else " WHERE f.status = ?"
    rows = request.connection.execute(FLAG_SELECT + where + " ORDER BY f.id DESC", () if status == "all" else (status,)).fetchall()
    return {"flags": [flag_json(row) for row in rows]}


@router.route("POST", "/api/admin/duplicate-flags/{id}/resolve")
def resolve_duplicate_flag(request):
    """Dismiss the flag, or remove the newer listing (the one that copied)."""
    user = request.require("admin")
    connection = request.connection
    row = connection.execute(FLAG_SELECT + " WHERE f.id = ?", (request.params["id"],)).fetchone()
    if row is None:
        raise ApiError(404, "This flag does not exist.")
    if row["status"] != "open":
        raise ApiError(409, "This flag has already been handled.")
    checker = Checker(request.json())
    action = checker.choice("action", "Action", ("dismiss", "remove"))
    checker.done()
    now = utc_now()
    status = "dismissed" if action == "dismiss" else "removed"
    connection.execute("UPDATE duplicate_flags SET status = ?, resolved_by = ?, resolved_at = ? WHERE id = ?",
                       (status, user["id"], now, row["id"]))
    if action == "remove" and row["status_a"] != "removed":
        listing = fetch_property(connection, row["property_id"])
        connection.execute("UPDATE properties SET listing_status = 'removed', updated_at = ? WHERE id = ?", (now, row["property_id"]))
        audit(connection, user["id"], "listing_status_changed", "property", row["property_id"], listing["listing_status"], "removed",
              f"Duplicate of listing #{row['matched_property_id']}")
        notify(connection, listing["owner_id"], "listing_report", "Your listing was removed",
               f"{listing['title']} was removed because it copies another listing.", "/owner/listings")
        # Other open flags on the removed listing are closed with it.
        connection.execute("""UPDATE duplicate_flags SET status = 'removed', resolved_by = ?, resolved_at = ?
                              WHERE property_id = ? AND status = 'open'""", (user["id"], now, row["property_id"]))
    return {"flag": flag_json(connection.execute(FLAG_SELECT + " WHERE f.id = ?", (row["id"],)).fetchone())}


# ================================================================ area price guide (PB-40)

MIN_GROUP = 3


def price_rows(connection, listing_type):
    return connection.execute(
        """SELECT p.id, p.city, p.area_name, p.bedrooms,
                  CASE WHEN p.listing_type = 'rent' THEN rd.monthly_rent ELSE p.price END AS amount
           FROM properties p LEFT JOIN rent_details rd ON rd.property_id = p.id
           WHERE p.listing_status = 'active' AND p.listing_type = ?""",
        (listing_type,),
    ).fetchall()


def summarize(amounts):
    return {"count": len(amounts), "average": round(sum(amounts) / len(amounts)), "lowest": min(amounts), "highest": max(amounts)}


def price_guide(connection, listing_type, city=None):
    by_area, by_district = {}, {}
    for row in price_rows(connection, listing_type):
        if row["amount"] is None or (city and row["city"] != city):
            continue
        by_area.setdefault((row["city"], row["area_name"].lower(), row["bedrooms"]), []).append((row["area_name"], row["amount"]))
        by_district.setdefault((row["city"], row["bedrooms"]), []).append(row["amount"])
    areas = [
        {"city": key[0], "area": values[0][0], "bedrooms": key[2], **summarize([amount for _, amount in values])}
        for key, values in sorted(by_area.items()) if len(values) >= MIN_GROUP
    ]
    districts = [
        {"city": key[0], "bedrooms": key[1], **summarize(values)}
        for key, values in sorted(by_district.items()) if len(values) >= MIN_GROUP
    ]
    return {"listingType": listing_type, "minimumListings": MIN_GROUP, "areas": areas, "districts": districts}


def price_position(connection, row):
    """How a listing's price compares with similar homes nearby: the same area if it has enough, else the district."""
    if row["amount"] is None:
        return None
    others = [r for r in price_rows(connection, row["listing_type"])
              if r["id"] != row["id"] and r["amount"] is not None and r["bedrooms"] == row["bedrooms"] and r["city"] == row["city"]]
    same_area = [r["amount"] for r in others if r["area_name"].lower() == row["area_name"].lower()]
    if len(same_area) >= MIN_GROUP:
        scope, place, amounts = "area", row["area_name"], same_area
    elif len(others) >= MIN_GROUP:
        scope, place, amounts = "district", row["city"], [r["amount"] for r in others]
    else:
        return None
    summary = summarize(amounts)
    return {"scope": scope, "place": place, "bedrooms": row["bedrooms"], **summary,
            "differencePercent": round((row["amount"] - summary["average"]) * 100 / summary["average"])}


@router.route("GET", "/api/price-guide")
def get_price_guide(request):
    checker = Checker(request.query)
    listing_type = checker.choice("listingType", "Listing type", ("rent", "sale"), required=False, default="rent")
    from .validation import CITIES
    city = checker.choice("city", "District", CITIES, required=False)
    checker.done("Please check the filters.")
    return price_guide(request.connection, listing_type, city)


# ================================================================ advocate reviews (PB-41)

@router.route("POST", "/api/consultations/{id}/review")
def review_advocate(request):
    user = request.require("buyer_tenant")
    row = consult.load_consultation(request, user)
    if row["client_id"] != user["id"]:
        raise ApiError(403, "Only the client of this consultation can rate it.")
    if row["kind"] != "paid" or row["status"] != "completed":
        raise ApiError(409, "You can rate an advocate after a completed consultation.")
    if row["review_rating"] is not None:
        raise ApiError(409, "You have already rated this consultation.")
    checker = Checker(request.json())
    rating = checker.integer("rating", "Rating", 1, 5)
    comment = checker.text("comment", "Comment", max_length=500, required=False)
    checker.done()
    connection = request.connection
    connection.execute(
        "INSERT INTO reviews (consultation_id, advocate_id, client_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (row["id"], row["advocate_id"], user["id"], rating, comment or None, utc_now()),
    )
    notify(connection, row["advocate_id"], "review", f"New {rating}-star review",
           f"{user['full_name']} rated your consultation.", f"/consultations/{row['id']}")
    return Response(201, consult.detail_json(connection, consult.reload(connection, row["id"])))


@router.route("GET", "/api/advocates/{id}/reviews")
def advocate_reviews(request):
    connection = request.connection
    advocate = connection.execute(consult.ADVOCATE_LIST_SQL + " AND u.id = ?", (request.params["id"],)).fetchone()
    if advocate is None:
        raise ApiError(404, "This advocate is not available.")
    rows = connection.execute(
        """SELECT r.*, u.full_name FROM reviews r JOIN users u ON u.id = r.client_id
           WHERE r.advocate_id = ? ORDER BY r.id DESC LIMIT 50""", (advocate["id"],)).fetchall()
    return {
        "advocate": consult.advocate_json(advocate),
        # Reviewers are shown by first name only.
        "reviews": [{"rating": r["rating"], "comment": r["comment"], "createdAt": r["created_at"],
                     "by": r["full_name"].split()[0]} for r in rows],
    }


# ================================================================ rent payments and reminders (PB-43)

REMIND_DAYS_BEFORE = 3


def month_offset(start, months):
    """The same day `months` later (the 31st becomes the last day of a shorter month)."""
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


def create_rent_schedule(connection, agreement):
    """Called when both sides have signed: one rent payment per month of the lease."""
    start = date.fromisoformat(agreement["start_date"])
    months = agreement["lease_months"] or 12
    for index in range(months):
        connection.execute(
            "INSERT OR IGNORE INTO rent_payments (agreement_id, due_date, amount) VALUES (?, ?, ?)",
            (agreement["id"], month_offset(start, index).isoformat(), agreement["monthly_rent"]),
        )
    notify(connection, agreement["tenant_id"], "rent", "Your rent schedule is ready",
           f"{months} monthly payments of {agreement['monthly_rent']:,} taka, the first on {start.strftime('%d %b %Y')}.",
           f"/agreements/{agreement['id']}")


def send_rent_reminders(connection, user):
    """Reminders are sent when someone involved opens the site, so no background job is needed."""
    if user["role"] not in ("buyer_tenant", "owner"):
        return
    today = bangladesh_today()
    rows = connection.execute(
        """SELECT rp.*, a.tenant_id, a.landlord_id, p.title FROM rent_payments rp
           JOIN rent_agreements a ON a.id = rp.agreement_id JOIN properties p ON p.id = a.property_id
           WHERE rp.status = 'due' AND a.status = 'signed' AND (a.tenant_id = ? OR a.landlord_id = ?)
             AND (rp.reminded_before = 0 OR rp.reminded_overdue = 0)""",
        (user["id"], user["id"]),
    ).fetchall()
    for row in rows:
        due = date.fromisoformat(row["due_date"])
        link = f"/agreements/{row['agreement_id']}"
        when = due.strftime("%d %b")
        if due < today and not row["reminded_overdue"]:
            notify(connection, row["tenant_id"], "rent", "Rent is overdue",
                   f"The rent of {row['amount']:,} taka for {row['title']} was due on {when}.", link)
            notify(connection, row["landlord_id"], "rent", "Rent not paid yet",
                   f"The rent for {row['title']} due on {when} is not marked as paid.", link)
            connection.execute("UPDATE rent_payments SET reminded_overdue = 1, reminded_before = 1 WHERE id = ?", (row["id"],))
        elif today <= due <= today + timedelta(days=REMIND_DAYS_BEFORE) and not row["reminded_before"]:
            notify(connection, row["tenant_id"], "rent", "Rent due soon",
                   f"The rent of {row['amount']:,} taka for {row['title']} is due on {when}.", link)
            connection.execute("UPDATE rent_payments SET reminded_before = 1 WHERE id = ?", (row["id"],))


def rent_payment_json(row, today):
    return {
        "id": row["id"], "dueDate": row["due_date"], "amount": row["amount"], "status": row["status"],
        "overdue": row["status"] == "due" and date.fromisoformat(row["due_date"]) < today,
        "note": row["paid_note"], "markedPaidAt": row["marked_paid_at"], "confirmedAt": row["confirmed_at"],
    }


@router.route("GET", "/api/agreements/{id}/payments")
def agreement_payments(request):
    user = request.require("owner", "buyer_tenant", "admin")
    row = load_agreement(request, user)
    role = agreement_role(user, row)
    if role not in ("landlord", "tenant", "admin"):
        raise ApiError(403, "Only the landlord, the tenant and admins see the rent payments.")
    connection = request.connection
    send_rent_reminders(connection, user)
    today = bangladesh_today()
    payments = [rent_payment_json(r, today) for r in connection.execute(
        "SELECT * FROM rent_payments WHERE agreement_id = ? ORDER BY due_date", (row["id"],))]
    return {
        "payments": payments,
        "role": role,
        "summary": {
            "total": len(payments),
            "confirmed": sum(p["status"] == "confirmed" for p in payments),
            "waitingForLandlord": sum(p["status"] == "marked_paid" for p in payments),
            "overdue": sum(p["overdue"] for p in payments),
            "nextDue": next((p["dueDate"] for p in payments if p["status"] == "due"), None),
        },
    }


def load_rent_payment(request, user):
    row = request.connection.execute(
        """SELECT rp.*, a.tenant_id, a.landlord_id, a.status AS agreement_status, p.title FROM rent_payments rp
           JOIN rent_agreements a ON a.id = rp.agreement_id JOIN properties p ON p.id = a.property_id WHERE rp.id = ?""",
        (request.params["id"],),
    ).fetchone()
    if row is None:
        raise ApiError(404, "This rent payment does not exist.")
    if user["id"] not in (row["tenant_id"], row["landlord_id"]):
        raise ApiError(403, "You do not have access to this rent payment.")
    return row


@router.route("POST", "/api/rent-payments/{id}/mark-paid")
def mark_rent_paid(request):
    user = request.require("buyer_tenant")
    row = load_rent_payment(request, user)
    if row["tenant_id"] != user["id"]:
        raise ApiError(403, "Only the tenant marks a month as paid.")
    if row["status"] != "due":
        raise ApiError(409, "This month is already marked as paid.")
    checker = Checker(request.json())
    note = checker.text("note", "Payment note", max_length=200, required=False)
    checker.done()
    connection = request.connection
    connection.execute("UPDATE rent_payments SET status = 'marked_paid', paid_note = ?, marked_paid_at = ? WHERE id = ?",
                       (note or None, utc_now(), row["id"]))
    notify(connection, row["landlord_id"], "rent", "Rent marked as paid",
           f"{user['full_name']} paid the rent for {row['title']} due on {row['due_date']}. Please confirm you received it.",
           f"/agreements/{row['agreement_id']}")
    return rent_payment_json(connection.execute("SELECT * FROM rent_payments WHERE id = ?", (row["id"],)).fetchone(),
                             bangladesh_today())


@router.route("POST", "/api/rent-payments/{id}/confirm")
def confirm_rent_paid(request):
    """The landlord confirms the money arrived (also for cash handed over without the tenant marking it)."""
    user = request.require("owner")
    row = load_rent_payment(request, user)
    if row["landlord_id"] != user["id"]:
        raise ApiError(403, "Only the landlord confirms a payment.")
    if row["status"] == "confirmed":
        raise ApiError(409, "This payment is already confirmed.")
    connection = request.connection
    connection.execute("UPDATE rent_payments SET status = 'confirmed', confirmed_at = ? WHERE id = ?", (utc_now(), row["id"]))
    notify(connection, row["tenant_id"], "rent", "Rent payment confirmed",
           f"{user['full_name']} confirmed your rent for {row['title']} due on {row['due_date']}.",
           f"/agreements/{row['agreement_id']}")
    return rent_payment_json(connection.execute("SELECT * FROM rent_payments WHERE id = ?", (row["id"],)).fetchone(),
                             bangladesh_today())
