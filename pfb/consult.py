"""Sprint 3 API: Ask an Advocate (PB-20), chat (PB-21), paid consultations (PB-22 to PB-24)
and in-app notifications (PB-25).

A consultation is either a free chat about one property or a paid booking for a time slot.
A paid booking moves: requested -> confirmed by the advocate -> paid by the client (booked)
-> completed with follow-up notes. It can also be refused by the advocate or cancelled by the client.
"""

import re
import secrets
import sqlite3
from datetime import datetime, timedelta

from .api import BANGLADESH_TIME, DEFAULT_CONSULTATION_FEE, fetch_property, router
from .db import notify, utc_now
from .validation import PHONE_PATTERN, Checker, normalize_phone
from .web import ApiError, Response

# Slots an advocate offers: every day except Friday, for the next week (Bangladesh time).
SLOT_HOURS = (10, 11, 12, 15, 16, 17)
SLOT_DAYS = 7
PAYMENT_METHODS = {"bkash": "bKash", "nagad": "Nagad", "card": "Card"}
# Demo payments: no real money moves. An account number that ends in this is declined.
DECLINED_ENDING = "0000"
MESSAGE_LIMIT = 1000

CONSULT_SELECT = """
SELECT c.*, p.title AS property_title, p.area_name, p.city,
       cl.full_name AS client_name, cl.phone AS client_phone,
       ad.full_name AS advocate_name, ap.specialization,
       pay.transaction_ref, pay.paid_at, pay.method AS paid_method, pay.amount AS paid_amount,
       (SELECT COUNT(*) FROM chat_messages m WHERE m.consultation_id = c.id) AS message_count,
       (SELECT MAX(m.sent_at) FROM chat_messages m WHERE m.consultation_id = c.id) AS last_message_at
FROM consultations c
JOIN users cl ON cl.id = c.client_id
JOIN users ad ON ad.id = c.advocate_id
LEFT JOIN advocate_profiles ap ON ap.user_id = c.advocate_id
LEFT JOIN properties p ON p.id = c.property_id
LEFT JOIN payments pay ON pay.consultation_id = c.id AND pay.status = 'paid'
"""

ADVOCATE_LIST_SQL = """
SELECT u.id, u.full_name, ap.specialization, ap.consultation_fee
FROM users u JOIN advocate_profiles ap ON ap.user_id = u.id
WHERE u.role = 'advocate' AND u.account_status = 'active' AND ap.verification_status = 'verified'
"""


# ---------------------------------------------------------------- helpers

def consult_state(row):
    """One word for where a consultation stands, used by the pages to pick labels and actions."""
    if row["kind"] == "free_chat":
        return "chat"
    if row["status"] == "requested":
        return "awaiting_advocate"
    if row["status"] == "confirmed":
        return "booked" if row["transaction_ref"] else "awaiting_payment"
    return row["status"]  # refused, completed, cancelled


def consult_json(row):
    data = {
        "id": row["id"],
        "kind": row["kind"],
        "state": consult_state(row),
        "slotStart": row["slot_start"],
        "fee": row["fee"],
        "followUpNotes": row["follow_up_notes"],
        "createdAt": row["created_at"],
        "property": {"id": row["property_id"], "title": row["property_title"], "areaName": row["area_name"], "city": row["city"]}
                    if row["property_id"] else None,
        "client": {"id": row["client_id"], "name": row["client_name"]},
        "advocate": {"id": row["advocate_id"], "name": row["advocate_name"], "specialization": row["specialization"]},
        "messageCount": row["message_count"],
        "lastMessageAt": row["last_message_at"],
        "receipt": None,
    }
    if row["transaction_ref"]:
        data["receipt"] = {
            "transactionRef": row["transaction_ref"],
            "amount": row["paid_amount"],
            "method": PAYMENT_METHODS.get(row["paid_method"], row["paid_method"]),
            "paidAt": row["paid_at"],
        }
    return data


