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
from datetime import date, datetime, timedelta, timezone
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

    def advocate_application(self, **overrides):
        data = {
            "fullName": "Adv. Self Signup", "email": "selfadv@example.com", "phone": "01911111113",
            "password": "Start1234", "barCouncilId": "DBC-2023-0099", "specialization": "Land",
        }
        data.update(overrides)
        return data

    def test_advocate_applies_gets_appointment_and_is_verified_in_person(self):
        advocate = self.client()
        status, body = advocate.post("/api/auth/advocate-signup", self.advocate_application())
        self.assertEqual(status, 201, body)
        self.assertEqual((body["user"]["role"], body["user"]["advocateStatus"]), ("advocate", "pending"))
        advocate_id = body["user"]["id"]

        # Until the admin verifies them, the advocate has no advocate powers.
        self.assertEqual(advocate.get("/api/advocate/queue")[0], 403)
        pending_request = self.request_id("Easy, airy living by the lake")
        self.assertEqual(advocate.get(f"/api/verification-requests/{pending_request}")[0], 403)
        self.assertEqual(advocate.post(f"/api/verification-requests/{pending_request}/start-review")[0], 403)
        issue_listing = self.property_id("A family home with room to grow")
        self.assertEqual(advocate.get(f"/api/properties/{issue_listing}")[1]["verificationStatus"], "unverified")
        status, body = advocate.get("/api/advocate/application")
        self.assertEqual((status, body["application"]["advocateStatus"], body["application"]["appointment"]), (200, "pending", None))

        admin = self.client("admin@pfb.test")
        listed = {a["email"]: a["advocateStatus"] for a in admin.get("/api/admin/advocates")[1]["advocates"]}
        self.assertEqual(listed["selfadv@example.com"], "pending")
        self.assertEqual(listed["advocate@pfb.test"], "verified")
        # No verification without an appointment first.
        self.assertEqual(admin.post(f"/api/admin/advocates/{advocate_id}/verification", {"decision": "verified"})[0], 409)
        status, body = admin.post(f"/api/admin/advocates/{advocate_id}/appointment", {"appointmentAt": "2020-01-01T10:00", "place": ""})
        self.assertEqual(status, 400)
        self.assertEqual(set(body["fields"]), {"appointmentAt", "place"})
        when = (date.today() + timedelta(days=3)).isoformat() + "T10:30"
        status, body = admin.post(f"/api/admin/advocates/{advocate_id}/appointment", {
            "appointmentAt": when, "place": "PFB office, Road 5, Dhanmondi", "message": "Bring your Bar Council certificate.",
        })
        self.assertEqual((status, body["advocate"]["advocateStatus"]), (200, "appointment_sent"), body)

        # The advocate sees the appointment message after logging in again.
        advocate = self.client()
        advocate.login("selfadv@example.com", "Start1234")
        application = advocate.get("/api/advocate/application")[1]["application"]
        self.assertEqual(application["appointment"], {"at": when, "place": "PFB office, Road 5, Dhanmondi"})
        self.assertEqual(application["adminMessage"], "Bring your Bar Council certificate.")
        self.assertEqual(advocate.get("/api/advocate/queue")[0], 403)

        status, body = admin.post(f"/api/admin/advocates/{advocate_id}/verification", {"decision": "verified"})
        self.assertEqual((status, body["advocate"]["advocateStatus"]), (200, "verified"), body)
        self.assertEqual(advocate.get("/api/auth/me")[1]["user"]["advocateStatus"], "verified")
        self.assertEqual(advocate.get("/api/advocate/queue")[0], 200)
        self.assertEqual(admin.post(f"/api/admin/advocates/{advocate_id}/verification", {"decision": "rejected", "note": "Too late"})[0], 409)
        with self.db() as connection:
            actions = [row[0] for row in connection.execute(
                "SELECT action_type FROM audit_log WHERE target_type = 'user' AND target_id = ? ORDER BY id", (advocate_id,))]
        self.assertEqual(actions, ["advocate_applied", "advocate_appointment_sent", "advocate_verification_changed"])

    def test_advocate_application_can_be_rejected_and_is_admin_only(self):
        advocate = self.client()
        status, body = advocate.post("/api/auth/advocate-signup", self.advocate_application())
        advocate_id = body["user"]["id"]
        # Only the admin can send appointments or decide; an applicant cannot verify themselves.
        for client in (advocate, self.client("owner@pfb.test"), self.client("advocate@pfb.test")):
            self.assertEqual(client.post(f"/api/admin/advocates/{advocate_id}/verification", {"decision": "verified"})[0], 403)
            self.assertEqual(client.post(f"/api/admin/advocates/{advocate_id}/appointment", {})[0], 403)
        self.assertEqual(self.client("tenant@pfb.test").get("/api/advocate/application")[0], 403)

        admin = self.client("admin@pfb.test")
        status, body = admin.post(f"/api/admin/advocates/{advocate_id}/verification", {"decision": "rejected"})
        self.assertEqual(status, 400)
        self.assertIn("note", body["fields"])
        status, body = admin.post(f"/api/admin/advocates/{advocate_id}/verification",
                                  {"decision": "rejected", "note": "Bar Council ID could not be confirmed."})
        self.assertEqual((status, body["advocate"]["advocateStatus"]), (200, "rejected"))
        application = advocate.get("/api/advocate/application")[1]["application"]
        self.assertEqual((application["advocateStatus"], application["adminMessage"]),
                         ("rejected", "Bar Council ID could not be confirmed."))
        self.assertEqual(advocate.get("/api/advocate/queue")[0], 403)

    def test_advocate_signup_errors_and_duplicates(self):
        status, body = self.client().post("/api/auth/advocate-signup", {"fullName": "A", "email": "bad", "phone": "1", "password": "x"})
        self.assertEqual(status, 400)
        self.assertEqual(set(body["fields"]), {"fullName", "email", "phone", "password", "barCouncilId", "specialization"})
        status, body = self.client().post("/api/auth/advocate-signup",
                                          self.advocate_application(email="advocate@pfb.test", barCouncilId="DBC-2016-0412"))
        self.assertEqual(status, 409)
        self.assertEqual(set(body["fields"]), {"email", "barCouncilId"})
        # The demo applicant is waiting and cannot use the queue.
        applicant = self.client("applicant@pfb.test")
        self.assertEqual(applicant.get("/api/auth/me")[1]["user"]["advocateStatus"], "pending")
        self.assertEqual(applicant.get("/api/advocate/queue")[0], 403)

    def test_passwords_are_stored_hashed_with_a_salt_per_account(self):
        self.client().post("/api/auth/signup", {
            "fullName": "New Tenant", "email": "new@example.com", "phone": "01812345678",
            "password": DEMO_PASSWORD, "role": "buyer_tenant",
        })
        with self.db() as connection:
            hashes = [row[0] for row in connection.execute("SELECT password_hash FROM users")]
        self.assertEqual(len(set(hashes)), len(hashes))  # same password, different stored value
        for stored in hashes:
            self.assertTrue(stored.startswith("pbkdf2_sha256$"))
            self.assertNotIn(DEMO_PASSWORD, stored)

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

    def test_old_database_keeps_its_advocates_verified(self):
        old = Path(self.temp.name) / "old.sqlite3"
        connection = sqlite3.connect(old)
        connection.executescript(db.SCHEMA + db.HISTORY_SCHEMA)
        connection.execute("INSERT INTO users (full_name, email, phone, password_hash, role, created_at) "
                           "VALUES ('Adv. Old', 'old@example.com', '01711111111', 'x', 'advocate', '2026-01-01')")
        connection.execute("INSERT INTO advocate_profiles (user_id, bar_council_id, specialization, added_at) "
                           "VALUES (1, 'DBC-1', 'Land', '2026-01-01')")
        connection.execute("PRAGMA user_version = 2")
        connection.commit()
        connection.close()
        self.assertFalse(db.initialize(old))
        with contextlib.closing(sqlite3.connect(old)) as connection:
            self.assertEqual(connection.execute("SELECT verification_status FROM advocate_profiles").fetchone()[0], "verified")
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)


