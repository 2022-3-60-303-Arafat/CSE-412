"""Database schema and connection helpers (PB-01).

Table names follow the classes on the CRC cards. Tables for Sprint 3 and 4
classes (consultations, chat, payments, reports, rent agreements) are created
now so later sprints only add features, not schema changes.
"""

import math
import sqlite3
from datetime import datetime, timezone

SCHEMA_VERSION = 8

ROLES = ("buyer_tenant", "owner", "advocate", "admin")
PROPERTY_TYPES = ("Apartment", "House", "Duplex", "Studio", "Plot", "Commercial")
DOCUMENT_TYPES = ("land_deed", "mutation", "tax_receipt", "ownership_history")
REQUIRED_DOCUMENT_TYPES = ("land_deed", "mutation", "tax_receipt")
CHECKLIST_ITEMS = DOCUMENT_TYPES
OPEN_REQUEST_STATUSES = ("pending", "in_review", "issue_found")

SCHEMA = """
CREATE TABLE users (
    id              INTEGER PRIMARY KEY,
    full_name       TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE COLLATE NOCASE,
    phone           TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('buyer_tenant', 'owner', 'advocate', 'admin')),
    account_status  TEXT NOT NULL DEFAULT 'active' CHECK (account_status IN ('active', 'blocked', 'removed')),
    created_at      TEXT NOT NULL
);

CREATE TABLE advocate_profiles (
    user_id           INTEGER PRIMARY KEY REFERENCES users(id),
    bar_council_id    TEXT NOT NULL UNIQUE COLLATE NOCASE,
    specialization    TEXT NOT NULL,
    consultation_fee  INTEGER NOT NULL DEFAULT 0 CHECK (consultation_fee >= 0),
    added_by          INTEGER REFERENCES users(id),
    added_at          TEXT NOT NULL
);

CREATE TABLE sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX sessions_user ON sessions(user_id);

CREATE TABLE properties (
    id                   INTEGER PRIMARY KEY,
    owner_id             INTEGER NOT NULL REFERENCES users(id),
    title                TEXT NOT NULL,
    description          TEXT NOT NULL,
    listing_type         TEXT NOT NULL CHECK (listing_type IN ('sale', 'rent')),
    property_type        TEXT NOT NULL CHECK (property_type IN ('Apartment', 'House', 'Duplex', 'Studio', 'Plot', 'Commercial')),
    -- Sale price. Rent listings keep their amount in rent_details.monthly_rent.
    price                INTEGER CHECK (price IS NULL OR price > 0),
    area_name            TEXT NOT NULL,
    city                 TEXT NOT NULL,
    address              TEXT NOT NULL,
    size_sqft            INTEGER NOT NULL CHECK (size_sqft > 0),
    bedrooms             INTEGER NOT NULL CHECK (bedrooms >= 0),
    bathrooms            INTEGER NOT NULL CHECK (bathrooms >= 0),
    furnished            INTEGER NOT NULL DEFAULT 0 CHECK (furnished IN (0, 1)),
    listing_status       TEXT NOT NULL DEFAULT 'active' CHECK (listing_status IN ('active', 'sold_rented', 'removed')),
    verification_status  TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status IN ('unverified', 'document_verified', 'issue_found')),
    badge_level          TEXT NOT NULL DEFAULT 'none' CHECK (badge_level IN ('none', 'document_verified', 'site_visited', 'fully_verified')),
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    CHECK (listing_type = 'rent' OR price IS NOT NULL)
);
CREATE INDEX properties_search ON properties(listing_status, listing_type, verification_status);
CREATE INDEX properties_owner ON properties(owner_id);

CREATE TABLE rent_details (
    property_id         INTEGER PRIMARY KEY REFERENCES properties(id) ON DELETE CASCADE,
    monthly_rent        INTEGER NOT NULL CHECK (monthly_rent > 0),
    security_deposit    INTEGER NOT NULL CHECK (security_deposit >= 0),
    available_from      TEXT NOT NULL,
    min_lease_months    INTEGER NOT NULL DEFAULT 12 CHECK (min_lease_months BETWEEN 1 AND 60),
    utilities_included  INTEGER NOT NULL DEFAULT 0 CHECK (utilities_included IN (0, 1)),
    tenant_preference   TEXT NOT NULL DEFAULT 'any' CHECK (tenant_preference IN ('family', 'bachelor', 'any'))
);

CREATE TABLE property_images (
    id           INTEGER PRIMARY KEY,
    property_id  INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    image_url    TEXT NOT NULL,
    caption      TEXT NOT NULL DEFAULT '',
    is_primary   INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    uploaded_at  TEXT NOT NULL
);
CREATE INDEX property_images_property ON property_images(property_id);

CREATE TABLE favorites (
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id  INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    saved_at     TEXT NOT NULL,
    PRIMARY KEY (user_id, property_id)
);

CREATE TABLE inquiries (
    id             INTEGER PRIMARY KEY,
    property_id    INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    sender_id      INTEGER NOT NULL REFERENCES users(id),
    sender_name    TEXT NOT NULL,
    sender_phone   TEXT NOT NULL,
    message        TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'replied', 'closed')),
    reply_message  TEXT,
    created_at     TEXT NOT NULL,
    replied_at     TEXT
);
CREATE INDEX inquiries_property ON inquiries(property_id);
CREATE INDEX inquiries_sender ON inquiries(sender_id);

CREATE TABLE verification_requests (
    id                  INTEGER PRIMARY KEY,
    property_id         INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    owner_id            INTEGER NOT NULL REFERENCES users(id),
    advocate_id         INTEGER REFERENCES users(id),
    status              TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_review', 'document_verified', 'issue_found')),
    submitted_at        TEXT NOT NULL,
    assigned_at         TEXT,
    completed_at        TEXT,
    advocate_notes      TEXT,
    checklist           TEXT,
    resubmission_count  INTEGER NOT NULL DEFAULT 0
);
-- A property can have only one open verification request at a time.
CREATE UNIQUE INDEX verification_requests_one_open
    ON verification_requests(property_id) WHERE status IN ('pending', 'in_review', 'issue_found');
CREATE INDEX verification_requests_queue ON verification_requests(status, advocate_id);

CREATE TABLE legal_documents (
    id             INTEGER PRIMARY KEY,
    request_id     INTEGER NOT NULL REFERENCES verification_requests(id) ON DELETE CASCADE,
    document_type  TEXT NOT NULL CHECK (document_type IN ('land_deed', 'mutation', 'tax_receipt', 'ownership_history')),
    file_name      TEXT NOT NULL,
    file_type      TEXT NOT NULL CHECK (file_type IN ('pdf', 'jpg', 'png')),
    file_size_kb   INTEGER NOT NULL,
    storage_name   TEXT NOT NULL UNIQUE,
    review_status  TEXT NOT NULL DEFAULT 'not_checked' CHECK (review_status IN ('not_checked', 'ok', 'problem')),
    -- Replaced papers are kept for the record but are no longer current.
    is_current     INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0, 1)),
    uploaded_by    INTEGER NOT NULL REFERENCES users(id),
    uploaded_at    TEXT NOT NULL
);
CREATE INDEX legal_documents_request ON legal_documents(request_id, is_current);

CREATE TABLE verification_reports (
    id               INTEGER PRIMARY KEY,
    request_id       INTEGER NOT NULL UNIQUE REFERENCES verification_requests(id) ON DELETE CASCADE,
    badge_level      TEXT NOT NULL CHECK (badge_level IN ('document_verified', 'site_visited', 'fully_verified')),
    checklist_result TEXT NOT NULL,
    summary_text     TEXT NOT NULL,
    disclaimer_text  TEXT NOT NULL,
    issued_at        TEXT NOT NULL,
    pdf_path         TEXT
);

CREATE TABLE high_demand_areas (
    id          INTEGER PRIMARY KEY,
    area_name   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    added_by    INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL
);

CREATE TABLE audit_log (
    id           INTEGER PRIMARY KEY,
    actor_id     INTEGER REFERENCES users(id),
    action_type  TEXT NOT NULL,
    target_type  TEXT NOT NULL,
    target_id    INTEGER NOT NULL,
    old_value    TEXT,
    new_value    TEXT,
    details      TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX audit_log_target ON audit_log(target_type, target_id);

-- PB-16: audit entries can never be edited or deleted.
CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'Audit log entries cannot be changed.'); END;
CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'Audit log entries cannot be deleted.'); END;

CREATE TABLE consultations (
    id               INTEGER PRIMARY KEY,
    property_id      INTEGER REFERENCES properties(id) ON DELETE SET NULL,
    client_id        INTEGER NOT NULL REFERENCES users(id),
    advocate_id      INTEGER NOT NULL REFERENCES users(id),
    kind             TEXT NOT NULL CHECK (kind IN ('free_chat', 'paid')),
    slot_start       TEXT,
    fee              INTEGER NOT NULL DEFAULT 0 CHECK (fee >= 0),
    status           TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested', 'confirmed', 'refused', 'completed', 'cancelled')),
    follow_up_notes  TEXT,
    created_at       TEXT NOT NULL
);
CREATE UNIQUE INDEX consultations_slot ON consultations(advocate_id, slot_start)
    WHERE slot_start IS NOT NULL AND status IN ('requested', 'confirmed');

CREATE TABLE chat_messages (
    id               INTEGER PRIMARY KEY,
    consultation_id  INTEGER NOT NULL REFERENCES consultations(id) ON DELETE CASCADE,
    sender_id        INTEGER NOT NULL REFERENCES users(id),
    body             TEXT NOT NULL,
    sent_at          TEXT NOT NULL
);

CREATE TABLE payments (
    id               INTEGER PRIMARY KEY,
    consultation_id  INTEGER NOT NULL REFERENCES consultations(id),
    amount           INTEGER NOT NULL CHECK (amount > 0),
    method           TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'failed')),
    transaction_ref  TEXT,
    created_at       TEXT NOT NULL,
    paid_at          TEXT
);

CREATE TABLE rent_agreements (
    id                INTEGER PRIMARY KEY,
    property_id       INTEGER NOT NULL REFERENCES properties(id),
    landlord_id       INTEGER NOT NULL REFERENCES users(id),
    tenant_id         INTEGER REFERENCES users(id),
    reviewer_id       INTEGER REFERENCES users(id),
    start_date        TEXT,
    end_date          TEXT,
    monthly_rent      INTEGER NOT NULL CHECK (monthly_rent > 0),
    security_deposit  INTEGER NOT NULL CHECK (security_deposit >= 0),
    status            TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'under_review', 'approved', 'signed')),
    created_at        TEXT NOT NULL
);
"""