def detail_json(connection, row):
    data = consult_json(row)
    data["messages"] = [
        {"id": message["id"], "senderId": message["sender_id"], "senderName": message["full_name"],
         "body": message["body"], "sentAt": message["sent_at"]}
        for message in connection.execute(
            """SELECT m.*, u.full_name FROM chat_messages m JOIN users u ON u.id = m.sender_id
               WHERE m.consultation_id = ? ORDER BY m.id""",
            (row["id"],),
        )
    ]
    return data


def load_consultation(request, user):
    """Load a consultation the signed-in user takes part in."""
    row = request.connection.execute(CONSULT_SELECT + " WHERE c.id = ?", (request.params["id"],)).fetchone()
    if row is None:
        raise ApiError(404, "This consultation does not exist.")
    if user["id"] not in (row["client_id"], row["advocate_id"]):
        raise ApiError(403, "You do not have access to this consultation.")
    return row


def reload(connection, consultation_id):
    return connection.execute(CONSULT_SELECT + " WHERE c.id = ?", (consultation_id,)).fetchone()


def verified_listing(request, property_id=None):
    """PB-20: advocates are asked about listings that carry the Verified badge."""
    row = fetch_property(request.connection, property_id if property_id is not None else request.params["id"])
    if row is None or row["listing_status"] != "active":
        raise ApiError(404, "This listing does not exist or has been removed.")
    if row["verification_status"] != "document_verified":
        raise ApiError(409, "You can ask an advocate about verified listings only.")
    return row


def pick_advocate(connection, property_id):
    """The advocate who verified the listing answers questions about it; otherwise the least busy one."""
    verifier = connection.execute(
        ADVOCATE_LIST_SQL + """ AND u.id = (SELECT advocate_id FROM verification_requests
            WHERE property_id = ? AND status = 'document_verified' ORDER BY id DESC LIMIT 1)""",
        (property_id,),
    ).fetchone()
    if verifier:
        return verifier
    advocate = connection.execute(
        ADVOCATE_LIST_SQL + """ ORDER BY (SELECT COUNT(*) FROM consultations c WHERE c.advocate_id = u.id
            AND c.kind = 'free_chat'), u.id LIMIT 1"""
    ).fetchone()
    if advocate is None:
        raise ApiError(409, "No advocate is available right now. Please try again later.")
    return advocate


def nice_time(slot):
    """'2026-11-18T10:00' as 'Wed 18 Nov at 10:00 am', for messages people read."""
    when = datetime.strptime(slot, "%Y-%m-%dT%H:%M")
    hour = when.strftime("%I:%M %p").lstrip("0").lower()
    return f"{when.strftime('%a')} {when.day} {when.strftime('%b')} at {hour}"


def bangladesh_now():
    return datetime.now(BANGLADESH_TIME).replace(tzinfo=None)


def free_slots(connection, advocate_id):
    taken = {
        row[0] for row in connection.execute(
            """SELECT slot_start FROM consultations WHERE advocate_id = ? AND slot_start IS NOT NULL
               AND status IN ('requested', 'confirmed')""",
            (advocate_id,),
        )
    }
    today = bangladesh_now().date()
    slots = []
    for offset in range(1, SLOT_DAYS + 1):
        day = today + timedelta(days=offset)
        if day.weekday() == 4:  # Friday
            continue
        for hour in SLOT_HOURS:
            slot = f"{day.isoformat()}T{hour:02d}:00"
            if slot not in taken:
                slots.append(slot)
    return slots


def advocate_json(row):
    return {"id": row["id"], "name": row["full_name"], "specialization": row["specialization"],
            "fee": row["consultation_fee"] or DEFAULT_CONSULTATION_FEE}


def add_message(connection, consultation, sender, body):
    connection.execute(
        "INSERT INTO chat_messages (consultation_id, sender_id, body, sent_at) VALUES (?, ?, ?, ?)",
        (consultation["id"], sender["id"], body, utc_now()),
    )
    to_advocate = sender["id"] == consultation["client_id"]
    notify(
        connection,
        consultation["advocate_id"] if to_advocate else consultation["client_id"],
        "chat_message",
        f"New question from {sender['full_name']}" if to_advocate else f"{sender['full_name']} replied to your question",
        body[:120],
        f"/consultations/{consultation['id']}",
    )


