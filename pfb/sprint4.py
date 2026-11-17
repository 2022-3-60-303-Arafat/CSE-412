"""Sprint 4 API: rent agreements (PB-26, PB-27), saved searches with alerts (PB-28),
the admin platform report (PB-29) and reports of fake listings (PB-30).

A rent agreement moves: draft (landlord fills it in) -> under_review (an advocate checks it)
-> approved -> signed (when both landlord and tenant have signed). An advocate can also send it
back to draft with notes. Nobody can sign before an advocate approves it.
"""

import json
import re
from datetime import date, datetime, timedelta

from .api import (
    BANGLADESH_TIME, PROPERTY_SELECT, SEARCH_FILTER_KEYS, fetch_property, is_staff, property_json, router,
)
from .db import PROPERTY_TYPES, audit, distance_km, notify, notify_advocates, utc_now
from .places import LANDMARKS_BY_ID
from .pdf import build_pdf
from .reports import bangladesh_date
from .validation import CITIES, Checker, check_email
from .web import ApiError, Response

MAX_SAVED_SEARCHES = 20
REPORT_REASONS = {
    "fake": "The listing looks fake",
    "wrong_details": "Wrong price, size or location",
    "already_gone": "Already sold or rented",
    "duplicate": "The same home is listed twice",
    "other": "Something else",
}
AGREEMENT_STATUSES = ("draft", "under_review", "approved", "signed")


def bangladesh_today():
    return datetime.now(BANGLADESH_TIME).date()


def add_months(start, months):
    """The last day of a lease that starts on `start` and runs for `months` months."""
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    days_in_month = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(start.day, days_in_month)) - timedelta(days=1)


# ================================================================ rent agreements (PB-26, PB-27)

AGREEMENT_SELECT = """
SELECT a.*, p.title, p.address, p.area_name, p.city, p.property_type, p.listing_type, p.listing_status,
       l.full_name AS landlord_name, l.phone AS landlord_phone, l.email AS landlord_email,
       t.full_name AS tenant_name, t.phone AS tenant_phone, t.email AS tenant_email,
       r.full_name AS reviewer_name, rd.min_lease_months
FROM rent_agreements a
JOIN properties p ON p.id = a.property_id
JOIN users l ON l.id = a.landlord_id
LEFT JOIN users t ON t.id = a.tenant_id
LEFT JOIN users r ON r.id = a.reviewer_id
LEFT JOIN rent_details rd ON rd.property_id = a.property_id
"""


def agreement_role(user, row):
    if user["id"] == row["landlord_id"]:
        return "landlord"
    if user["id"] == row["tenant_id"]:
        return "tenant"
    if user["role"] == "admin":
        return "admin"
    if user["role"] == "advocate" and is_staff(user) and (row["status"] != "draft" or row["reviewer_id"] == user["id"]):
        return "advocate"
    return None


def agreement_json(row, user):
    role = agreement_role(user, row)
    signed_by_me = (role == "landlord" and row["landlord_signed_at"]) or (role == "tenant" and row["tenant_signed_at"])
    return {
        "id": row["id"],
        "status": row["status"],
        "property": {"id": row["property_id"], "title": row["title"], "address": row["address"],
                     "areaName": row["area_name"], "city": row["city"], "propertyType": row["property_type"]},
        "landlord": {"id": row["landlord_id"], "name": row["landlord_name"], "phone": row["landlord_phone"]},
        "tenant": {"id": row["tenant_id"], "name": row["tenant_name"], "phone": row["tenant_phone"], "email": row["tenant_email"]},
        "reviewer": {"name": row["reviewer_name"]} if row["reviewer_id"] else None,
        "startDate": row["start_date"],
        "endDate": row["end_date"],
        "leaseMonths": row["lease_months"],
        "monthlyRent": row["monthly_rent"],
        "securityDeposit": row["security_deposit"],
        "utilitiesIncluded": bool(row["utilities_included"]),
        "specialTerms": row["special_terms"],
        "reviewNotes": row["review_notes"],
        "submittedAt": row["submitted_at"],
        "reviewedAt": row["reviewed_at"],
        "landlordSignedAt": row["landlord_signed_at"],
        "tenantSignedAt": row["tenant_signed_at"],
        "createdAt": row["created_at"],
        "myRole": role,
        "canEdit": role == "landlord" and row["status"] == "draft",
        "canReview": role == "advocate" and row["status"] == "under_review",
        "canSign": role in ("landlord", "tenant") and row["status"] == "approved" and not signed_by_me,
    }