# Version 2: browsing history (PROPERTY_VIEW in the ER diagram, plus search history).
# Guests are counted with user_id NULL. No IP address or browser details are stored.
HISTORY_SCHEMA = """
CREATE TABLE property_views (
    id           INTEGER PRIMARY KEY,
    property_id  INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    user_id      INTEGER REFERENCES users(id),
    source       TEXT NOT NULL DEFAULT 'direct' CHECK (source IN ('search', 'favorites', 'history', 'direct')),
    viewed_at    TEXT NOT NULL
);
CREATE INDEX property_views_property ON property_views(property_id, viewed_at);
CREATE INDEX property_views_user ON property_views(user_id, viewed_at);

CREATE TABLE search_history (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    filters       TEXT NOT NULL,
    result_count  INTEGER NOT NULL,
    searched_at   TEXT NOT NULL
);
CREATE INDEX search_history_user ON search_history(user_id, searched_at);
"""

# Version 3: advocates can apply for an account themselves. The admin sends an
# appointment, meets the advocate in person and then verifies or rejects them.
# Advocates added by the admin (and all older accounts) are 'verified' from the start.
ADVOCATE_VERIFICATION_SCHEMA = """
ALTER TABLE advocate_profiles ADD COLUMN verification_status TEXT NOT NULL DEFAULT 'verified'
    CHECK (verification_status IN ('pending', 'appointment_sent', 'verified', 'rejected'));
-- Appointment date and time as Bangladesh local time, 'YYYY-MM-DDTHH:MM'.
ALTER TABLE advocate_profiles ADD COLUMN appointment_at TEXT;
ALTER TABLE advocate_profiles ADD COLUMN appointment_place TEXT;
ALTER TABLE advocate_profiles ADD COLUMN admin_message TEXT;
ALTER TABLE advocate_profiles ADD COLUMN reviewed_by INTEGER REFERENCES users(id);
ALTER TABLE advocate_profiles ADD COLUMN reviewed_at TEXT;
"""