def message_body(request):
    checker = Checker(request.json())
    checker.text("body", "Message", min_length=2, max_length=MESSAGE_LIMIT)
    return checker.done()["body"]


# ---------------------------------------------------------------- advocates and slots (PB-20, PB-22)

@router.route("GET", "/api/advocates")
def list_public_advocates(request):
    request.require("buyer_tenant")
    rows = request.connection.execute(ADVOCATE_LIST_SQL + " ORDER BY u.full_name").fetchall()
    return {"advocates": [advocate_json(row) for row in rows]}


@router.route("GET", "/api/advocates/{id}/slots")
def advocate_slots(request):
    request.require("buyer_tenant")
    advocate = request.connection.execute(ADVOCATE_LIST_SQL + " AND u.id = ?", (request.params["id"],)).fetchone()
    if advocate is None:
        raise ApiError(404, "This advocate is not available.")
    return {"advocate": advocate_json(advocate), "slots": free_slots(request.connection, advocate["id"])}


# ---------------------------------------------------------------- free chat (PB-21)

@router.route("GET", "/api/properties/{id}/chat")
def property_chat(request):
    """The buyer's chat about one listing. The history stays with the listing."""
    user = request.require("buyer_tenant")
    listing = verified_listing(request)
    connection = request.connection
    existing = connection.execute(
        "SELECT id FROM consultations WHERE property_id = ? AND client_id = ? AND kind = 'free_chat'",
        (listing["id"], user["id"]),
    ).fetchone()
    advocate = pick_advocate(connection, listing["id"])
    return {
        "consultation": detail_json(connection, reload(connection, existing["id"])) if existing else None,
        "advocate": advocate_json(advocate),
    }


@router.route("POST", "/api/properties/{id}/chat")
def ask_free_question(request):
    user = request.require("buyer_tenant")
    listing = verified_listing(request)
    body = message_body(request)
    connection = request.connection
    existing = connection.execute(
        "SELECT id FROM consultations WHERE property_id = ? AND client_id = ? AND kind = 'free_chat'",
        (listing["id"], user["id"]),
    ).fetchone()
    if existing:
        consultation_id = existing["id"]
    else:
        advocate = pick_advocate(connection, listing["id"])
        consultation_id = connection.execute(
            """INSERT INTO consultations (property_id, client_id, advocate_id, kind, fee, status, created_at)
               VALUES (?, ?, ?, 'free_chat', 0, 'confirmed', ?)""",
            (listing["id"], user["id"], advocate["id"], utc_now()),
        ).lastrowid
    add_message(connection, reload(connection, consultation_id), user, body)
    return Response(201, detail_json(connection, reload(connection, consultation_id)))


@router.route("POST", "/api/consultations/{id}/messages")
def send_message(request):
    user = request.require("buyer_tenant", "advocate")
    row = load_consultation(request, user)
    if row["kind"] != "free_chat":
        raise ApiError(409, "Messages can only be sent in a free question chat.")
    add_message(request.connection, row, user, message_body(request))
    return Response(201, detail_json(request.connection, reload(request.connection, row["id"])))


# ---------------------------------------------------------------- paid consultations (PB-22, PB-23, PB-24)

@router.route("GET", "/api/consultations")
def list_consultations(request):
    user = request.require("buyer_tenant", "advocate")
    column = "c.client_id" if user["role"] == "buyer_tenant" else "c.advocate_id"
    rows = request.connection.execute(CONSULT_SELECT + f" WHERE {column} = ? ORDER BY c.id DESC", (user["id"],)).fetchall()
    return {"consultations": [consult_json(row) for row in rows]}


@router.route("GET", "/api/consultations/{id}")
def get_consultation(request):
    user = request.require("buyer_tenant", "advocate")
    return detail_json(request.connection, load_consultation(request, user))