def load_agreement(request, user):
    row = request.connection.execute(AGREEMENT_SELECT + " WHERE a.id = ?", (request.params["id"],)).fetchone()
    if row is None:
        raise ApiError(404, "This rent agreement does not exist.")
    if agreement_role(user, row) is None:
        raise ApiError(403, "You do not have access to this rent agreement.")
    return row


def reload_agreement(connection, agreement_id):
    return connection.execute(AGREEMENT_SELECT + " WHERE a.id = ?", (agreement_id,)).fetchone()


def clean_agreement(connection, data, listing):
    """Check the landlord's form. The rent, deposit and utilities come from the listing (PB-26)."""
    checker = Checker(data)
    check_email(checker, "tenantEmail")
    months = checker.integer("leaseMonths", "Lease length", 1, 60)
    checker.text("specialTerms", "Special terms", max_length=1000, required=False)
    today = bangladesh_today()
    start = None
    try:
        start = date.fromisoformat(str(data.get("startDate", "")))
    except ValueError:
        checker.fail("startDate", "Choose the date the tenant moves in.")
    else:
        if start < today - timedelta(days=30):
            checker.fail("startDate", "The start date cannot be more than 30 days ago.")
        elif start > today + timedelta(days=365):
            checker.fail("startDate", "The start date must be within the next year.")
    if months and listing["min_lease_months"] and months < listing["min_lease_months"]:
        checker.fail("leaseMonths", f"The minimum lease for this home is {listing['min_lease_months']} months.")
    cleaned = checker.done()
    tenant = connection.execute(
        "SELECT * FROM users WHERE email = ? AND role = 'buyer_tenant' AND account_status = 'active'", (cleaned["tenantEmail"],)
    ).fetchone()
    if tenant is None:
        raise ApiError(400, "Please fix the highlighted fields.",
                       {"tenantEmail": "No buyer/tenant account uses this email. Ask the tenant to sign up first."})
    end = add_months(start, months)
    return {
        "tenant_id": tenant["id"], "start_date": start.isoformat(), "end_date": end.isoformat(), "lease_months": months,
        "special_terms": cleaned["specialTerms"] or None, "monthly_rent": listing["monthly_rent"],
        "security_deposit": listing["security_deposit"], "utilities_included": int(bool(listing["utilities_included"])),
    }


def landlord_rent_listing(request, user, property_id):
    row = fetch_property(request.connection, property_id)
    if row is None or row["listing_status"] == "removed":
        raise ApiError(404, "This listing does not exist.")
    if row["owner_id"] != user["id"]:
        raise ApiError(403, "You can only make agreements for your own listings.")
    if row["listing_type"] != "rent" or row["monthly_rent"] is None:
        raise ApiError(409, "Rent agreements are for listings that are for rent.")
    return row


@router.route("POST", "/api/properties/{id}/agreements")
def create_agreement(request):
    """PB-26: the landlord picks the tenant and dates; everything else is filled from the listing."""
    user = request.require("owner")
    listing = landlord_rent_listing(request, user, request.params["id"])
    connection = request.connection
    values = clean_agreement(connection, request.json(), listing)
    agreement_id = connection.execute(
        """INSERT INTO rent_agreements (property_id, landlord_id, tenant_id, start_date, end_date, lease_months, monthly_rent,
               security_deposit, utilities_included, special_terms, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?)""",
        (listing["id"], user["id"], values["tenant_id"], values["start_date"], values["end_date"], values["lease_months"],
         values["monthly_rent"], values["security_deposit"], values["utilities_included"], values["special_terms"], utc_now()),
    ).lastrowid
    audit(connection, user["id"], "agreement_created", "rent_agreement", agreement_id, None, "draft", listing["title"])
    return Response(201, agreement_json(reload_agreement(connection, agreement_id), user))


@router.route("PUT", "/api/agreements/{id}")
def update_agreement(request):
    user = request.require("owner")
    row = load_agreement(request, user)
    if agreement_role(user, row) != "landlord" or row["status"] != "draft":
        raise ApiError(409, "Only a draft can be changed, by its landlord.")
    listing = landlord_rent_listing(request, user, row["property_id"])
    values = clean_agreement(request.connection, request.json(), listing)
    request.connection.execute(
        """UPDATE rent_agreements SET tenant_id = ?, start_date = ?, end_date = ?, lease_months = ?, monthly_rent = ?,
               security_deposit = ?, utilities_included = ?, special_terms = ? WHERE id = ?""",
        (values["tenant_id"], values["start_date"], values["end_date"], values["lease_months"], values["monthly_rent"],
         values["security_deposit"], values["utilities_included"], values["special_terms"], row["id"]),
    )
    return agreement_json(reload_agreement(request.connection, row["id"]), user)