# Version 4 (Sprint 3): in-app notifications (PB-25) and a consultation fee for every advocate (PB-22).
SPRINT3_SCHEMA = """
CREATE TABLE notifications (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    -- Page to open, as a path inside the site, for example '/consultations/4'.
    link        TEXT,
    is_read     INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
    created_at  TEXT NOT NULL
);
CREATE INDEX notifications_user ON notifications(user_id, is_read, id);
UPDATE advocate_profiles SET consultation_fee = 500 WHERE consultation_fee = 0;
"""

# Version 5 (Sprint 4): rent agreement details (PB-26, PB-27), saved searches (PB-28), listing reports (PB-30).
SPRINT4_SCHEMA = """
ALTER TABLE rent_agreements ADD COLUMN lease_months INTEGER;
ALTER TABLE rent_agreements ADD COLUMN utilities_included INTEGER NOT NULL DEFAULT 0;
ALTER TABLE rent_agreements ADD COLUMN special_terms TEXT;
ALTER TABLE rent_agreements ADD COLUMN review_notes TEXT;
ALTER TABLE rent_agreements ADD COLUMN submitted_at TEXT;
ALTER TABLE rent_agreements ADD COLUMN reviewed_at TEXT;
ALTER TABLE rent_agreements ADD COLUMN landlord_signed_at TEXT;
ALTER TABLE rent_agreements ADD COLUMN tenant_signed_at TEXT;
CREATE INDEX rent_agreements_parties ON rent_agreements(landlord_id, tenant_id, status);

CREATE TABLE saved_searches (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filters     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE (user_id, filters)
);

CREATE TABLE listing_reports (
    id           INTEGER PRIMARY KEY,
    property_id  INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    reporter_id  INTEGER NOT NULL REFERENCES users(id),
    reason       TEXT NOT NULL CHECK (reason IN ('fake', 'wrong_details', 'already_gone', 'duplicate', 'other')),
    details      TEXT,
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'dismissed', 'removed')),
    admin_note   TEXT,
    resolved_by  INTEGER REFERENCES users(id),
    resolved_at  TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX listing_reports_status ON listing_reports(status, property_id);
"""