@router.route("POST", "/api/consultations")
def book_consultation(request):
    """PB-22: the buyer picks an advocate and a free slot. The slot is held from this moment."""
    user = request.require("buyer_tenant")
    connection = request.connection
    data = request.json()
    checker = Checker(data)
    property_id = checker.integer("propertyId", "Listing", 1, 10**9)
    advocate_id = checker.integer("advocateId", "Advocate", 1, 10**9)
    slot = checker.text("slotStart", "Time slot", min_length=16, max_length=16)
    checker.done()

    listing = verified_listing(request, property_id)
    advocate = connection.execute(ADVOCATE_LIST_SQL + " AND u.id = ?", (advocate_id,)).fetchone()
    if advocate is None:
        raise ApiError(404, "This advocate is not available.")
    taken = ApiError(409, "This time slot is not free any more. Please choose another one.", {"slotStart": "Choose a free time slot."})
    if slot not in free_slots(connection, advocate["id"]):
        raise taken
    fee = advocate["consultation_fee"] or DEFAULT_CONSULTATION_FEE
    try:
        consultation_id = connection.execute(
            """INSERT INTO consultations (property_id, client_id, advocate_id, kind, slot_start, fee, status, created_at)
               VALUES (?, ?, ?, 'paid', ?, ?, 'requested', ?)""",
            (listing["id"], user["id"], advocate["id"], slot, fee, utc_now()),
        ).lastrowid
    except sqlite3.IntegrityError:
        # Two buyers asked for the same slot at the same moment; the database keeps only the first.
        raise taken from None
    notify(connection, advocate["id"], "consultation", "New consultation request",
           f"{user['full_name']} asked for {nice_time(slot)} about {listing['title']}.",
           f"/consultations/{consultation_id}")
    return Response(201, detail_json(connection, reload(connection, consultation_id)))


@router.route("POST", "/api/consultations/{id}/respond")
def respond_to_request(request):
    """PB-23: the advocate confirms or refuses a requested slot."""
    user = request.require("advocate")
    row = load_consultation(request, user)
    if row["kind"] != "paid" or row["status"] != "requested":
        raise ApiError(409, "This request has already been answered.")
    checker = Checker(request.json())
    decision = checker.choice("decision", "Decision", ("confirmed", "refused"))
    reason = checker.text("reason", "Reason", min_length=5, max_length=500, required=decision == "refused")
    checker.done()
    connection = request.connection
    connection.execute("UPDATE consultations SET status = ?, follow_up_notes = ? WHERE id = ?", (decision, reason or None, row["id"]))
    when = nice_time(row["slot_start"])
    if decision == "confirmed":
        notify(connection, row["client_id"], "consultation", "Your consultation was accepted",
               f"{user['full_name']} accepted {when}. Pay the fee of {row['fee']} taka to confirm the booking.",
               f"/consultations/{row['id']}")
    else:
        notify(connection, row["client_id"], "consultation", "Your consultation request was refused",
               f"{user['full_name']} cannot take {when}: {reason}", f"/consultations/{row['id']}")
    return detail_json(connection, reload(connection, row["id"]))