@router.route("GET", "/api/agreements")
def list_agreements(request):
    user = request.require("owner", "buyer_tenant", "advocate", "admin")
    connection = request.connection
    if user["role"] == "owner":
        rows = connection.execute(AGREEMENT_SELECT + " WHERE a.landlord_id = ? ORDER BY a.id DESC", (user["id"],)).fetchall()
    elif user["role"] == "buyer_tenant":
        rows = connection.execute(AGREEMENT_SELECT + " WHERE a.tenant_id = ? ORDER BY a.id DESC", (user["id"],)).fetchall()
    elif user["role"] == "advocate":
        rows = connection.execute(
            AGREEMENT_SELECT + " WHERE a.status = 'under_review' OR a.reviewer_id = ? ORDER BY a.status != 'under_review', a.id DESC",
            (user["id"],),
        ).fetchall()
    else:
        rows = connection.execute(AGREEMENT_SELECT + " ORDER BY a.id DESC").fetchall()
    return {"agreements": [agreement_json(row, user) for row in rows]}


@router.route("GET", "/api/agreements/{id}")
def get_agreement(request):
    user = request.require()
    return agreement_json(load_agreement(request, user), user)


@router.route("POST", "/api/agreements/{id}/submit")
def submit_agreement(request):
    """PB-27: the landlord sends the draft to an advocate for review."""
    user = request.require("owner")
    row = load_agreement(request, user)
    if agreement_role(user, row) != "landlord" or row["status"] != "draft":
        raise ApiError(409, "Only a draft can be sent for review, by its landlord.")
    connection = request.connection
    connection.execute("UPDATE rent_agreements SET status = 'under_review', submitted_at = ? WHERE id = ?", (utc_now(), row["id"]))
    audit(connection, user["id"], "agreement_status_changed", "rent_agreement", row["id"], "draft", "under_review", row["title"])
    notify_advocates(connection, "agreement", "A rent agreement needs review",
                     f"{row['title']}: {row['landlord_name']} and {row['tenant_name']}.", f"/agreements/{row['id']}")
    notify(connection, row["tenant_id"], "agreement", "A rent agreement is being prepared for you",
           f"{row['landlord_name']} sent the agreement for {row['title']} to an advocate for review.", f"/agreements/{row['id']}")
    return agreement_json(reload_agreement(connection, row["id"]), user)


@router.route("POST", "/api/agreements/{id}/review")
def review_agreement(request):
    """PB-27: the advocate approves the agreement or sends it back with notes."""
    user = request.require("advocate")
    row = load_agreement(request, user)
    if row["status"] != "under_review":
        raise ApiError(409, "This agreement is not waiting for review.")
    checker = Checker(request.json())
    decision = checker.choice("decision", "Decision", ("approved", "changes_requested"))
    notes = checker.text("notes", "Notes", min_length=10, max_length=2000, required=decision == "changes_requested")
    checker.done()
    new_status = "approved" if decision == "approved" else "draft"
    connection = request.connection
    connection.execute(
        "UPDATE rent_agreements SET status = ?, reviewer_id = ?, reviewed_at = ?, review_notes = ? WHERE id = ?",
        (new_status, user["id"], utc_now(), notes or None, row["id"]),
    )
    audit(connection, user["id"], "agreement_status_changed", "rent_agreement", row["id"], "under_review", new_status, notes)
    link = f"/agreements/{row['id']}"
    if new_status == "approved":
        for party in (row["landlord_id"], row["tenant_id"]):
            notify(connection, party, "agreement", "Your rent agreement is approved",
                   f"{user['full_name']} approved the agreement for {row['title']}. It can now be signed.", link)
    else:
        notify(connection, row["landlord_id"], "agreement", "Changes needed in your rent agreement",
               f"{user['full_name']}: {notes[:120]}", link)
    return agreement_json(reload_agreement(connection, row["id"]), user)


def same_name(typed, real):
    return " ".join(str(typed).split()).casefold() == " ".join(real.split()).casefold()


