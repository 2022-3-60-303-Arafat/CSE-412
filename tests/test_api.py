"""Acceptance tests for the Sprint 1 and Sprint 2 stories (PB-01 to PB-17).

Run with:  python -m unittest discover -s tests -v
Each test starts from a fresh copy of the demo database.
Set PFB_TEST_WSGI=1 to run every test against the hosted (WSGI) version.
"""

import contextlib
import http.cookiejar
import json
import os
import socketserver
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402
from pfb import db  # noqa: E402
from pfb.api import router  # noqa: E402
from pfb.wsgi_app import make_wsgi_app  # noqa: E402
from pfb.seed import DEMO_PASSWORD, sample_pdf  # noqa: E402

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class Client:
    def __init__(self, base_url):
        self.base_url = base_url
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, payload=None, raw=None, content_type=None, csrf=True):
        headers = {}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if raw is not None:
            data = raw
            headers["Content-Type"] = content_type or "application/octet-stream"
        if csrf and method != "GET":
            headers["X-PFB-Request"] = "1"
        request = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(request) as response:
                body = response.read()
                status = response.status
                kind = response.headers.get_content_type()
        except urllib.error.HTTPError as error:
            body = error.read()
            status = error.code
            kind = error.headers.get_content_type()
        return status, (json.loads(body) if kind == "application/json" else body)

    def get(self, path):
        return self.call("GET", path)

    def post(self, path, payload=None):
        return self.call("POST", path, payload if payload is not None else {})

    def put(self, path, payload=None):
        return self.call("PUT", path, payload if payload is not None else {})

    def delete(self, path):
        return self.call("DELETE", path)

    def login(self, email, password=DEMO_PASSWORD):
        status, body = self.post("/api/auth/login", {"email": email, "password": password})
        assert status == 200, body
        return body["user"]

    def upload(self, request_id, document_type, name, data):
        return self.call(
            "POST", f"/api/verification-requests/{request_id}/documents?type={document_type}&name={name}", raw=data
        )


def rent_listing(**overrides):
    listing = {
        "title": "Test rent flat in Mirpur",
        "description": "A test listing with enough description text to pass validation.",
        "listingType": "rent",
        "propertyType": "Apartment",
        "areaName": "Mirpur 2",
        "city": "Dhaka",
        "address": "Road 5, Mirpur 2, Dhaka",
        "sizeSqft": 900,
        "bedrooms": 2,
        "bathrooms": 1,
        "furnished": False,
        "rent": {
            "monthlyRent": 20000,
            "securityDeposit": 40000,
            "availableFrom": (date.today() + timedelta(days=10)).isoformat(),
            "minLeaseMonths": 12,
            "utilitiesIncluded": False,
            "tenantPreference": "family",
        },
    }
    listing.update(overrides)
    return listing


class QuietWsgiHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


class ThreadingWsgiServer(socketserver.ThreadingMixIn, WSGIServer):
    daemon_threads = True


class ApiTestCase(unittest.TestCase):
    # PFB_TEST_WSGI=1 runs every test against the hosted (WSGI) version instead of server.py.
    use_wsgi = os.environ.get("PFB_TEST_WSGI") == "1"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = server.Config(data_dir=Path(self.temp.name), quiet=True)
        server.prepare(self.config)
        if self.use_wsgi:
            self.httpd = make_server("127.0.0.1", 0, make_wsgi_app(router, self.config),
                                     server_class=ThreadingWsgiServer, handler_class=QuietWsgiHandler)
        else:
            self.httpd = server.create_server(self.config, port=0)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.temp.cleanup()

    def client(self, email=None):
        client = Client(self.base)
        if email:
            client.login(email)
        return client

    def db(self):
        connection = sqlite3.connect(self.config.database)
        connection.row_factory = sqlite3.Row
        return contextlib.closing(connection)

    def property_id(self, title):
        with self.db() as connection:
            return connection.execute("SELECT id FROM properties WHERE title = ?", (title,)).fetchone()[0]

    def request_id(self, title):
        with self.db() as connection:
            return connection.execute(
                "SELECT vr.id FROM verification_requests vr JOIN properties p ON p.id = vr.property_id WHERE p.title = ?",
                (title,),
            ).fetchone()[0]