# Version 6: owners upload photos of their listings. A photo uploaded by an owner has a file_path
# (relative to the photo folder); the demo photos are links to a photo service and have none.
# A listing has at most one cover photo, which search cards show.
PHOTOS_SCHEMA = """
ALTER TABLE property_images RENAME COLUMN is_primary TO is_cover;
ALTER TABLE property_images ADD COLUMN file_path TEXT;
UPDATE property_images SET is_cover = 0
    WHERE is_cover = 1 AND id NOT IN (SELECT MIN(id) FROM property_images WHERE is_cover = 1 GROUP BY property_id);
CREATE UNIQUE INDEX property_images_one_cover ON property_images(property_id) WHERE is_cover = 1;
"""

# Version 7 (Sprint 5, PB-34 to PB-43): site visits, phone confirmation, wallet receipts, map positions,
# duplicate-listing flags, advocate reviews and monthly rent payments.
SPRINT5_SCHEMA = """
CREATE TABLE site_visits (
    id            INTEGER PRIMARY KEY,
    property_id   INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    tenant_id     INTEGER NOT NULL REFERENCES users(id),
    owner_id      INTEGER NOT NULL REFERENCES users(id),
    slot_start    TEXT NOT NULL,
    note          TEXT,
    status        TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested', 'confirmed', 'declined', 'cancelled')),
    owner_reply   TEXT,
    created_at    TEXT NOT NULL,
    responded_at  TEXT
);
-- A time slot of a listing can be held by one open visit only.
CREATE UNIQUE INDEX site_visits_slot ON site_visits(property_id, slot_start) WHERE status IN ('requested', 'confirmed');
CREATE INDEX site_visits_tenant ON site_visits(tenant_id, status);
CREATE INDEX site_visits_owner ON site_visits(owner_id, status);

ALTER TABLE users ADD COLUMN phone_verified_at TEXT;
-- Owners who already had listings before this step keep publishing.
UPDATE users SET phone_verified_at = created_at WHERE role = 'owner'
    AND EXISTS (SELECT 1 FROM properties p WHERE p.owner_id = users.id);
CREATE TABLE phone_verifications (
    id           INTEGER PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    phone        TEXT NOT NULL,
    code_hash    TEXT NOT NULL,
    attempts     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    verified_at  TEXT
);
CREATE INDEX phone_verifications_user ON phone_verifications(user_id, id);

ALTER TABLE payments ADD COLUMN account_masked TEXT;

ALTER TABLE properties ADD COLUMN latitude REAL;
ALTER TABLE properties ADD COLUMN longitude REAL;

ALTER TABLE property_images ADD COLUMN file_hash TEXT;
CREATE INDEX property_images_hash ON property_images(file_hash) WHERE file_hash IS NOT NULL;
CREATE TABLE duplicate_flags (
    id                   INTEGER PRIMARY KEY,
    property_id          INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    matched_property_id  INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    kind                 TEXT NOT NULL CHECK (kind IN ('photo', 'text')),
    similarity           INTEGER NOT NULL,
    status               TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'dismissed', 'removed')),
    resolved_by          INTEGER REFERENCES users(id),
    resolved_at          TEXT,
    created_at           TEXT NOT NULL,
    UNIQUE (property_id, matched_property_id, kind)
);
CREATE INDEX duplicate_flags_status ON duplicate_flags(status);

CREATE TABLE reviews (
    id               INTEGER PRIMARY KEY,
    consultation_id  INTEGER NOT NULL UNIQUE REFERENCES consultations(id) ON DELETE CASCADE,
    advocate_id      INTEGER NOT NULL REFERENCES users(id),
    client_id        INTEGER NOT NULL REFERENCES users(id),
    rating           INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment          TEXT,
    created_at       TEXT NOT NULL
);
CREATE INDEX reviews_advocate ON reviews(advocate_id);

CREATE TABLE rent_payments (
    id                INTEGER PRIMARY KEY,
    agreement_id      INTEGER NOT NULL REFERENCES rent_agreements(id) ON DELETE CASCADE,
    due_date          TEXT NOT NULL,
    amount            INTEGER NOT NULL CHECK (amount > 0),
    status            TEXT NOT NULL DEFAULT 'due' CHECK (status IN ('due', 'marked_paid', 'confirmed')),
    paid_note         TEXT,
    marked_paid_at    TEXT,
    confirmed_at      TEXT,
    reminded_before   INTEGER NOT NULL DEFAULT 0 CHECK (reminded_before IN (0, 1)),
    reminded_overdue  INTEGER NOT NULL DEFAULT 0 CHECK (reminded_overdue IN (0, 1)),
    UNIQUE (agreement_id, due_date)
);
"""