@router.route("POST", "/api/agreements/{id}/sign")
def sign_agreement(request):
    """PB-27: signing is allowed only after an advocate approves the agreement."""
    user = request.require("owner", "buyer_tenant")
    row = load_agreement(request, user)
    role = agreement_role(user, row)
    if role not in ("landlord", "tenant"):
        raise ApiError(403, "Only the landlord and the tenant sign the agreement.")
    if row["status"] in ("draft", "under_review"):
        raise ApiError(409, "The agreement can be signed only after an advocate approves it.")
    column = f"{role}_signed_at"
    if row[column]:
        raise ApiError(409, "You have already signed this agreement.")
    data = request.json()
    if not same_name(data.get("signature", ""), user["full_name"]):
        raise ApiError(400, "Please fix the highlighted fields.",
                       {"signature": f"Type your full name exactly as on your account: {user['full_name']}"})
    connection = request.connection
    now = utc_now()
    connection.execute(f"UPDATE rent_agreements SET {column} = ? WHERE id = ?", (now, row["id"]))
    other_signed = row["tenant_signed_at"] if role == "landlord" else row["landlord_signed_at"]
    other_id = row["tenant_id"] if role == "landlord" else row["landlord_id"]
    link = f"/agreements/{row['id']}"
    if other_signed:
        connection.execute("UPDATE rent_agreements SET status = 'signed' WHERE id = ?", (row["id"],))
        from .sprint5 import create_rent_schedule   # PB-43: one rent payment per month once both have signed
        create_rent_schedule(connection, row)
        audit(connection, user["id"], "agreement_status_changed", "rent_agreement", row["id"], "approved", "signed", row["title"])
        notify(connection, other_id, "agreement", "The rent agreement is signed by both sides",
               f"{row['title']}: download the signed agreement.", link)
    else:
        audit(connection, user["id"], "agreement_signed", "rent_agreement", row["id"], None, role, row["title"])
        notify(connection, other_id, "agreement", "Please sign the rent agreement",
               f"{user['full_name']} signed the agreement for {row['title']}.", link)
    return agreement_json(reload_agreement(connection, row["id"]), user)


def agreement_pdf(row):
    taka = lambda amount: f"Tk {amount:,}"  # noqa: E731 - PDF fonts have no taka sign
    start, end = row["start_date"], row["end_date"]
    stage = {"draft": "DRAFT - not yet reviewed by an advocate", "under_review": "DRAFT - under review by an advocate",
             "approved": "Approved by an advocate - ready to sign", "signed": "Signed by both parties"}[row["status"]]

    def signature(name, signed_at):
        return f"Signed by {name} on {bangladesh_date(signed_at)} (signed online)" if signed_at else f"{name}: ______________________  Date: __________"

    clauses = [
        f"1. Term. The tenancy starts on {start} and ends on {end} ({row['lease_months']} months).",
        f"2. Rent. The tenant pays {taka(row['monthly_rent'])} each month, by the 10th day of the month. "
        "The landlord gives a written receipt for every payment.",
        f"3. Security deposit. The tenant pays a security deposit of {taka(row['security_deposit'])} before moving in. "
        "The landlord returns it within 30 days after the tenant leaves, less the cost of any damage beyond normal wear.",
        "4. Utilities. " + ("Electricity, water and gas bills are included in the rent."
                            if row["utilities_included"] else "The tenant pays the electricity, water and gas bills."),
        "5. Use. The tenant uses the premises as a home only, and does not sublet them without written permission.",
        "6. Care and repairs. The tenant keeps the premises clean and in good condition. The landlord carries out "
        "major repairs to the structure, roof, wiring and plumbing.",
        "7. Notice. Either party can end this agreement early by giving two months' written notice.",
        "8. Law. This agreement follows the Premises Rent Control Act, 1991 of Bangladesh.",
    ]
    if row["special_terms"]:
        clauses.append(f"9. Special terms. {row['special_terms']}")
    blocks = [
        ("title", "Rent agreement"),
        ("small", f"Property Finder Bangladesh  |  Agreement no. PFB-A{row['id']:05d}  |  {stage}"),
        ("rule", ""),
        ("heading", "Parties"),
        ("text", f"Landlord: {row['landlord_name']}, phone {row['landlord_phone']}"),
        ("text", f"Tenant: {row['tenant_name']}, phone {row['tenant_phone']}"),
        ("heading", "Premises"),
        ("text", f"{row['title']}, {row['address']} ({row['property_type']})"),
        ("heading", "Terms"),
    ]
    for clause in clauses:
        blocks += [("text", clause), ("gap", "")]
    blocks += [("heading", "Signatures"),
               ("text", signature(f"Landlord, {row['landlord_name']}", row["landlord_signed_at"])),
               ("text", signature(f"Tenant, {row['tenant_name']}", row["tenant_signed_at"]))]
    if row["reviewer_name"] and row["status"] in ("approved", "signed"):
        blocks.append(("text", f"Reviewed and approved by {row['reviewer_name']} on {bangladesh_date(row['reviewed_at'])}."))
    blocks += [("rule", ""), ("small",
                "This agreement was filled in from the listing on Property Finder Bangladesh. For it to be enforced in "
                "court, print it on non-judicial stamp paper of the required value and have it registered as the law requires.")]
    return build_pdf(blocks)