class Sprint3Tests(ApiTestCase):
    """Legal reports, badge levels, Ask an Advocate, chat, paid consultations and notifications (PB-18 to PB-25)."""

    VERIFIED = "A quiet home above the city"      # verified by advocate@pfb.test
    UNVERIFIED = "Light-filled corner apartment"

    def advocate_id(self, email="advocate@pfb.test"):
        with self.db() as connection:
            return connection.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]

    def verify_new_listing(self):
        """An owner lists a home, uploads the papers and an advocate verifies it. Returns (listing id, request id)."""
        owner = self.client("owner@pfb.test")
        _, body = owner.post("/api/properties", rent_listing(requestVerification=True))
        listing_id, request_id = body["property"]["id"], body["verificationRequestId"]
        for document_type in ("land_deed", "mutation", "tax_receipt"):
            owner.upload(request_id, document_type, f"{document_type}.pdf", sample_pdf([document_type]))
        advocate = self.client("advocate@pfb.test")
        advocate.post(f"/api/verification-requests/{request_id}/start-review")
        status, body = advocate.post(f"/api/verification-requests/{request_id}/decision", {
            "decision": "document_verified", "notes": "All papers are in order.",
            "checklist": {"land_deed": "ok", "mutation": "ok", "tax_receipt": "ok", "ownership_history": "ok"},
        })
        self.assertEqual(status, 200, body)
        return listing_id, request_id

    def book(self, client, slot_index=0, email="advocate@pfb.test"):
        advocate_id = self.advocate_id(email)
        slots = client.get(f"/api/advocates/{advocate_id}/slots")[1]["slots"]
        return client.post("/api/consultations", {
            "propertyId": self.property_id(self.VERIFIED), "advocateId": advocate_id, "slotStart": slots[slot_index],
        }), slots[slot_index]

    def test_pb18_legal_report_pdf_is_created_when_a_property_is_verified(self):
        listing_id, request_id = self.verify_new_listing()
        with self.db() as connection:
            report = connection.execute("SELECT * FROM verification_reports WHERE request_id = ?", (request_id,)).fetchone()
        self.assertIsNotNone(report)
        self.assertEqual(report["badge_level"], "document_verified")
        self.assertIn("not a legal opinion", report["disclaimer_text"])
        # A visitor who is not logged in can download it from the listing.
        status, pdf = self.client().get(f"/api/properties/{listing_id}/legal-report")
        self.assertEqual(status, 200)
        self.assertTrue(pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF"))
        for text in (b"Property legal report", b"Land deed: In order", b"Mutation paper", b"Land development tax receipt: In order",
                     b"Ownership history: In order", b"Result: Document Verified", b"Disclaimer", b"Adv. Sarah Rahman",
                     datetime.now(timezone(timedelta(hours=6))).date().isoformat().encode()):
            self.assertIn(text, pdf)
        # Listings that are not verified have no report.
        self.assertEqual(self.client().get(f"/api/properties/{self.property_id(self.UNVERIFIED)}/legal-report")[0], 404)
        self.assertEqual(self.client().get(f"/api/properties/{self.property_id('A family home with room to grow')}/legal-report")[0], 404)

    def test_pb19_advocate_sets_badge_level_and_listing_and_report_show_it(self):
        listing_id, request_id = self.verify_new_listing()
        advocate = self.client("advocate@pfb.test")
        self.assertEqual(advocate.get(f"/api/verification-requests/{request_id}")[1]["canSetBadgeLevel"], True)
        self.assertEqual(advocate.post(f"/api/verification-requests/{request_id}/badge-level", {"level": "gold"})[0], 400)
        status, body = advocate.post(f"/api/verification-requests/{request_id}/badge-level", {"level": "site_visited"})
        self.assertEqual((status, body["badgeLevel"]), (200, "site_visited"), body)
        listing = self.client().get(f"/api/properties/{listing_id}")[1]
        self.assertEqual((listing["verificationStatus"], listing["badgeLevel"]), ("document_verified", "site_visited"))
        self.assertIn(b"Result: Site Visited", self.client().get(f"/api/properties/{listing_id}/legal-report")[1])
        advocate.post(f"/api/verification-requests/{request_id}/badge-level", {"level": "fully_verified"})
        self.assertIn(b"Result: Fully Verified", self.client().get(f"/api/properties/{listing_id}/legal-report")[1])
        # Only the advocate who verified it can change the level, and only on a verified listing.
        url = f"/api/verification-requests/{request_id}/badge-level"
        for email in ("advocate2@pfb.test", "owner@pfb.test", "admin@pfb.test"):
            self.assertEqual(self.client(email).post(url, {"level": "document_verified"})[0], 403, email)
        pending = self.request_id("Easy, airy living by the lake")
        advocate.post(f"/api/verification-requests/{pending}/start-review")
        self.assertEqual(advocate.post(f"/api/verification-requests/{pending}/badge-level", {"level": "site_visited"})[0], 409)
        # Demo data has one listing of each higher level.
        levels = {p["badgeLevel"] for p in self.client().get("/api/properties?verified=1")[1]["properties"]}
        self.assertEqual(levels, {"document_verified", "site_visited", "fully_verified"})

    def test_pb20_ask_an_advocate_only_on_verified_listings_for_buyers(self):
        tenant = self.client("tenant2@pfb.test")
        verified, unverified = self.property_id(self.VERIFIED), self.property_id(self.UNVERIFIED)
        status, body = tenant.get(f"/api/properties/{verified}/chat")
        self.assertEqual((status, body["consultation"]), (200, None))
        self.assertEqual(body["advocate"]["name"], "Adv. Sarah Rahman")  # the advocate who verified this listing
        self.assertEqual(tenant.get(f"/api/properties/{unverified}/chat")[0], 409)
        self.assertEqual(tenant.post(f"/api/properties/{unverified}/chat", {"body": "Is this safe to buy?"})[0], 409)
        status, body = tenant.post("/api/consultations", {
            "propertyId": unverified, "advocateId": self.advocate_id(), "slotStart": "2030-01-01T10:00"})
        self.assertEqual(status, 409)
        # The two choices: a free question needs no fee, a paid booking shows advocates with their fee.
        advocates = tenant.get("/api/advocates")[1]["advocates"]
        self.assertEqual({a["name"]: a["fee"] for a in advocates}, {"Adv. Sarah Rahman": 500, "Adv. Mahmud Karim": 700})
        for client in (self.client(), self.client("owner@pfb.test")):
            self.assertIn(client.get(f"/api/properties/{verified}/chat")[0], (401, 403))
            self.assertIn(client.get("/api/advocates")[0], (401, 403))

    def test_pb21_chat_messages_are_saved_and_the_advocate_can_reply(self):
        tenant = self.client("tenant2@pfb.test")
        listing_id = self.property_id(self.VERIFIED)
        self.assertEqual(tenant.post(f"/api/properties/{listing_id}/chat", {"body": ""})[0], 400)
        status, chat = tenant.post(f"/api/properties/{listing_id}/chat", {"body": "Is the mutation paper up to date?"})
        self.assertEqual((status, chat["kind"], chat["state"], chat["fee"]), (201, "free_chat", "chat", 0), chat)
        advocate = self.client("advocate@pfb.test")
        self.assertIn(chat["id"], [c["id"] for c in advocate.get("/api/consultations")[1]["consultations"]])
        status, body = advocate.post(f"/api/consultations/{chat['id']}/messages", {"body": "Yes, it was renewed this year."})
        self.assertEqual(status, 201, body)
        tenant.post(f"/api/properties/{listing_id}/chat", {"body": "Thank you."})
        # The history stays with the property page, in order, in one thread.
        thread = tenant.get(f"/api/properties/{listing_id}/chat")[1]["consultation"]
        self.assertEqual(thread["id"], chat["id"])
        self.assertEqual([m["body"] for m in thread["messages"]],
                         ["Is the mutation paper up to date?", "Yes, it was renewed this year.", "Thank you."])
        self.assertEqual([m["senderName"] for m in thread["messages"]], ["Sumaiya Islam", "Adv. Sarah Rahman", "Sumaiya Islam"])
        # Nobody else can read or write in the chat.
        for email in ("tenant@pfb.test", "advocate2@pfb.test"):
            other = self.client(email)
            self.assertEqual(other.get(f"/api/consultations/{chat['id']}")[0], 403)
            self.assertEqual(other.post(f"/api/consultations/{chat['id']}/messages", {"body": "Let me in"})[0], 403)
        self.assertEqual(self.client("owner@pfb.test").get(f"/api/consultations/{chat['id']}")[0], 403)

    def test_pb22_buyer_books_a_free_slot_and_it_cannot_be_booked_twice(self):
        tenant = self.client("tenant@pfb.test")
        advocate_id = self.advocate_id()
        slots = tenant.get(f"/api/advocates/{advocate_id}/slots")[1]["slots"]
        self.assertGreater(len(slots), 10)
        self.assertEqual(slots, sorted(set(slots)))
        with self.db() as connection:
            taken = [row[0] for row in connection.execute(
                "SELECT slot_start FROM consultations WHERE advocate_id = ? AND status IN ('requested', 'confirmed') "
                "AND slot_start IS NOT NULL", (advocate_id,))]
        self.assertTrue(taken)
        self.assertFalse(set(taken) & set(slots))  # slots already asked for are not offered
        for slot in slots:
            self.assertNotEqual(date.fromisoformat(slot[:10]).weekday(), 4)  # closed on Fridays

        (status, booking), slot = self.book(tenant)
        self.assertEqual((status, booking["state"], booking["slotStart"], booking["fee"]), (201, "awaiting_advocate", slot, 500), booking)
        self.assertNotIn(slot, tenant.get(f"/api/advocates/{advocate_id}/slots")[1]["slots"])
        payload = {"propertyId": self.property_id(self.VERIFIED), "advocateId": advocate_id, "slotStart": slot}
        status, body = self.client("tenant2@pfb.test").post("/api/consultations", payload)
        self.assertEqual(status, 409)
        self.assertIn("slotStart", body["fields"])
        # Times that are not real slots are refused too.
        for bad in ("2020-01-01T10:00", slot[:11] + "03:00", "tomorrow"):
            self.assertIn(tenant.post("/api/consultations", {**payload, "slotStart": bad})[0], (400, 409), bad)
        # The same time is still free with another advocate; cancelling gives a slot back.
        self.assertIn(slot, tenant.get(f"/api/advocates/{self.advocate_id('advocate2@pfb.test')}/slots")[1]["slots"])
        self.assertEqual(tenant.post(f"/api/consultations/{booking['id']}/cancel")[1]["state"], "cancelled")
        self.assertIn(slot, tenant.get(f"/api/advocates/{advocate_id}/slots")[1]["slots"])

    def test_pb23_advocate_confirms_or_refuses_and_adds_follow_up_notes(self):
        tenant = self.client("tenant@pfb.test")
        advocate = self.client("advocate@pfb.test")
        (_, first), _ = self.book(tenant, 0)
        (_, second), second_slot = self.book(tenant, 1)
        # Only the advocate who was asked can answer.
        for client in (tenant, self.client("advocate2@pfb.test")):
            self.assertEqual(client.post(f"/api/consultations/{first['id']}/respond", {"decision": "confirmed"})[0], 403)
        self.assertEqual(advocate.post(f"/api/consultations/{second['id']}/respond", {"decision": "refused"})[0], 400)
        status, body = advocate.post(f"/api/consultations/{second['id']}/respond", {"decision": "refused", "reason": "I am in court that morning."})
        self.assertEqual((status, body["state"]), (200, "refused"))
        self.assertIn(second_slot, tenant.get(f"/api/advocates/{self.advocate_id()}/slots")[1]["slots"])  # slot is free again
        status, body = advocate.post(f"/api/consultations/{first['id']}/respond", {"decision": "confirmed"})
        self.assertEqual((status, body["state"]), (200, "awaiting_payment"))
        self.assertEqual(advocate.post(f"/api/consultations/{first['id']}/respond", {"decision": "refused", "reason": "Changed my mind"})[0], 409)

        # Notes come after the session, so the booking must be paid first.
        notes = "Ask for the original deed and the latest tax receipt before paying."
        self.assertEqual(advocate.post(f"/api/consultations/{first['id']}/complete", {"notes": notes})[0], 409)
        tenant.post(f"/api/consultations/{first['id']}/pay", {"method": "bkash", "account": "01712345678"})
        self.assertEqual(advocate.post(f"/api/consultations/{first['id']}/complete", {"notes": "short"})[0], 400)
        self.assertEqual(tenant.post(f"/api/consultations/{first['id']}/complete", {"notes": notes})[0], 403)
        status, body = advocate.post(f"/api/consultations/{first['id']}/complete", {"notes": notes})
        self.assertEqual((status, body["state"]), (200, "completed"))
        # The notes show in the buyer's dashboard.
        mine = {c["id"]: c for c in tenant.get("/api/consultations")[1]["consultations"]}
        self.assertEqual((mine[first["id"]]["state"], mine[first["id"]]["followUpNotes"]), ("completed", notes))
        self.assertEqual(mine[second["id"]]["followUpNotes"], "I am in court that morning.")

    def test_pb24_payment_confirms_the_booking_and_a_failed_payment_is_clear(self):
        tenant = self.client("tenant@pfb.test")
        advocate = self.client("advocate@pfb.test")
        (_, booking), _ = self.book(tenant)
        pay_url = f"/api/consultations/{booking['id']}/pay"
        good = {"method": "bkash", "account": "01712345678"}
        self.assertEqual(tenant.post(pay_url, good)[0], 409)  # the advocate has not accepted yet
        advocate.post(f"/api/consultations/{booking['id']}/respond", {"decision": "confirmed"})
        for bad in ({"method": "cash", "account": "01712345678"}, {"method": "bkash", "account": "12345"}, {"method": "card", "account": "4111"}):
            status, body = tenant.post(pay_url, bad)
            self.assertEqual(status, 400, bad)
            self.assertTrue(body["fields"])
        self.assertEqual(self.client("tenant2@pfb.test").post(pay_url, good)[0], 403)

        status, body = tenant.post(pay_url, {"method": "nagad", "account": "01712340000"})
        self.assertEqual(status, 402)
        self.assertIn("Payment failed", body["error"])
        self.assertIn("No money was taken", body["error"])
        self.assertEqual(tenant.get(f"/api/consultations/{booking['id']}")[1]["state"], "awaiting_payment")

        status, body = tenant.post(pay_url, {"method": "card", "account": "4111 1111 1111 1111"})
        self.assertEqual((status, body["state"]), (200, "booked"), body)
        receipt = body["receipt"]
        self.assertEqual((receipt["amount"], receipt["method"]), (500, "Card"))
        self.assertRegex(receipt["transactionRef"], r"^PFB-[0-9A-F]{10}$")
        self.assertTrue(receipt["paidAt"])
        self.assertEqual(tenant.post(pay_url, good)[0], 409)  # cannot pay twice
        self.assertEqual(tenant.post(f"/api/consultations/{booking['id']}/cancel")[0], 409)
        with self.db() as connection:
            payments = [tuple(row) for row in connection.execute(
                "SELECT status, method, amount FROM payments WHERE consultation_id = ? ORDER BY id", (booking["id"],))]
        self.assertEqual(payments, [("failed", "nagad", 500), ("paid", "card", 500)])
        self.assertEqual(advocate.get(f"/api/consultations/{booking['id']}")[1]["receipt"]["transactionRef"], receipt["transactionRef"])

    def test_pb25_notifications_for_verification_results_and_new_requests(self):
        owner = self.client("owner@pfb.test")
        advocate = self.client("advocate@pfb.test")
        advocate.post("/api/notifications/read", {"all": True})
        owner.post("/api/notifications/read", {"all": True})
        self.assertEqual(owner.get("/api/notifications?count=1")[1], {"unread": 0})

        listing_id, request_id = self.verify_new_listing()
        # Advocates are told about the new request (both of them, but not the applicant who is not verified).
        # The demo data already holds one such notification for the first advocate.
        for email, expected in (("advocate@pfb.test", 2), ("advocate2@pfb.test", 1), ("applicant@pfb.test", 0)):
            titles = [n["title"] for n in self.client(email).get("/api/notifications")[1]["notifications"]]
            self.assertEqual(titles.count("New verification request"), expected, email)
        # The owner is told about the result, with a link to the request.
        status, body = owner.get("/api/notifications")
        self.assertEqual((status, body["unread"]), (200, 1))
        latest = body["notifications"][0]
        self.assertEqual((latest["title"], latest["isRead"], latest["link"]),
                         ("Your property is Document Verified", False, f"/owner/verification/{request_id}"))
        # Marking it read lowers the bell count; a user cannot mark someone else's notification.
        self.assertEqual(advocate.post("/api/notifications/read", {"id": latest["id"]})[1]["unread"], 1)
        self.assertEqual(owner.get("/api/notifications?count=1")[1], {"unread": 1})
        self.assertEqual(owner.post("/api/notifications/read", {"id": latest["id"]})[1], {"unread": 0})
        self.assertEqual(self.client().get("/api/notifications")[0], 401)

        # An issue found is reported to the owner too.
        issue_request = self.request_id("Easy, airy living by the lake")
        advocate.post(f"/api/verification-requests/{issue_request}/start-review")
        advocate.post(f"/api/verification-requests/{issue_request}/decision", {
            "decision": "issue_found", "notes": "The tax receipt is out of date.",
            "checklist": {"land_deed": "ok", "mutation": "ok", "tax_receipt": "problem", "ownership_history": "ok"},
        })
        self.assertEqual(owner.get("/api/notifications")[1]["notifications"][0]["title"], "An issue was found in your papers")

        # Consultation requests reach the advocate, and the answer reaches the buyer.
        tenant = self.client("tenant2@pfb.test")
        (_, booking), _ = self.book(tenant)
        note = advocate.get("/api/notifications")[1]["notifications"][0]
        self.assertEqual((note["title"], note["link"]), ("New consultation request", f"/consultations/{booking['id']}"))
        advocate.post(f"/api/consultations/{booking['id']}/respond", {"decision": "confirmed"})
        self.assertEqual(tenant.get("/api/notifications")[1]["notifications"][0]["title"], "Your consultation was accepted")

    def test_sprint3_demo_data_and_upgrade_from_an_older_database(self):
        tenant = self.client("tenant@pfb.test")
        states = sorted(c["state"] for c in tenant.get("/api/consultations")[1]["consultations"])
        self.assertEqual(states, ["awaiting_payment", "booked", "chat"])
        self.assertEqual(sorted(c["state"] for c in self.client("tenant2@pfb.test").get("/api/consultations")[1]["consultations"]),
                         ["awaiting_advocate", "completed"])
        self.assertGreater(tenant.get("/api/notifications?count=1")[1]["unread"], 0)

        old = Path(self.temp.name) / "old.sqlite3"
        connection = sqlite3.connect(old)
        connection.executescript(db.SCHEMA + db.HISTORY_SCHEMA + db.ADVOCATE_VERIFICATION_SCHEMA)
        connection.execute("INSERT INTO users (full_name, email, phone, password_hash, role, created_at) "
                           "VALUES ('Adv. Old', 'old@example.com', '01711111111', 'x', 'advocate', '2026-01-01')")
        connection.execute("INSERT INTO advocate_profiles (user_id, bar_council_id, specialization, added_at) "
                           "VALUES (1, 'DBC-1', 'Land', '2026-01-01')")
        connection.execute("PRAGMA user_version = 3")
        connection.commit()
        connection.close()
        self.assertFalse(db.initialize(old))
        with contextlib.closing(sqlite3.connect(old)) as connection:
            self.assertEqual(connection.execute("SELECT consultation_fee FROM advocate_profiles").fetchone()[0], 500)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM notifications").fetchone()[0], 0)
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)