class Sprint1Tests(ApiTestCase):
    def test_pb01_all_new_tables_exist_and_old_listings_work(self):
        with self.db() as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table in ("rent_details", "verification_requests", "legal_documents", "verification_reports", "audit_log",
                      "consultations", "chat_messages", "payments", "rent_agreements"):
            self.assertIn(table, tables)
        status, body = self.client().get("/api/properties")
        self.assertEqual(status, 200)
        self.assertEqual(body["total"], 38)

    def test_pb02_role_saved_at_signup_and_pages_limited_by_role(self):
        guest = self.client()
        status, body = guest.post("/api/auth/signup", {
            "fullName": "New Tenant", "email": "new@example.com", "phone": "01812345678",
            "password": "secret123", "role": "buyer_tenant",
        })
        self.assertEqual(status, 201, body)
        self.assertEqual(body["user"]["role"], "buyer_tenant")
        self.assertEqual(guest.get("/api/auth/me")[1]["user"]["role"], "buyer_tenant")
        # A tenant cannot open owner, advocate or admin endpoints.
        self.assertEqual(guest.get("/api/my/listings")[0], 403)
        self.assertEqual(guest.get("/api/advocate/queue")[0], 403)
        self.assertEqual(guest.get("/api/admin/advocates")[0], 403)
        # Nobody can sign themselves up as an admin or advocate.
        status, body = self.client().post("/api/auth/signup", {
            "fullName": "Sneaky", "email": "sneaky@example.com", "phone": "01812345679",
            "password": "secret123", "role": "admin",
        })
        self.assertEqual(status, 400)
        self.assertIn("role", body["fields"])
        self.assertEqual(self.client().get("/api/my/listings")[0], 401)

    def test_pb02_signup_errors_are_clear(self):
        status, body = self.client().post("/api/auth/signup", {
            "fullName": "", "email": "bad", "phone": "123", "password": "short", "role": "owner",
        })
        self.assertEqual(status, 400)
        self.assertEqual(set(body["fields"]), {"fullName", "email", "phone", "password"})

    def test_pb03_owner_cannot_edit_or_delete_another_owners_listing(self):
        other = self.client("owner2@pfb.test")
        listing_id = self.property_id("Light-filled corner apartment")  # belongs to owner@pfb.test
        status, _ = other.put(f"/api/properties/{listing_id}", rent_listing())
        self.assertEqual(status, 403)
        self.assertEqual(other.delete(f"/api/properties/{listing_id}")[0], 403)
        self.assertEqual(self.client("tenant@pfb.test").delete(f"/api/properties/{listing_id}")[0], 403)

    def test_pb03_owner_cannot_change_verified_status(self):
        owner = self.client("owner@pfb.test")
        status, body = owner.post("/api/properties", rent_listing(verificationStatus="document_verified"))
        self.assertEqual(status, 403)
        listing_id = self.property_id("Easy, airy living by the lake")
        status, _ = owner.put(f"/api/properties/{listing_id}", rent_listing(badgeLevel="fully_verified"))
        self.assertEqual(status, 403)
        request_id = self.request_id("Easy, airy living by the lake")
        self.assertEqual(owner.post(f"/api/verification-requests/{request_id}/decision", {})[0], 403)

    def test_pb04_admin_adds_blocks_and_removes_advocate(self):
        admin = self.client("admin@pfb.test")
        status, body = admin.post("/api/admin/advocates", {
            "fullName": "Adv. New Person", "email": "newadv@example.com", "phone": "01911111111",
            "password": "Start1234", "barCouncilId": "DBC-2020-0001", "specialization": "Land",
        })
        self.assertEqual(status, 201, body)
        advocate_id = body["advocate"]["id"]
        advocate = self.client()
        advocate.login("newadv@example.com", "Start1234")
        self.assertEqual(advocate.get("/api/advocate/queue")[0], 200)

        self.assertEqual(admin.post(f"/api/admin/advocates/{advocate_id}/status", {"status": "blocked"})[0], 200)
        self.assertEqual(advocate.get("/api/advocate/queue")[0], 401)  # session ended
        status, body = Client(self.base).post("/api/auth/login", {"email": "newadv@example.com", "password": "Start1234"})
        self.assertEqual(status, 403)
        self.assertIn("blocked", body["error"])

        self.assertEqual(admin.post(f"/api/admin/advocates/{advocate_id}/status", {"status": "active"})[0], 200)
        self.assertEqual(admin.delete(f"/api/admin/advocates/{advocate_id}")[0], 200)
        emails = [a["email"] for a in admin.get("/api/admin/advocates")[1]["advocates"]]
        self.assertNotIn("newadv@example.com", emails)
        self.assertEqual(Client(self.base).post("/api/auth/login", {"email": "newadv@example.com", "password": "Start1234"})[0], 401)

    def test_pb04_duplicate_bar_council_id_rejected(self):
        status, body = self.client("admin@pfb.test").post("/api/admin/advocates", {
            "fullName": "Adv. Copy", "email": "copy@example.com", "phone": "01911111112",
            "password": "Start1234", "barCouncilId": "DBC-2016-0412", "specialization": "Land",
        })
        self.assertEqual(status, 409)
        self.assertIn("barCouncilId", body["fields"])

    def test_pb05_description_is_optional(self):
        owner = self.client("owner@pfb.test")
        for description in (None, "", "   "):
            listing = rent_listing(description=description)
            if description is None:
                del listing["description"]
            status, body = owner.post("/api/properties", listing)
            self.assertEqual(status, 201, body)
            self.assertEqual(body["property"]["description"], "")
        listing_id = body["property"]["id"]
        status, body = owner.put(f"/api/properties/{listing_id}", rent_listing(description="Short note"))
        self.assertEqual(status, 200, body)
        self.assertEqual(body["property"]["description"], "Short note")
        status, body = owner.post("/api/properties", rent_listing(description="x" * 2001))
        self.assertEqual(status, 400)
        self.assertIn("description", body["fields"])

    def test_pb05_pb06_pb09_rent_listing_saved_live_and_unverified(self):
        owner = self.client("owner@pfb.test")
        status, body = owner.post("/api/properties", rent_listing())
        self.assertEqual(status, 201, body)
        listing = body["property"]
        self.assertEqual(listing["verificationStatus"], "unverified")
        self.assertEqual(listing["rent"]["moveInCost"], 60000)
        # A visitor sees it at once, with rent, deposit and move-in cost.
        status, public = self.client().get(f"/api/properties/{listing['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(public["verificationStatus"], "unverified")
        self.assertEqual(public["rent"], {
            "monthlyRent": 20000, "securityDeposit": 40000, "moveInCost": 60000,
            "availableFrom": listing["rent"]["availableFrom"], "minLeaseMonths": 12,
            "utilitiesIncluded": False, "tenantPreference": "family",
        })

    def test_pb05_negative_rent_shows_clear_error(self):
        owner = self.client("owner@pfb.test")
        bad = rent_listing()
        bad["rent"] = {**bad["rent"], "monthlyRent": -5000, "securityDeposit": "abc", "availableFrom": "2020-01-01"}
        status, body = owner.post("/api/properties", bad)
        self.assertEqual(status, 400)
        self.assertEqual(body["fields"]["rent.monthlyRent"], "Monthly rent must be more than 0.")
        self.assertEqual(body["fields"]["rent.securityDeposit"], "Security deposit must be a whole number.")
        self.assertIn("rent.availableFrom", body["fields"])

    def test_pb05_only_owners_can_create_listings(self):
        self.assertEqual(self.client("tenant@pfb.test").post("/api/properties", rent_listing())[0], 403)

    def test_pb07_filters_by_purpose_rent_range_area_type_and_bedrooms(self):
        guest = self.client()
        _, body = guest.get("/api/properties?purpose=rent&minPrice=30000&maxPrice=60000")
        rents = [p["rent"]["monthlyRent"] for p in body["properties"]]
        self.assertTrue(rents)
        self.assertTrue(all(p["listingType"] == "rent" for p in body["properties"]))
        self.assertTrue(all(30000 <= r <= 60000 for r in rents))

        _, body = guest.get("/api/properties?purpose=sale&area=dhanmondi")
        self.assertEqual(body["total"], 0)
        _, body = guest.get("/api/properties?area=Dhanmondi&type=Studio&bedrooms=1")
        self.assertEqual([p["title"] for p in body["properties"]], ["The little studio with big light"])
        _, body = guest.get("/api/properties?bedrooms=4")
        self.assertTrue(all(p["bedrooms"] >= 4 for p in body["properties"]))

        status, body = guest.get("/api/properties?minPrice=500&maxPrice=100")
        self.assertEqual(status, 400)
        self.assertIn("maxPrice", body["fields"])

    def test_removed_listing_leaves_search(self):
        owner = self.client("owner@pfb.test")
        listing_id = self.property_id("Sunny apartment in Banasree")
        self.assertEqual(owner.delete(f"/api/properties/{listing_id}")[0], 200)
        _, body = self.client().get("/api/properties?area=Banasree")
        self.assertEqual(body["total"], 0)
        self.assertEqual(self.client().get(f"/api/properties/{listing_id}")[0], 404)


class Sprint2Tests(ApiTestCase):
    def new_request(self, owner):
        _, body = owner.post("/api/properties", rent_listing(requestVerification=True))
        return body["property"]["id"], body["verificationRequestId"]

    def upload_required(self, owner, request_id):
        for document_type in ("land_deed", "mutation", "tax_receipt"):
            status, body = owner.upload(request_id, document_type, f"{document_type}.pdf", sample_pdf([document_type]))
            self.assertEqual(status, 201, body)

    def test_pb10_request_created_pending_and_visible_to_owner(self):
        owner = self.client("owner@pfb.test")
        property_id, request_id = self.new_request(owner)
        self.assertIsNotNone(request_id)
        status, body = owner.get(f"/api/verification-requests/{request_id}")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "pending")
        _, listings = owner.get("/api/my/listings")
        mine = next(p for p in listings["properties"] if p["id"] == property_id)
        self.assertEqual(mine["verificationRequest"]["status"], "pending")
        # A second open request for the same listing is refused.
        self.assertEqual(owner.post(f"/api/properties/{property_id}/verification-request")[0], 409)

    def test_pb11_only_pdf_jpg_png_under_limit(self):
        owner = self.client("owner@pfb.test")
        _, request_id = self.new_request(owner)
        self.assertEqual(owner.upload(request_id, "land_deed", "deed.png", PNG_BYTES)[0], 201)
        status, body = owner.upload(request_id, "land_deed", "deed.docx", b"PK\x03\x04")
        self.assertEqual((status, body["error"]), (400, "Only PDF, JPG and PNG files are accepted."))
        status, body = owner.upload(request_id, "land_deed", "fake.pdf", b"<html>not a pdf</html>")
        self.assertEqual(status, 400)
        status, _ = owner.upload(request_id, "land_deed", "huge.pdf", b"%PDF-" + b"0" * (5 * 1024 * 1024))
        self.assertEqual(status, 413)

    def test_pb11_files_are_private(self):
        owner = self.client("owner@pfb.test")
        request_id = self.request_id("Light-filled corner apartment")  # pending, uploaded by owner@pfb.test
        _, detail = owner.get(f"/api/verification-requests/{request_id}")
        document_id = detail["documents"][0]["id"]
        url = f"/api/documents/{document_id}/file"

        status, body = owner.get(url)
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"%PDF-"))
        self.assertEqual(self.client().get(url)[0], 401)
        self.assertEqual(self.client("tenant@pfb.test").get(url)[0], 403)
        self.assertEqual(self.client("owner2@pfb.test").get(url)[0], 403)
        advocate = self.client("advocate@pfb.test")
        self.assertEqual(advocate.get(url)[0], 403)  # not assigned yet
        advocate.post(f"/api/verification-requests/{request_id}/start-review")
        self.assertEqual(advocate.get(url)[0], 200)
        self.assertEqual(self.client("advocate2@pfb.test").get(url)[0], 403)
        self.assertEqual(self.client("admin@pfb.test").get(url)[0], 200)
        # Uploaded files are never reachable as static files.
        self.assertEqual(self.client().get("/instance/pfb.sqlite3")[0], 404)

    def test_pb12_queue_lists_pending_requests_with_details(self):
        advocate = self.client("advocate@pfb.test")
        status, body = advocate.get("/api/advocate/queue")
        self.assertEqual(status, 200)
        titles = [item["property"]["title"] for item in body["queue"]]
        self.assertIn("Light-filled corner apartment", titles)
        first = body["queue"][0]
        for key in ("title", "areaName"):
            self.assertIn(key, first["property"])
        self.assertIn("submittedAt", first)
        status, detail = advocate.get(f"/api/verification-requests/{first['id']}")
        self.assertEqual(status, 200)

    def test_pb12_cannot_start_review_before_papers_uploaded(self):
        advocate = self.client("advocate@pfb.test")
        request_id = self.request_id("A practical flat close to Mirpur 10")
        status, body = advocate.post(f"/api/verification-requests/{request_id}/start-review")
        self.assertEqual(status, 409)
        self.assertIn("required papers", body["error"])

    def test_pb13_pb15_verify_with_checklist_then_badge_and_filter(self):
        owner = self.client("owner@pfb.test")
        property_id, request_id = self.new_request(owner)
        self.upload_required(owner, request_id)
        advocate = self.client("advocate@pfb.test")
        self.assertEqual(advocate.post(f"/api/verification-requests/{request_id}/start-review")[0], 200)
        # Second advocate cannot take or decide the same request.
        self.assertEqual(self.client("advocate2@pfb.test").post(f"/api/verification-requests/{request_id}/start-review")[0], 409)

        # Not verified yet: no badge, hidden by the Verified-only filter.
        _, verified = self.client().get("/api/properties?verified=1")
        self.assertNotIn(property_id, [p["id"] for p in verified["properties"]])

        checklist = {"land_deed": "ok", "mutation": "ok", "tax_receipt": "ok", "ownership_history": "ok"}
        status, body = advocate.post(f"/api/verification-requests/{request_id}/decision",
                                     {"decision": "document_verified", "checklist": checklist, "notes": ""})
        self.assertEqual(status, 400)
        self.assertIn("notes", body["fields"])
        status, body = advocate.post(f"/api/verification-requests/{request_id}/decision",
                                     {"decision": "document_verified", "checklist": {**checklist, "mutation": "problem"},
                                      "notes": "Everything checked properly."})
        self.assertEqual(status, 400)
        status, body = advocate.post(f"/api/verification-requests/{request_id}/decision",
                                     {"decision": "document_verified", "checklist": checklist,
                                      "notes": "Deed, mutation and tax receipt all match."})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["status"], "document_verified")
        self.assertTrue(all(d["reviewStatus"] == "ok" for d in body["documents"]))

        _, listing = self.client().get(f"/api/properties/{property_id}")
        self.assertEqual(listing["verificationStatus"], "document_verified")
        _, verified = self.client().get("/api/properties?verified=1")
        self.assertIn(property_id, [p["id"] for p in verified["properties"]])
        self.assertTrue(all(p["verificationStatus"] == "document_verified" for p in verified["properties"]))

    def test_pb14_issue_found_notes_and_resubmission(self):
        owner = self.client("owner@pfb.test")
        property_id, request_id = self.new_request(owner)
        self.upload_required(owner, request_id)
        advocate = self.client("advocate@pfb.test")
        advocate.post(f"/api/verification-requests/{request_id}/start-review")
        # Owner cannot swap papers during the review.
        self.assertEqual(owner.upload(request_id, "mutation", "m.pdf", sample_pdf(["x"]))[0], 409)
        notes = "Mutation paper is for a different plot number."
        status, _ = advocate.post(f"/api/verification-requests/{request_id}/decision", {
            "decision": "issue_found", "notes": notes,
            "checklist": {"land_deed": "ok", "mutation": "problem", "tax_receipt": "ok", "ownership_history": "ok"},
        })
        self.assertEqual(status, 200)

        _, detail = owner.get(f"/api/verification-requests/{request_id}")
        self.assertEqual((detail["status"], detail["advocateNotes"]), ("issue_found", notes))
        self.assertEqual(self.client().get(f"/api/properties/{property_id}")[1]["verificationStatus"], "unverified")

        status, body = owner.upload(request_id, "mutation", "mutation-fixed.pdf", sample_pdf(["fixed"]))
        self.assertEqual(status, 201)
        self.assertEqual(body["requestStatus"], "pending")
        _, detail = owner.get(f"/api/verification-requests/{request_id}")
        self.assertEqual(detail["resubmissionCount"], 1)
        self.assertEqual([d["fileName"] for d in detail["replacedDocuments"]], ["mutation.pdf"])
        queue_ids = [item["id"] for item in advocate.get("/api/advocate/queue")[1]["queue"]]
        self.assertIn(request_id, queue_ids)

    def test_pb16_every_status_change_logged_and_log_is_append_only(self):
        owner = self.client("owner@pfb.test")
        property_id, request_id = self.new_request(owner)
        self.upload_required(owner, request_id)
        advocate = self.client("advocate@pfb.test")
        advocate.post(f"/api/verification-requests/{request_id}/start-review")
        advocate.post(f"/api/verification-requests/{request_id}/decision", {
            "decision": "document_verified", "notes": "All papers are in order.",
            "checklist": {"land_deed": "ok", "mutation": "ok", "tax_receipt": "ok", "ownership_history": "ok"},
        })
        admin = self.client("admin@pfb.test")
        _, log = admin.get(f"/api/admin/audit-log?targetType=verification_request&targetId={request_id}")
        changes = [(e["oldValue"], e["newValue"], e["actor"]["name"]) for e in log["entries"]
                   if e["actionType"] in ("verification_requested", "verification_status_changed")]
        self.assertCountEqual(changes, [
            (None, "pending", "Nadia Rahman"),
            ("pending", "in_review", "Adv. Sarah Rahman"),
            ("in_review", "document_verified", "Adv. Sarah Rahman"),
        ])
        self.assertTrue(all(e["createdAt"] for e in log["entries"]))
        _, log = admin.get(f"/api/admin/audit-log?targetType=property&targetId={property_id}")
        self.assertIn(("unverified", "document_verified"), [(e["oldValue"], e["newValue"]) for e in log["entries"]])

        self.assertEqual(self.client("advocate@pfb.test").get("/api/admin/audit-log")[0], 403)
        with self.db() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE audit_log SET new_value = 'x'")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM audit_log")

    def test_pb17_high_demand_areas_come_first(self):
        admin = self.client("admin@pfb.test")
        advocate = self.client("advocate@pfb.test")
        queue = advocate.get("/api/advocate/queue")[1]["queue"]
        self.assertEqual(queue[0]["property"]["areaName"], "Gulshan 2")  # Gulshan is seeded as high-demand
        self.assertTrue(queue[0]["isHighDemand"])

        # Mark Mirpur as high-demand: the Mirpur request moves above the non-high-demand Dhanmondi one.
        self.assertEqual(admin.post("/api/admin/high-demand-areas", {"areaName": "Mirpur"})[0], 201)
        areas = [item["property"]["areaName"] for item in advocate.get("/api/advocate/queue")[1]["queue"]]
        self.assertLess(areas.index("Mirpur 10"), areas.index("Dhanmondi"))
        self.assertEqual(advocate.post("/api/admin/high-demand-areas", {"areaName": "Uttara"})[0], 403)