@router.route("GET", "/api/agreements/{id}/pdf")
def download_agreement(request):
    user = request.require()
    row = load_agreement(request, user)
    return Response(body=agreement_pdf(row), content_type="application/pdf",
                    headers=[("Content-Disposition", f'inline; filename="PFB-rent-agreement-{row["id"]}.pdf"')])


# ================================================================ saved searches and alerts (PB-28)

def clean_filters(raw):
    if not isinstance(raw, dict):
        raw = {}
    filters = {key: str(raw[key]).strip()[:60] for key in SEARCH_FILTER_KEYS if str(raw.get(key, "")).strip()}
    filters.pop("verified", None)  # alerts are only ever for verified homes
    if filters.get("purpose") not in (None, "sale", "rent"):
        filters.pop("purpose")
    checker = Checker(filters)
    checker.choice("type", "Property type", PROPERTY_TYPES, required=False)
    checker.choice("city", "District", CITIES, required=False)
    checker.choice("furnished", "Furnished", ("yes", "no"), required=False)
    # PB-37: a saved search can be near a landmark (never near a person's own location, which is not stored).
    if filters.get("near") and filters["near"] not in LANDMARKS_BY_ID:
        checker.fail("near", "Choose a place from the list.")
    checker.choice("radius", "Distance", ("1", "3", "5", "10"), required=False)
    if not filters.get("near"):
        filters.pop("radius", None)
    for key, label in (("minPrice", "Minimum price"), ("maxPrice", "Maximum price"), ("bedrooms", "Bedrooms")):
        checker.integer(key, label, 0, 10**12, required=False)
    checker.done("This search cannot be saved.")
    return filters


def matches(filters, row):
    """Does a listing (a PROPERTY_SELECT row) match saved search filters?"""
    if filters.get("purpose") and row["listing_type"] != filters["purpose"]:
        return False
    if filters.get("type") and row["property_type"] != filters["type"]:
        return False
    if filters.get("city") and row["city"] != filters["city"]:
        return False
    if filters.get("furnished") and bool(row["furnished"]) != (filters["furnished"] == "yes"):
        return False
    area = filters.get("area", "").casefold()
    if area and area not in f"{row['area_name']} {row['city']} {row['address']}".casefold():
        return False
    amount = row["amount"] or 0
    if filters.get("minPrice") and amount < int(filters["minPrice"]):
        return False
    if filters.get("maxPrice") and amount > int(filters["maxPrice"]):
        return False
    if filters.get("bedrooms") and row["bedrooms"] < int(filters["bedrooms"]):
        return False
    landmark = LANDMARKS_BY_ID.get(filters.get("near", ""))
    if landmark:
        distance = distance_km(row["latitude"], row["longitude"], landmark["lat"], landmark["lng"])
        if distance is None or distance > int(filters.get("radius") or 5):
            return False
    return True


def alert_saved_searches(connection, property_id):
    """Called when a listing becomes verified: tell everyone whose saved search it matches."""
    row = fetch_property(connection, property_id)
    if row is None or row["listing_status"] != "active":
        return 0
    told = set()
    for search in connection.execute(
        """SELECT s.* FROM saved_searches s JOIN users u ON u.id = s.user_id
           WHERE u.account_status = 'active' AND s.user_id != ? ORDER BY s.id""", (row["owner_id"],)
    ).fetchall():
        if search["user_id"] in told or not matches(json.loads(search["filters"]), row):
            continue
        told.add(search["user_id"])
        notify(connection, search["user_id"], "saved_search", "A new verified home matches your search",
               f"{row['title']} in {row['area_name']}, {row['city']}.", f"/property/{row['id']}")
    return len(told)


def saved_search_json(connection, row):
    filters = json.loads(row["filters"])
    verified = connection.execute(
        PROPERTY_SELECT + " WHERE p.listing_status = 'active' AND p.verification_status = 'document_verified'"
    ).fetchall()
    return {"id": row["id"], "filters": filters, "createdAt": row["created_at"],
            "verifiedMatches": sum(1 for listing in verified if matches(filters, listing))}


@router.route("GET", "/api/saved-searches")
def list_saved_searches(request):
    user = request.require("buyer_tenant")
    rows = request.connection.execute("SELECT * FROM saved_searches WHERE user_id = ? ORDER BY id DESC", (user["id"],)).fetchall()
    return {"savedSearches": [saved_search_json(request.connection, row) for row in rows]}