# Version 8: the profile page (profile picture, occupation and a short "about me").
PROFILE_SCHEMA = """
ALTER TABLE users ADD COLUMN avatar_path TEXT;
ALTER TABLE users ADD COLUMN occupation TEXT;
ALTER TABLE users ADD COLUMN bio TEXT;
"""

# Steps that bring an older database up to date, keyed by the version they start from.
MIGRATIONS = {1: HISTORY_SCHEMA, 2: ADVOCATE_VERIFICATION_SCHEMA, 3: SPRINT3_SCHEMA, 4: SPRINT4_SCHEMA, 5: PHOTOS_SCHEMA,
              6: SPRINT5_SCHEMA, 7: PROFILE_SCHEMA}

# Signed-in user rows carry advocate_status (NULL for every role except advocate).
USER_SELECT = """SELECT u.*, ap.verification_status AS advocate_status
                 FROM users u LEFT JOIN advocate_profiles ap ON ap.user_id = u.id"""


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def distance_km(lat1, lng1, lat2, lng2):
    """Straight-line distance in kilometres between two points (haversine). None if a point is missing."""
    if None in (lat1, lng1, lat2, lng2):
        return None
    lat1, lng1, lat2, lng2 = map(math.radians, (lat1, lng1, lat2, lng2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def connect(path):
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    # PB-37: SQL can filter and sort listings by distance to a place.
    connection.create_function("distance_km", 4, distance_km, deterministic=True)
    return connection


def initialize(path):
    """Create the schema if the database is new, or upgrade an older one.

    Returns True when a new database was created (so demo data should be loaded).
    """
    connection = connect(path)
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            return False
        if version == 0:
            # The default journal mode is used on purpose: WAL is not safe on the
            # network drives that hosting services such as PythonAnywhere use.
            connection.executescript(SCHEMA + HISTORY_SCHEMA + ADVOCATE_VERIFICATION_SCHEMA + SPRINT3_SCHEMA + SPRINT4_SCHEMA
                                     + PHOTOS_SCHEMA + SPRINT5_SCHEMA + PROFILE_SCHEMA)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.commit()
            return True
        if version not in MIGRATIONS:
            raise RuntimeError(
                f"Database schema version {version} is not supported. "
                "Run 'python server.py --reset' to rebuild the demo database."
            )
        while version < SCHEMA_VERSION:
            connection.executescript(MIGRATIONS[version])
            version += 1
            connection.execute(f"PRAGMA user_version = {version}")
            connection.commit()
        return False
    finally:
        connection.close()


def audit(connection, actor_id, action_type, target_type, target_id, old_value=None, new_value=None, details=None):
    """Append one entry to the audit log (PB-16)."""
    connection.execute(
        """INSERT INTO audit_log (actor_id, action_type, target_type, target_id, old_value, new_value, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (actor_id, action_type, target_type, target_id, old_value, new_value, details, utc_now()),
    )


def notify(connection, user_id, kind, title, body="", link=None):
    """Add one in-app notification for a user (PB-25)."""
    connection.execute(
        "INSERT INTO notifications (user_id, kind, title, body, link, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, kind, title, body, link, utc_now()),
    )


def notify_advocates(connection, kind, title, body="", link=None):
    """Notify every advocate who is active and verified."""
    for (advocate_id,) in connection.execute(
        """SELECT u.id FROM users u JOIN advocate_profiles ap ON ap.user_id = u.id
           WHERE u.role = 'advocate' AND u.account_status = 'active' AND ap.verification_status = 'verified'"""
    ).fetchall():
        notify(connection, advocate_id, kind, title, body, link)