class BrowsingHistoryTests(ApiTestCase):
    def view_rows(self, property_id):
        with self.db() as connection:
            return connection.execute(
                "SELECT user_id, source FROM property_views WHERE property_id = ? ORDER BY id", (property_id,)
            ).fetchall()

    def test_views_are_recorded_once_per_visit_and_staff_or_owner_views_are_not(self):
        listing_id = self.property_id("Easy, airy living by the lake")  # owned by owner@pfb.test
        before = len(self.view_rows(listing_id))
        tenant = self.client("tenant@pfb.test")
        tenant.get(f"/api/properties/{listing_id}?from=search")
        tenant.get(f"/api/properties/{listing_id}?from=search")  # a refresh is not a second visit
        self.client().get(f"/api/properties/{listing_id}?from=bogus")  # guest, unknown source
        self.client("owner@pfb.test").get(f"/api/properties/{listing_id}")
        self.client("advocate@pfb.test").get(f"/api/properties/{listing_id}")
        self.client("admin@pfb.test").get(f"/api/properties/{listing_id}")
        new_rows = [(row["user_id"] is None, row["source"]) for row in self.view_rows(listing_id)[before:]]
        self.assertEqual(new_rows, [(False, "search"), (True, "direct")])

    def test_searches_are_saved_for_signed_in_users_without_repeats(self):
        tenant = self.client("tenant2@pfb.test")
        _, before = tenant.get("/api/history")
        tenant.get("/api/properties")  # the plain list of all homes is not a search
        tenant.get("/api/properties?purpose=rent&area=Banani&sort=newest")
        tenant.get("/api/properties?purpose=rent&area=Banani&sort=price_asc")  # same filters, other sort
        self.client().get("/api/properties?purpose=rent&area=Banani")  # guests are not saved
        _, after = tenant.get("/api/history")
        self.assertEqual(len(after["searches"]), len(before["searches"]) + 1)
        latest = after["searches"][0]
        self.assertEqual(latest["filters"], {"purpose": "rent", "area": "Banani"})
        self.assertEqual(latest["resultCount"], 2)

    def test_history_page_shows_own_views_and_can_be_cleared(self):
        tenant = self.client("tenant@pfb.test")
        listing_id = self.property_id("Plot in Rangpur town")
        tenant.get(f"/api/properties/{listing_id}?from=search")
        status, history = tenant.get("/api/history")
        self.assertEqual(status, 200)
        self.assertEqual(history["views"][0]["id"], listing_id)
        self.assertTrue(history["searches"])
        self.assertEqual(self.client("advocate@pfb.test").get("/api/history")[0], 403)
        self.assertEqual(self.client().get("/api/history")[0], 401)

        total_before = len(self.view_rows(listing_id))
        status, result = tenant.delete("/api/history")
        self.assertEqual(status, 200)
        self.assertGreater(result["viewsCleared"], 0)
        _, history = tenant.get("/api/history")
        self.assertEqual((history["views"], history["searches"]), ([], []))
        # The listing keeps its view count; the views are just no longer linked to the tenant.
        self.assertEqual(len(self.view_rows(listing_id)), total_before)

    def test_owner_sees_view_counts_and_admin_sees_activity(self):
        listing_id = self.property_id("Easy, airy living by the lake")
        owner = self.client("owner@pfb.test")
        _, listings = owner.get("/api/my/listings")
        before = next(p for p in listings["properties"] if p["id"] == listing_id)["views"]["total"]
        self.client().get(f"/api/properties/{listing_id}")
        _, listings = owner.get("/api/my/listings")
        views = next(p for p in listings["properties"] if p["id"] == listing_id)["views"]
        self.assertEqual(views["total"], before + 1)
        self.assertGreaterEqual(views["total"], views["lastWeek"])

        status, activity = self.client("admin@pfb.test").get("/api/admin/activity?days=30")
        self.assertEqual(status, 200)
        self.assertGreater(activity["totals"]["views"], 0)
        self.assertTrue(activity["topListings"] and activity["topAreas"] and activity["recentViews"])
        self.assertEqual(self.client("tenant@pfb.test").get("/api/admin/activity")[0], 403)

    def test_old_database_is_upgraded_with_history_tables(self):
        old = Path(self.temp.name) / "old.sqlite3"
        connection = sqlite3.connect(old)
        connection.executescript(db.SCHEMA)
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
        connection.close()
        self.assertFalse(db.initialize(old))  # upgraded, not re-created
        with contextlib.closing(sqlite3.connect(old)) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertTrue({"property_views", "search_history"} <= tables)
        self.assertEqual(version, db.SCHEMA_VERSION)