@router.route("POST", "/api/saved-searches")
def save_search(request):
    user = request.require("buyer_tenant")
    filters = clean_filters(request.json().get("filters"))
    connection = request.connection
    encoded = json.dumps(filters, sort_keys=True)
    existing = connection.execute("SELECT * FROM saved_searches WHERE user_id = ? AND filters = ?", (user["id"], encoded)).fetchone()
    if existing:
        return saved_search_json(connection, existing)
    count = connection.execute("SELECT COUNT(*) FROM saved_searches WHERE user_id = ?", (user["id"],)).fetchone()[0]
    if count >= MAX_SAVED_SEARCHES:
        raise ApiError(409, f"You can keep up to {MAX_SAVED_SEARCHES} saved searches. Delete one first.")
    search_id = connection.execute(
        "INSERT INTO saved_searches (user_id, filters, created_at) VALUES (?, ?, ?)", (user["id"], encoded, utc_now())
    ).lastrowid
    return Response(201, saved_search_json(connection, connection.execute("SELECT * FROM saved_searches WHERE id = ?", (search_id,)).fetchone()))


@router.route("DELETE", "/api/saved-searches/{id}")
def delete_saved_search(request):
    user = request.require("buyer_tenant")
    deleted = request.connection.execute(
        "DELETE FROM saved_searches WHERE id = ? AND user_id = ?", (request.params["id"], user["id"])
    ).rowcount
    if not deleted:
        raise ApiError(404, "This saved search does not exist.")
    return {"status": "deleted"}


# ================================================================ reports of fake listings (PB-30)

REPORT_SELECT = """
SELECT r.*, p.title, p.area_name, p.city, p.listing_status, p.owner_id, o.full_name AS owner_name,
       u.full_name AS reporter_name, u.role AS reporter_role, a.full_name AS resolver_name,
       (SELECT COUNT(*) FROM listing_reports x WHERE x.property_id = r.property_id AND x.status = 'open') AS open_for_listing
FROM listing_reports r
JOIN properties p ON p.id = r.property_id
JOIN users o ON o.id = p.owner_id
JOIN users u ON u.id = r.reporter_id
LEFT JOIN users a ON a.id = r.resolved_by
"""


def listing_report_json(row):
    return {
        "id": row["id"], "reason": row["reason"], "reasonLabel": REPORT_REASONS[row["reason"]], "details": row["details"],
        "status": row["status"], "adminNote": row["admin_note"], "createdAt": row["created_at"], "resolvedAt": row["resolved_at"],
        "property": {"id": row["property_id"], "title": row["title"], "areaName": row["area_name"], "city": row["city"],
                     "listingStatus": row["listing_status"], "ownerName": row["owner_name"]},
        "reporter": {"name": row["reporter_name"], "role": row["reporter_role"]},
        "resolvedBy": row["resolver_name"],
        "openForListing": row["open_for_listing"],
    }


@router.route("POST", "/api/properties/{id}/reports")
def report_listing(request):
    """PB-30: any signed-in user (except the owner and admins) can report a listing."""
    user = request.require("buyer_tenant", "owner", "advocate")
    connection = request.connection
    row = fetch_property(connection, request.params["id"])
    if row is None or row["listing_status"] != "active":
        raise ApiError(404, "This listing does not exist or has been removed.")
    if row["owner_id"] == user["id"]:
        raise ApiError(403, "You cannot report your own listing.")
    data = request.json()
    checker = Checker(data)
    reason = checker.choice("reason", "Reason", tuple(REPORT_REASONS))
    checker.text("details", "Details", min_length=10, max_length=1000, required=reason == "other")
    cleaned = checker.done()
    if connection.execute(
        "SELECT 1 FROM listing_reports WHERE property_id = ? AND reporter_id = ? AND status = 'open'", (row["id"], user["id"])
    ).fetchone():
        raise ApiError(409, "You have already reported this listing. The admin will look at it soon.")
    report_id = connection.execute(
        "INSERT INTO listing_reports (property_id, reporter_id, reason, details, created_at) VALUES (?, ?, ?, ?, ?)",
        (row["id"], user["id"], reason, cleaned["details"] or None, utc_now()),
    ).lastrowid
    audit(connection, user["id"], "listing_reported", "property", row["id"], None, reason, cleaned["details"] or REPORT_REASONS[reason])
    for (admin_id,) in connection.execute("SELECT id FROM users WHERE role = 'admin' AND account_status = 'active'").fetchall():
        notify(connection, admin_id, "listing_report", "A listing was reported",
               f"{row['title']}: {REPORT_REASONS[reason]}.", "/admin?tab=reports")
    return Response(201, {"id": report_id, "status": "open"})