class Sprint4Tests(ApiTestCase):
    """Rent agreements, saved searches with alerts, the admin report and listing reports (PB-26 to PB-33)."""

    RENT_LISTING = "Easy, airy living by the lake"   # owner@pfb.test, for rent, minimum lease 12 months
    SALE_LISTING = "Light-filled corner apartment"   # owner@pfb.test, for sale

    def new_agreement(self, **overrides):
        data = {"tenantEmail": "tenant2@pfb.test", "startDate": (date.today() + timedelta(days=10)).isoformat(),
                "leaseMonths": 12, "specialTerms": "No smoking inside the flat."}
        data.update(overrides)
        return self.client("owner@pfb.test").post(f"/api/properties/{self.property_id(self.RENT_LISTING)}/agreements", data)

    def test_pb26_agreement_is_filled_from_the_listing_and_downloads_as_pdf(self):
        owner = self.client("owner@pfb.test")
        status, body = self.new_agreement()
        self.assertEqual(status, 201, body)
        with self.db() as connection:
            rent = connection.execute("SELECT * FROM rent_details WHERE property_id = ?", (self.property_id(self.RENT_LISTING),)).fetchone()
        start = date.fromisoformat(body["startDate"])
        self.assertEqual((body["status"], body["landlord"]["name"], body["tenant"]["name"]), ("draft", "Nadia Rahman", "Sumaiya Islam"))
        self.assertEqual((body["monthlyRent"], body["securityDeposit"]), (rent["monthly_rent"], rent["security_deposit"]))
        self.assertEqual(body["endDate"], (date(start.year + 1, start.month, start.day) - timedelta(days=1)).isoformat())
        status, pdf = owner.get(f"/api/agreements/{body['id']}/pdf")
        self.assertEqual(status, 200)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        for text in (b"Rent agreement", b"Nadia Rahman", b"Sumaiya Islam", f"Tk {rent['monthly_rent']:,}".encode(),
                     body["startDate"].encode(), body["endDate"].encode(), b"No smoking inside the flat.", b"DRAFT"):
            self.assertIn(text, pdf)
        # Bad input is refused with clear messages.
        status, body = self.new_agreement(tenantEmail="owner2@pfb.test", leaseMonths=3, startDate="2020-01-01")
        self.assertEqual(status, 400)
        self.assertEqual(set(body["fields"]), {"leaseMonths", "startDate"})
        status, body = self.new_agreement(tenantEmail="owner2@pfb.test")
        self.assertEqual((status, list(body["fields"])), (400, ["tenantEmail"]))
        self.assertEqual(owner.post(f"/api/properties/{self.property_id(self.SALE_LISTING)}/agreements", {})[0], 409)
        self.assertEqual(self.client("owner2@pfb.test").post(
            f"/api/properties/{self.property_id(self.RENT_LISTING)}/agreements", {})[0], 403)

    def test_pb27_review_then_sign_and_no_signing_before_approval(self):
        owner, tenant, advocate = self.client("owner@pfb.test"), self.client("tenant2@pfb.test"), self.client("advocate2@pfb.test")
        _, draft = self.new_agreement()
        url = f"/api/agreements/{draft['id']}"
        self.assertEqual(tenant.post(f"{url}/sign", {"signature": "Sumaiya Islam"})[0], 409)
        self.assertEqual(advocate.get(url)[0], 403)  # advocates see it only once it is sent for review
        self.assertEqual(owner.post(f"{url}/submit")[1]["status"], "under_review")
        self.assertEqual(owner.put(url, {"tenantEmail": "tenant@pfb.test", "startDate": draft["startDate"], "leaseMonths": 12})[0], 409)
        self.assertEqual(owner.post(f"{url}/sign", {"signature": "Nadia Rahman"})[0], 409)
        self.assertEqual(tenant.post(f"{url}/review", {"decision": "approved"})[0], 403)
        self.assertIn(draft["id"], [a["id"] for a in advocate.get("/api/agreements")[1]["agreements"]])

        # Changes requested: back to Draft with notes, then the landlord fixes and resends it.
        self.assertEqual(advocate.post(f"{url}/review", {"decision": "changes_requested"})[0], 400)
        status, body = advocate.post(f"{url}/review", {"decision": "changes_requested", "notes": "Add the notice period for the deposit."})
        self.assertEqual((status, body["status"], body["reviewNotes"]), (200, "draft", "Add the notice period for the deposit."))
        status, body = owner.put(url, {"tenantEmail": "tenant2@pfb.test", "startDate": draft["startDate"], "leaseMonths": 24,
                                       "specialTerms": "Deposit returned within 30 days."})
        self.assertEqual((status, body["leaseMonths"]), (200, 24), body)
        owner.post(f"{url}/submit")
        status, body = advocate.post(f"{url}/review", {"decision": "approved"})
        self.assertEqual((status, body["status"], body["reviewer"]["name"]), (200, "approved", "Adv. Mahmud Karim"))

        # Signing: the typed name must match, both sides sign, then it is Signed.
        status, body = tenant.post(f"{url}/sign", {"signature": "Someone Else"})
        self.assertEqual(status, 400)
        self.assertIn("signature", body["fields"])
        self.assertEqual(self.client("tenant@pfb.test").post(f"{url}/sign", {"signature": "Rafi Chowdhury"})[0], 403)
        status, body = tenant.post(f"{url}/sign", {"signature": "  sumaiya   ISLAM "})
        self.assertEqual((status, body["status"], bool(body["tenantSignedAt"])), (200, "approved", True))
        self.assertEqual(tenant.post(f"{url}/sign", {"signature": "Sumaiya Islam"})[0], 409)
        status, body = owner.post(f"{url}/sign", {"signature": "Nadia Rahman"})
        self.assertEqual((status, body["status"]), (200, "signed"))
        pdf = tenant.get(f"{url}/pdf")[1]
        self.assertIn(b"Signed by both parties", pdf)
        self.assertIn(b"Reviewed and approved by Adv. Mahmud Karim", pdf)
        with self.db() as connection:
            steps = [tuple(r) for r in connection.execute(
                "SELECT old_value, new_value FROM audit_log WHERE target_type = 'rent_agreement' AND target_id = ? "
                "AND action_type = 'agreement_status_changed' ORDER BY id", (draft["id"],))]
        self.assertEqual(steps, [("draft", "under_review"), ("under_review", "draft"), ("draft", "under_review"),
                                 ("under_review", "approved"), ("approved", "signed")])

    def test_pb28_saved_search_alerts_when_a_matching_home_is_verified(self):
        tenant, tenant2 = self.client("tenant@pfb.test"), self.client("tenant2@pfb.test")
        status, body = tenant2.post("/api/saved-searches", {"filters": {"purpose": "rent", "area": "dhanmondi", "bedrooms": "2", "verified": "1"}})
        self.assertEqual(status, 201, body)
        self.assertEqual(body["filters"], {"purpose": "rent", "area": "dhanmondi", "bedrooms": "2"})
        self.assertEqual(tenant2.post("/api/saved-searches", {"filters": {"purpose": "rent", "area": "dhanmondi", "bedrooms": "2"}})[1]["id"], body["id"])
        nomatch = tenant2.post("/api/saved-searches", {"filters": {"purpose": "sale", "area": "Rangpur"}})[1]
        self.assertEqual(tenant2.post("/api/saved-searches", {"filters": {"type": "Castle"}})[0], 400)
        self.assertEqual(self.client("owner@pfb.test").post("/api/saved-searches", {"filters": {}})[0], 403)
        tenant.post("/api/notifications/read", {"all": True})
        tenant2.post("/api/notifications/read", {"all": True})

        # The lake flat (rent, Dhanmondi, 2 bedrooms) is verified: both tenants' searches match it.
        request_id = self.request_id(self.RENT_LISTING)
        advocate = self.client("advocate@pfb.test")
        advocate.post(f"/api/verification-requests/{request_id}/start-review")
        advocate.post(f"/api/verification-requests/{request_id}/decision", {
            "decision": "document_verified", "notes": "All papers are in order.",
            "checklist": {"land_deed": "ok", "mutation": "ok", "tax_receipt": "ok", "ownership_history": "ok"}})
        listing_id = self.property_id(self.RENT_LISTING)
        for client in (tenant, tenant2):
            alerts = [n for n in client.get("/api/notifications")[1]["notifications"] if n["kind"] == "saved_search"]
            self.assertEqual(len(alerts), 1)  # one alert per person, even with two matching searches
            self.assertEqual((alerts[0]["title"], alerts[0]["link"]), ("A new verified home matches your search", f"/property/{listing_id}"))
        searches = {s["id"]: s for s in tenant2.get("/api/saved-searches")[1]["savedSearches"]}
        self.assertGreaterEqual(searches[body["id"]]["verifiedMatches"], 1)
        self.assertEqual(searches[nomatch["id"]]["verifiedMatches"], 0)
        # Deleting works, and only for your own searches.
        self.assertEqual(tenant.delete(f"/api/saved-searches/{body['id']}")[0], 404)
        self.assertEqual(tenant2.delete(f"/api/saved-searches/{body['id']}")[0], 200)
        self.assertNotIn(body["id"], [s["id"] for s in tenant2.get("/api/saved-searches")[1]["savedSearches"]])

    def test_pb29_admin_report_counts_listings_and_advocate_work(self):
        status, report = self.client("admin@pfb.test").get("/api/admin/report")
        self.assertEqual(status, 200)
        listings = report["listings"]
        with self.db() as connection:
            count = lambda sql: connection.execute(sql).fetchone()[0]  # noqa: E731
            active = count("SELECT COUNT(*) FROM properties WHERE listing_status = 'active'")
            verified = count("SELECT COUNT(*) FROM properties WHERE listing_status = 'active' AND verification_status = 'document_verified'")
            rent = count("SELECT COUNT(*) FROM properties WHERE listing_status = 'active' AND listing_type = 'rent'")
        self.assertEqual((listings["active"], listings["verified"], listings["unverified"]), (active, verified, active - verified))
        self.assertEqual((listings["rent"], listings["sale"]), (rent, active - rent))
        self.assertEqual(sum(v["verified"] + v["unverified"] for v in listings["byType"].values()), active)
        self.assertEqual(sum(listings["badgeLevels"].values()), verified)
        work = {a["name"]: a for a in report["advocates"]}
        self.assertEqual(set(work), {"Adv. Sarah Rahman", "Adv. Mahmud Karim"})  # not the applicant who is not verified
        self.assertEqual(work["Adv. Mahmud Karim"]["inReview"], 1)
        self.assertGreater(report["verification"]["waitingForAdvocate"], 0)
        self.assertEqual(report["agreementsToReview"], 1)
        self.assertEqual(report["listingReports"]["open"], 3)
        for email in ("owner@pfb.test", "advocate@pfb.test", "tenant@pfb.test"):
            self.assertEqual(self.client(email).get("/api/admin/report")[0], 403)

    def test_pb30_report_a_listing_and_admin_removes_or_dismisses(self):
        tenant, owner, admin = self.client("tenant2@pfb.test"), self.client("owner@pfb.test"), self.client("admin@pfb.test")
        listing_id = self.property_id(self.SALE_LISTING)
        url = f"/api/properties/{listing_id}/reports"
        self.assertEqual(tenant.post(url, {"reason": "other"})[0], 400)  # "other" needs details
        self.assertEqual(tenant.post(url, {"reason": "nonsense"})[0], 400)
        self.assertEqual(tenant.post(url, {"reason": "fake", "details": "Photos are copied from another website."})[0], 201)
        self.assertEqual(tenant.post(url, {"reason": "fake"})[0], 409)  # one open report per person
        self.assertEqual(owner.post(url, {"reason": "fake"})[0], 403)  # not your own listing
        self.assertEqual(self.client().post(url, {"reason": "fake"})[0], 401)
        self.assertEqual(self.client("tenant@pfb.test").post(url, {"reason": "duplicate"})[0], 201)

        reports = admin.get("/api/admin/listing-reports")[1]["reports"]
        mine = [r for r in reports if r["property"]["id"] == listing_id]
        self.assertEqual((len(mine), mine[0]["openForListing"]), (2, 2))
        self.assertEqual(self.client("advocate@pfb.test").get("/api/admin/listing-reports")[0], 403)
        self.assertEqual(admin.post(f"/api/admin/listing-reports/{mine[0]['id']}/resolve", {"action": "remove"})[0], 400)
        status, body = admin.post(f"/api/admin/listing-reports/{mine[0]['id']}/resolve", {"action": "remove", "note": "Photos are copied."})
        self.assertEqual((status, body["status"], body["property"]["listingStatus"]), (200, "removed", "removed"))
        # The listing leaves the search results, and both reports on it are closed.
        titles = [p["title"] for p in self.client().get("/api/properties")[1]["properties"]]
        self.assertNotIn(self.SALE_LISTING, titles)
        self.assertEqual(self.client().get(f"/api/properties/{listing_id}")[0], 404)
        self.assertEqual([r for r in admin.get("/api/admin/listing-reports")[1]["reports"] if r["property"]["id"] == listing_id], [])
        self.assertEqual(admin.post(f"/api/admin/listing-reports/{mine[1]['id']}/resolve", {"action": "dismiss"})[0], 409)
        self.assertEqual(owner.get("/api/notifications")[1]["notifications"][0]["title"], "Your listing was removed")

        # Dismissing keeps the listing online.
        other = next(r for r in admin.get("/api/admin/listing-reports")[1]["reports"] if r["property"]["title"] == "Old Dhaka family house in Wari")
        status, body = admin.post(f"/api/admin/listing-reports/{other['id']}/resolve", {"action": "dismiss"})
        self.assertEqual((status, body["status"], body["property"]["listingStatus"]), (200, "dismissed", "active"))

    def test_pb31_pages_are_built_for_small_screens(self):
        guest = self.client()
        status, page = guest.get("/")
        self.assertIn(b'name="viewport" content="width=device-width, initial-scale=1"', page)
        css = guest.get("/css/app.css")[1]
        self.assertIn(b"@media (max-width: 600px)", css)
        script = guest.get("/js/ui.js")[1]
        self.assertIn(b'loading="lazy"', script)   # photos load only when they scroll into view
        self.assertIn(b"w=${width}", script)        # the photo size can be chosen per page
        self.assertIn(b", 640)}", guest.get("/js/views/home.js")[1])  # cards ask for smaller photos than the listing page

    def test_sprint4_demo_data_and_upgrade_from_an_older_database(self):
        statuses = sorted(a["status"] for a in self.client("admin@pfb.test").get("/api/agreements")[1]["agreements"])
        self.assertEqual(statuses, ["approved", "under_review"])
        tenant_agreement = self.client("tenant@pfb.test").get("/api/agreements")[1]["agreements"][0]
        self.assertEqual((tenant_agreement["status"], tenant_agreement["canSign"]), ("approved", True))
        self.assertEqual(len(self.client("tenant@pfb.test").get("/api/saved-searches")[1]["savedSearches"]), 2)

        old = Path(self.temp.name) / "old.sqlite3"
        connection = sqlite3.connect(old)
        connection.executescript(db.SCHEMA + db.HISTORY_SCHEMA + db.ADVOCATE_VERIFICATION_SCHEMA + db.SPRINT3_SCHEMA)
        connection.execute("PRAGMA user_version = 4")
        connection.commit()
        connection.close()
        self.assertFalse(db.initialize(old))
        with contextlib.closing(sqlite3.connect(old)) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            columns = {row[1] for row in connection.execute("PRAGMA table_info(rent_agreements)")}
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
        self.assertTrue({"saved_searches", "listing_reports"} <= tables)
        self.assertTrue({"lease_months", "landlord_signed_at", "tenant_signed_at", "review_notes"} <= columns)


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