class WsgiHostingTests(ApiTestCase):
    """The hosted version (wsgi.py) serves the same site and API as server.py."""

    use_wsgi = True

    def test_pages_are_served_and_private_files_are_not(self):
        guest = self.client()
        status, body = guest.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Property Finder Bangladesh", body)
        request = urllib.request.Request(self.base + "/js/app.js")
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.headers.get_content_type(), "text/javascript")
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        for path in ("/server.py", "/wsgi.py", "/instance/pfb.sqlite3", "/../server.py", "/%2e%2e/server.py", "/js/"):
            self.assertEqual(guest.get(path)[0], 404, path)

    def test_login_upload_and_review_work_through_wsgi(self):
        owner = self.client("owner@pfb.test")
        _, body = owner.post("/api/properties", rent_listing(requestVerification=True))
        request_id = body["verificationRequestId"]
        for document_type in ("land_deed", "mutation", "tax_receipt"):
            status, _ = owner.upload(request_id, document_type, f"{document_type}.pdf", sample_pdf([document_type]))
            self.assertEqual(status, 201)
        advocate = self.client("advocate@pfb.test")
        self.assertEqual(advocate.post(f"/api/verification-requests/{request_id}/start-review")[0], 200)
        status, body = advocate.post(f"/api/verification-requests/{request_id}/decision", {
            "decision": "document_verified", "notes": "All papers are in order.",
            "checklist": {"land_deed": "ok", "mutation": "ok", "tax_receipt": "ok", "ownership_history": "ok"},
        })
        self.assertEqual((status, body["status"]), (200, "document_verified"))
        self.assertEqual(self.client().post("/api/auth/logout", {})[0], 200)
        self.assertEqual(Client(self.base).call("POST", "/api/auth/logout", {}, csrf=False)[0], 403)


class SecurityTests(ApiTestCase):
    def test_state_changes_need_csrf_header(self):
        status, _ = self.client().call("POST", "/api/auth/login",
                                        {"email": "owner@pfb.test", "password": DEMO_PASSWORD}, csrf=False)
        self.assertEqual(status, 403)

    def test_repeated_wrong_passwords_are_throttled(self):
        guest = self.client()
        for _ in range(5):
            self.assertEqual(guest.post("/api/auth/login", {"email": "owner@pfb.test", "password": "wrong1234"})[0], 401)
        self.assertEqual(guest.post("/api/auth/login", {"email": "owner@pfb.test", "password": DEMO_PASSWORD})[0], 429)

    def test_issue_found_is_private_to_owner(self):
        listing_id = self.property_id("A family home with room to grow")
        self.assertEqual(self.client().get(f"/api/properties/{listing_id}")[1]["verificationStatus"], "unverified")
        self.assertEqual(self.client("owner@pfb.test").get(f"/api/properties/{listing_id}")[1]["verificationStatus"], "issue_found")


if __name__ == "__main__":
    unittest.main()
