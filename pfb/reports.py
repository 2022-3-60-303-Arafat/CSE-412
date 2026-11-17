"""Plain-language legal reports for verified properties (PB-18) and badge levels (PB-19)."""

import json
from datetime import datetime, timedelta, timezone

from .db import CHECKLIST_ITEMS, utc_now
from .pdf import build_pdf

# Badge levels a verified listing can have, lowest first.
BADGE_LEVELS = ("document_verified", "site_visited", "fully_verified")
BADGE_LABELS = {
    "document_verified": "Document Verified",
    "site_visited": "Site Visited",
    "fully_verified": "Fully Verified",
}
BADGE_MEANING = {
    "document_verified": "The advocate checked the legal papers of this property.",
    "site_visited": "The advocate checked the legal papers and visited the property in person.",
    "fully_verified": "The advocate checked the legal papers, visited the property and confirmed "
                      "the records with the land office.",
}
PAPER_LABELS = {
    "land_deed": "Land deed",
    "mutation": "Mutation paper (namjari)",
    "tax_receipt": "Land development tax receipt",
    "ownership_history": "Ownership history",
}
PAPER_MEANING = {
    "land_deed": "The deed is registered and names the current owner.",
    "mutation": "The mutation record matches the deed and the plot.",
    "tax_receipt": "The land development tax is paid and up to date.",
    "ownership_history": "The chain of earlier owners is clear, with no gap or dispute found.",
}
DISCLAIMER = (
    "This report is a summary of a document check done for Property Finder Bangladesh. It is based only on the "
    "papers the owner uploaded and on the checks named above, on the date shown. It is not a legal opinion, a "
    "guarantee of title or a replacement for your own lawyer. Before you pay any money, have the original papers "
    "checked and confirm the records at the land office."
)

REPORT_SELECT = """
SELECT r.*, vr.property_id, vr.completed_at, p.title, p.address, p.area_name, p.city, p.property_type, p.listing_type,
       o.full_name AS owner_name, a.full_name AS advocate_name, ap.bar_council_id
FROM verification_reports r
JOIN verification_requests vr ON vr.id = r.request_id
JOIN properties p ON p.id = vr.property_id
JOIN users o ON o.id = vr.owner_id
LEFT JOIN users a ON a.id = vr.advocate_id
LEFT JOIN advocate_profiles ap ON ap.user_id = vr.advocate_id
"""


BANGLADESH_TIME = timezone(timedelta(hours=6))


def bangladesh_date(stamp):
    """A stored UTC time stamp as the date in Bangladesh, for example '2026-11-17'."""
    return datetime.fromisoformat(stamp).astimezone(BANGLADESH_TIME).date().isoformat()


def summary_for(level, checklist):
    checked = ", ".join(PAPER_LABELS[item].lower() for item in CHECKLIST_ITEMS if checklist.get(item) == "ok")
    return f"{BADGE_MEANING[level]} Papers found in order: {checked}."


def ensure_report(connection, request_id):
    """Create the report for a verified request if it does not exist yet. Returns the report id, or None."""
    existing = connection.execute("SELECT id FROM verification_reports WHERE request_id = ?", (request_id,)).fetchone()
    if existing:
        return existing[0]
    request = connection.execute(
        """SELECT vr.status, vr.checklist, vr.completed_at, p.badge_level FROM verification_requests vr
           JOIN properties p ON p.id = vr.property_id WHERE vr.id = ?""",
        (request_id,),
    ).fetchone()
    if request is None or request["status"] != "document_verified" or not request["checklist"]:
        return None
    level = request["badge_level"] if request["badge_level"] in BADGE_LEVELS else "document_verified"
    checklist = json.loads(request["checklist"])
    cursor = connection.execute(
        """INSERT INTO verification_reports (request_id, badge_level, checklist_result, summary_text, disclaimer_text, issued_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (request_id, level, json.dumps(checklist), summary_for(level, checklist), DISCLAIMER,
         request["completed_at"] or utc_now()),
    )
    return cursor.lastrowid


def set_report_level(connection, request_id, level):
    report_id = ensure_report(connection, request_id)
    if report_id is None:
        return
    checklist = json.loads(connection.execute(
        "SELECT checklist_result FROM verification_reports WHERE id = ?", (report_id,)).fetchone()[0])
    connection.execute(
        "UPDATE verification_reports SET badge_level = ?, summary_text = ? WHERE id = ?",
        (level, summary_for(level, checklist), report_id),
    )


def current_report(connection, property_id):
    """The report of the verification that the listing's Verified badge comes from."""
    request = connection.execute(
        """SELECT vr.id FROM verification_requests vr JOIN properties p ON p.id = vr.property_id
           WHERE vr.property_id = ? AND vr.status = 'document_verified' AND p.verification_status = 'document_verified'
           ORDER BY vr.id DESC LIMIT 1""",
        (property_id,),
    ).fetchone()
    if request is None:
        return None
    report_id = ensure_report(connection, request["id"])
    if report_id is None:
        return None
    return connection.execute(REPORT_SELECT + " WHERE r.id = ?", (report_id,)).fetchone()


def report_pdf(report):
    checklist = json.loads(report["checklist_result"])
    issued = bangladesh_date(report["issued_at"])
    blocks = [
        ("title", "Property legal report"),
        ("small", f"Property Finder Bangladesh  |  Report no. PFB-R{report['id']:05d}  |  Issued {issued}"),
        ("rule", ""),
        ("heading", "Property"),
        ("bold", report["title"]),
        ("text", report["address"]),
        ("text", f"{report['property_type']}, for {report['listing_type']}  |  Listed by {report['owner_name']}"),
        ("heading", f"Result: {BADGE_LABELS[report['badge_level']]}"),
        ("text", report["summary_text"]),
        ("heading", "What was checked"),
    ]
    for item in CHECKLIST_ITEMS:
        result = {"ok": "In order", "problem": "Problem found"}.get(checklist.get(item), "Not checked")
        blocks.append(("bold", f"{PAPER_LABELS[item]}: {result}"))
        blocks.append(("text", PAPER_MEANING[item]))
        blocks.append(("gap", ""))
    blocks += [
        ("heading", "Checked by"),
        ("text", f"{report['advocate_name'] or 'Advocate on the PFB panel'}"
                 + (f"  |  Bar Council ID {report['bar_council_id']}" if report["bar_council_id"] else "")),
        ("text", f"Date of the check: {bangladesh_date(report['completed_at'] or report['issued_at'])}"),
        ("heading", "What the badge levels mean"),
    ]
    for level in BADGE_LEVELS:
        blocks.append(("text", f"{BADGE_LABELS[level]}: {BADGE_MEANING[level]}"))
    blocks += [("rule", ""), ("heading", "Disclaimer"), ("small", report["disclaimer_text"])]
    return build_pdf(blocks)