@router.route("POST", "/api/consultations/{id}/pay")
def pay_consultation(request):
    """PB-24: a demo payment. The booking is confirmed only after the payment succeeds."""
    user = request.require("buyer_tenant")
    row = load_consultation(request, user)
    if row["kind"] != "paid":
        raise ApiError(409, "A free question has no fee.")
    if row["transaction_ref"]:
        raise ApiError(409, "This consultation is already paid.")
    if row["status"] != "confirmed":
        raise ApiError(409, "You can pay after the advocate accepts your request.")
    data = request.json()
    checker = Checker(data)
    method = checker.choice("method", "Payment method", tuple(PAYMENT_METHODS))
    account = re.sub(r"[\s-]", "", str(data.get("account", "")))
    if method == "card":
        if not re.fullmatch(r"\d{16}", account):
            checker.fail("account", "Enter the 16-digit card number.")
    elif not PHONE_PATTERN.match(normalize_phone(account)):
        checker.fail("account", f"Enter the {PAYMENT_METHODS.get(method, 'wallet')} mobile number, such as 01712345678.")
    checker.done()

    connection = request.connection
    now = utc_now()
    if account.endswith(DECLINED_ENDING):
        connection.execute(
            "INSERT INTO payments (consultation_id, amount, method, status, created_at) VALUES (?, ?, ?, 'failed', ?)",
            (row["id"], row["fee"], method, now),
        )
        connection.commit()  # keep the failed attempt on record; the error below rolls nothing else back
        raise ApiError(402, f"Payment failed: {PAYMENT_METHODS[method]} declined this payment. "
                            "No money was taken. Check the number or try another method.")
    reference = "PFB-" + secrets.token_hex(5).upper()
    connection.execute(
        """INSERT INTO payments (consultation_id, amount, method, status, transaction_ref, created_at, paid_at)
           VALUES (?, ?, ?, 'paid', ?, ?, ?)""",
        (row["id"], row["fee"], method, reference, now, now),
    )
    notify(connection, row["advocate_id"], "consultation", "A consultation is booked and paid",
           f"{user['full_name']} paid for {nice_time(row['slot_start'])}.", f"/consultations/{row['id']}")
    return detail_json(connection, reload(connection, row["id"]))


@router.route("POST", "/api/consultations/{id}/complete")
def complete_consultation(request):
    """PB-23: after the session the advocate writes follow-up notes for the buyer."""
    user = request.require("advocate")
    row = load_consultation(request, user)
    if consult_state(row) != "booked":
        raise ApiError(409, "Follow-up notes can be added to a booked and paid consultation.")
    checker = Checker(request.json())
    notes = checker.text("notes", "Follow-up notes", min_length=10, max_length=2000)
    checker.done()
    connection = request.connection
    connection.execute("UPDATE consultations SET status = 'completed', follow_up_notes = ? WHERE id = ?", (notes, row["id"]))
    notify(connection, row["client_id"], "consultation", "Follow-up notes from your advocate",
           f"{user['full_name']} added notes after your consultation.", f"/consultations/{row['id']}")
    return detail_json(connection, reload(connection, row["id"]))


@router.route("POST", "/api/consultations/{id}/cancel")
def cancel_consultation(request):
    """The buyer can give the slot back until the fee is paid."""
    user = request.require("buyer_tenant")
    row = load_consultation(request, user)
    if consult_state(row) not in ("awaiting_advocate", "awaiting_payment"):
        raise ApiError(409, "This consultation can no longer be cancelled.")
    connection = request.connection
    connection.execute("UPDATE consultations SET status = 'cancelled' WHERE id = ?", (row["id"],))
    notify(connection, row["advocate_id"], "consultation", "A consultation request was cancelled",
           f"{user['full_name']} cancelled {nice_time(row['slot_start'])}.", f"/consultations/{row['id']}")
    return detail_json(connection, reload(connection, row["id"]))


# ---------------------------------------------------------------- notifications (PB-25)

@router.route("GET", "/api/notifications")
def list_notifications(request):
    user = request.require()
    connection = request.connection
    unread = connection.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (user["id"],)).fetchone()[0]
    if request.query.get("count") == "1":
        return {"unread": unread}
    rows = connection.execute("SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 60", (user["id"],)).fetchall()
    return {
        "unread": unread,
        "notifications": [
            {"id": row["id"], "kind": row["kind"], "title": row["title"], "body": row["body"], "link": row["link"],
             "isRead": bool(row["is_read"]), "createdAt": row["created_at"]}
            for row in rows
        ],
    }


@router.route("POST", "/api/notifications/read")
def mark_notifications_read(request):
    user = request.require()
    data = request.json()
    connection = request.connection
    if data.get("all") is True:
        connection.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user["id"],))
    else:
        checker = Checker(data)
        notification_id = checker.integer("id", "Notification", 1, 10**12)
        checker.done()
        connection.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", (notification_id, user["id"]))
    unread = connection.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (user["id"],)).fetchone()[0]
    return {"unread": unread}