@router.route("GET", "/api/admin/listing-reports")
def admin_listing_reports(request):
    request.require("admin")
    status = request.query.get("status", "open")
    where = " WHERE r.status = ?" if status in ("open", "dismissed", "removed") else ""
    rows = request.connection.execute(REPORT_SELECT + where + " ORDER BY r.id DESC LIMIT 200", (status,) if where else ()).fetchall()
    return {"reports": [listing_report_json(row) for row in rows]}


@router.route("POST", "/api/admin/listing-reports/{id}/resolve")
def resolve_listing_report(request):
    """PB-30: the admin dismisses a report, or removes the listing (it then leaves the search results)."""
    admin = request.require("admin")
    connection = request.connection
    row = connection.execute(REPORT_SELECT + " WHERE r.id = ?", (request.params["id"],)).fetchone()
    if row is None:
        raise ApiError(404, "This report does not exist.")
    if row["status"] != "open":
        raise ApiError(409, "This report has already been handled.")
    checker = Checker(request.json())
    action = checker.choice("action", "Action", ("dismiss", "remove"))
    note = checker.text("note", "Note", min_length=5, max_length=500, required=action == "remove")
    checker.done()
    now = utc_now()
    if action == "dismiss":
        connection.execute("UPDATE listing_reports SET status = 'dismissed', resolved_by = ?, resolved_at = ?, admin_note = ? WHERE id = ?",
                           (admin["id"], now, note or None, row["id"]))
        audit(connection, admin["id"], "listing_report_dismissed", "property", row["property_id"], "open", "dismissed", note)
        notify(connection, row["reporter_id"], "listing_report", "Your report was reviewed",
               f"The admin checked {row['title']} and kept it online.{(' ' + note) if note else ''}", f"/property/{row['property_id']}")
        return listing_report_json(connection.execute(REPORT_SELECT + " WHERE r.id = ?", (row["id"],)).fetchone())

    reporters = [r[0] for r in connection.execute(
        "SELECT DISTINCT reporter_id FROM listing_reports WHERE property_id = ? AND status = 'open'", (row["property_id"],))]
    connection.execute("""UPDATE listing_reports SET status = 'removed', resolved_by = ?, resolved_at = ?, admin_note = ?
                          WHERE property_id = ? AND status = 'open'""", (admin["id"], now, note, row["property_id"]))
    if row["listing_status"] != "removed":
        connection.execute("UPDATE properties SET listing_status = 'removed', updated_at = ? WHERE id = ?", (now, row["property_id"]))
        audit(connection, admin["id"], "listing_status_changed", "property", row["property_id"], row["listing_status"], "removed",
              f"Removed after a report: {note}")
    notify(connection, row["owner_id"], "listing_report", "Your listing was removed",
           f"The admin removed {row['title']}: {note}", "/owner/listings")
    for reporter_id in reporters:
        notify(connection, reporter_id, "listing_report", "A listing you reported was removed",
               f"{row['title']} is no longer shown. Thank you for reporting it.", "/")
    return listing_report_json(connection.execute(REPORT_SELECT + " WHERE r.id = ?", (row["id"],)).fetchone())


# ================================================================ admin platform report (PB-29)

@router.route("GET", "/api/admin/report")
def admin_report(request):
    from .sprint5 import price_guide   # sprint5 is loaded after this module
    request.require("admin")
    c = request.connection
    one = lambda sql, *args: c.execute(sql, args).fetchone()[0]  # noqa: E731

    listings = {}
    for kind in ("sale", "rent"):
        for status in ("document_verified", "unverified", "issue_found"):
            listings[f"{kind}_{status}"] = one(
                "SELECT COUNT(*) FROM properties WHERE listing_status = 'active' AND listing_type = ? AND verification_status = ?",
                kind, status)
    by_type = {
        kind: {"verified": listings[f"{kind}_document_verified"],
               "unverified": listings[f"{kind}_unverified"] + listings[f"{kind}_issue_found"],
               "issueFound": listings[f"{kind}_issue_found"]}
        for kind in ("sale", "rent")
    }
    verified = by_type["sale"]["verified"] + by_type["rent"]["verified"]
    unverified = by_type["sale"]["unverified"] + by_type["rent"]["unverified"]
    oldest = c.execute("SELECT MIN(submitted_at) FROM verification_requests WHERE status = 'pending' AND advocate_id IS NULL").fetchone()[0]
    advocates = c.execute(
        """SELECT u.id, u.full_name, u.account_status,
                  (SELECT COUNT(*) FROM verification_requests v WHERE v.advocate_id = u.id AND v.status = 'in_review') AS in_review,
                  (SELECT COUNT(*) FROM verification_requests v WHERE v.advocate_id = u.id
                     AND v.status IN ('document_verified', 'issue_found')) AS decided,
                  (SELECT COUNT(*) FROM consultations x WHERE x.advocate_id = u.id AND x.status = 'requested') AS consult_requests,
                  (SELECT COUNT(*) FROM consultations x LEFT JOIN payments pay ON pay.consultation_id = x.id AND pay.status = 'paid'
                     WHERE x.advocate_id = u.id AND x.status = 'confirmed' AND x.kind = 'paid' AND pay.id IS NOT NULL) AS sessions_booked
           FROM users u JOIN advocate_profiles ap ON ap.user_id = u.id
           WHERE u.role = 'advocate' AND u.account_status != 'removed' AND ap.verification_status = 'verified'
           ORDER BY u.full_name"""
    ).fetchall()
    return {
        "generatedAt": utc_now(),
        "listings": {
            "active": verified + unverified, "verified": verified, "unverified": unverified,
            "issueFound": by_type["sale"]["issueFound"] + by_type["rent"]["issueFound"],
            "sale": by_type["sale"]["verified"] + by_type["sale"]["unverified"],
            "rent": by_type["rent"]["verified"] + by_type["rent"]["unverified"],
            "byType": by_type,
            "removed": one("SELECT COUNT(*) FROM properties WHERE listing_status = 'removed'"),
            "soldOrRented": one("SELECT COUNT(*) FROM properties WHERE listing_status = 'sold_rented'"),
            "badgeLevels": {level: one("""SELECT COUNT(*) FROM properties WHERE listing_status = 'active'
                                          AND verification_status = 'document_verified' AND badge_level = ?""", level)
                            for level in ("document_verified", "site_visited", "fully_verified")},
        },
        "verification": {
            "waitingForAdvocate": one("""SELECT COUNT(*) FROM verification_requests WHERE status = 'pending' AND advocate_id IS NULL
                                         AND (SELECT COUNT(DISTINCT d.document_type) FROM legal_documents d WHERE d.request_id = verification_requests.id
                                              AND d.is_current = 1 AND d.document_type IN ('land_deed', 'mutation', 'tax_receipt')) >= 3"""),
            "waitingForPapers": one("""SELECT COUNT(*) FROM verification_requests WHERE status = 'pending'
                                       AND (SELECT COUNT(DISTINCT d.document_type) FROM legal_documents d WHERE d.request_id = verification_requests.id
                                            AND d.is_current = 1 AND d.document_type IN ('land_deed', 'mutation', 'tax_receipt')) < 3"""),
            "inReview": one("SELECT COUNT(*) FROM verification_requests WHERE status = 'in_review'"),
            "issueFound": one("SELECT COUNT(*) FROM verification_requests WHERE status = 'issue_found'"),
            "verified": one("SELECT COUNT(*) FROM verification_requests WHERE status = 'document_verified'"),
            "oldestWaitingSince": oldest,
        },
        "advocates": [
            {"id": row["id"], "name": row["full_name"], "accountStatus": row["account_status"], "inReview": row["in_review"],
             "decided": row["decided"], "consultationRequests": row["consult_requests"], "sessionsBooked": row["sessions_booked"]}
            for row in advocates
        ],
        "agreementsToReview": one("SELECT COUNT(*) FROM rent_agreements WHERE status = 'under_review'"),
        "agreements": {status: one("SELECT COUNT(*) FROM rent_agreements WHERE status = ?", status) for status in AGREEMENT_STATUSES},
        "consultations": {
            "freeQuestions": one("SELECT COUNT(*) FROM consultations WHERE kind = 'free_chat'"),
            "paidBookings": one("SELECT COUNT(DISTINCT consultation_id) FROM payments WHERE status = 'paid'"),
            "feesCollected": one("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid'"),
        },
        "listingReports": {status: one("SELECT COUNT(*) FROM listing_reports WHERE status = ?", status)
                           for status in ("open", "dismissed", "removed")},
        # Sprint 5: automatic duplicate flags (PB-39) and the district price guide (PB-40).
        "duplicateFlags": {status: one("SELECT COUNT(*) FROM duplicate_flags WHERE status = ?", status)
                           for status in ("open", "dismissed", "removed")},
        "priceGuide": {kind: price_guide(c, kind)["districts"] for kind in ("rent", "sale")},
        "siteVisits": {status: one("SELECT COUNT(*) FROM site_visits WHERE status = ?", status)
                       for status in ("requested", "confirmed", "declined", "cancelled")},
    }
