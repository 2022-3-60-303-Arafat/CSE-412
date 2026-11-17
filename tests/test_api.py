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
JPG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP_BYTES = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 64


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

    def search_all(self, query=""):
        """Every listing a search finds, walking through all its pages (12 per page)."""
        found, page = [], 1
        separator = "&" if query else ""
        while True:
            status, body = self.get(f"/api/properties?{query}{separator}page={page}")
            assert status == 200, body
            found += body["properties"]
            if page >= body["pages"]:
                return found
            page += 1

    def upload_photo(self, property_id, name, data, content_type="image/png"):
        return self.call("POST", f"/api/properties/{property_id}/images?name={name}", raw=data, content_type=content_type)


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
        # Listing photos go to the temporary folder too, never into the real public/uploads.
        self.config = server.Config(data_dir=Path(self.temp.name), photo_dir=Path(self.temp.name) / "photos",
                                    avatar_dir=Path(self.temp.name) / "avatars", quiet=True)
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
        verified = self.client().search_all("verified=1")
        self.assertNotIn(property_id, [p["id"] for p in verified])

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
        verified = self.client().search_all("verified=1")
        self.assertIn(property_id, [p["id"] for p in verified])
        self.assertTrue(all(p["verificationStatus"] == "document_verified" for p in verified))

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
        levels = {p["badgeLevel"] for p in self.client().search_all("verified=1")}
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
        tenant.post(f"/api/consultations/{first['id']}/pay", {"method": "bkash", "account": "01712345678", "pin": "12345"})
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
        good = {"method": "bkash", "account": "01712345678", "pin": "12345"}
        self.assertEqual(tenant.post(pay_url, good)[0], 409)  # the advocate has not accepted yet
        advocate.post(f"/api/consultations/{booking['id']}/respond", {"decision": "confirmed"})
        for bad in ({"method": "cash", "account": "01712345678"}, {"method": "bkash", "account": "12345"}, {"method": "card", "account": "4111"}):
            status, body = tenant.post(pay_url, bad)
            self.assertEqual(status, 400, bad)
            self.assertTrue(body["fields"])
        self.assertEqual(self.client("tenant2@pfb.test").post(pay_url, good)[0], 403)

        status, body = tenant.post(pay_url, {"method": "nagad", "account": "01712340000", "pin": "1234"})
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
        titles = [p["title"] for p in self.client().search_all()]
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


class SearchFilterTests(ApiTestCase):
    """Search by district and furnished, with 12 homes per page. Filters are plain GET parameters."""

    def count_active(self, where):
        with self.db() as connection:
            return connection.execute(
                f"SELECT COUNT(*) FROM properties WHERE listing_status = 'active' AND {where}").fetchone()[0]

    def test_district_and_furnished_filters(self):
        guest = self.client()
        sylhet = self.count_active("city = 'Sylhet'")
        furnished = self.count_active("furnished = 1")
        unfurnished = self.count_active("furnished = 0")
        dhaka_furnished_rent = self.count_active("city = 'Dhaka' AND furnished = 1 AND listing_type = 'rent'")
        self.assertTrue(sylhet and furnished and unfurnished and dhaka_furnished_rent)

        homes = guest.search_all("city=Sylhet")
        self.assertEqual(len(homes), sylhet)
        self.assertTrue(all(p["city"] == "Sylhet" for p in homes))
        homes = guest.search_all("furnished=yes")
        self.assertEqual(len(homes), furnished)
        self.assertTrue(all(p["furnished"] for p in homes))
        homes = guest.search_all("furnished=no")
        self.assertEqual(len(homes), unfurnished)
        self.assertFalse(any(p["furnished"] for p in homes))
        # Filters combine: district + furnished + rent, then bedrooms and a rent range on top.
        self.assertEqual(len(guest.search_all("purpose=rent&city=Dhaka&furnished=yes")), dhaka_furnished_rent)
        homes = guest.search_all("purpose=rent&city=Dhaka&furnished=yes&bedrooms=2&minPrice=20000&maxPrice=200000")
        self.assertTrue(all(p["listingType"] == "rent" and p["city"] == "Dhaka" and p["furnished"]
                            and p["bedrooms"] >= 2 and 20000 <= p["amount"] <= 200000 for p in homes))
        # The area text still narrows a district.
        self.assertTrue(all("Gulshan" in p["areaName"] + p["address"] for p in guest.search_all("city=Dhaka&area=Gulshan")))
        self.assertEqual(guest.get("/api/properties?city=Sylhet&area=Gulshan")[1]["total"], 0)

    def test_wrong_filter_values_get_clear_errors(self):
        guest = self.client()
        for query, field in (("city=Atlantis", "city"), ("furnished=maybe", "furnished"),
                             ("page=0", "page"), ("page=abc", "page"), ("purpose=lease", "purpose")):
            status, body = guest.get(f"/api/properties?{query}")
            self.assertEqual(status, 400, query)
            self.assertIn(field, body["fields"], query)

    def test_twelve_homes_per_page(self):
        guest = self.client()
        status, first = guest.get("/api/properties")
        self.assertEqual(status, 200)
        self.assertEqual((first["total"], first["page"], first["pageSize"], first["pages"]), (38, 1, 12, 4))
        pages = [first] + [guest.get(f"/api/properties?page={n}")[1] for n in (2, 3, 4)]
        self.assertEqual([len(p["properties"]) for p in pages], [12, 12, 12, 2])
        self.assertEqual([p["page"] for p in pages], [1, 2, 3, 4])
        ids = [home["id"] for p in pages for home in p["properties"]]
        self.assertEqual(len(set(ids)), 38)   # every home once: none on two pages, none missing
        # The pages follow the chosen sort order all the way through.
        prices = [home["amount"] for home in guest.search_all("purpose=sale&sort=price_asc")]
        self.assertGreater(len(prices), 12)
        self.assertEqual(prices, sorted(prices))
        # A page past the end shows the last page; a filtered search has its own page count.
        _, past = guest.get("/api/properties?page=99")
        self.assertEqual((past["page"], len(past["properties"])), (4, 2))
        _, sylhet = guest.get("/api/properties?city=Sylhet&page=5")
        self.assertEqual((sylhet["page"], sylhet["pages"]), (1, 1))
        _, none = guest.get("/api/properties?city=Sylhet&area=Gulshan")
        self.assertEqual((none["total"], none["page"], none["pages"], none["properties"]), (0, 1, 1, []))

    def test_turning_pages_is_not_saved_as_another_search(self):
        tenant = self.client("tenant2@pfb.test")
        before = len(tenant.get("/api/history")[1]["searches"])
        tenant.get("/api/properties?city=Dhaka&furnished=no")
        tenant.get("/api/properties?city=Dhaka&furnished=no&page=2")
        searches = tenant.get("/api/history")[1]["searches"]
        self.assertEqual(len(searches), before + 1)
        self.assertEqual(searches[0]["filters"], {"city": "Dhaka", "furnished": "no"})
        self.assertEqual(searches[0]["resultCount"], self.count_active("city = 'Dhaka' AND furnished = 0"))

    def test_saved_searches_use_district_and_furnished(self):
        tenant = self.client("tenant2@pfb.test")
        status, body = tenant.post("/api/saved-searches",
                                   {"filters": {"purpose": "rent", "city": "Dhaka", "furnished": "yes", "page": "3"}})
        self.assertEqual(status, 201, body)
        self.assertEqual(body["filters"], {"purpose": "rent", "city": "Dhaka", "furnished": "yes"})  # the page is not a filter
        self.assertEqual(tenant.post("/api/saved-searches", {"filters": {"city": "Atlantis"}})[0], 400)
        self.assertEqual(tenant.post("/api/saved-searches", {"filters": {"furnished": "maybe"}})[0], 400)
        # The alert check for saved searches agrees with the search itself.
        from pfb.sprint4 import matches
        row = {"listing_type": "rent", "property_type": "Apartment", "city": "Dhaka", "furnished": 0,
               "area_name": "Banani", "address": "Road 1", "amount": 30000, "bedrooms": 2}
        self.assertFalse(matches({"furnished": "yes"}, row))
        self.assertTrue(matches({"furnished": "no", "city": "Dhaka"}, row))
        self.assertFalse(matches({"city": "Sylhet"}, row))

    def test_search_page_has_the_new_filters_and_page_buttons(self):
        script = self.client().get("/js/views/home.js")[1]
        for text in (b'name="city"', b'name="furnished"', b"'furnished'", b"data-page", b"params.set('page', page)"):
            self.assertIn(text, script)


class Sprint5Tests(ApiTestCase):
    """PB-34 to PB-43: site visits, phone OTP, bKash/Nagad, map search, compare, duplicates, price guide, reviews, rent."""

    def notification_titles(self, client):
        return [n["title"] for n in client.get("/api/notifications")[1]["notifications"]]

    def new_owner(self, email="new.owner@pfb.test", phone="01755512345"):
        client = self.client()
        status, body = client.post("/api/auth/signup", {"fullName": "New Owner", "email": email, "phone": phone,
                                                         "password": "Secret123", "role": "owner"})
        self.assertEqual(status, 201, body)
        return client, body["user"]

    def confirm_phone(self, client):
        status, body = client.post("/api/phone/send-code", {})
        self.assertEqual(status, 200, body)
        status, body = client.post("/api/phone/verify", {"code": body["demoCode"]})
        self.assertEqual(status, 200, body)
        return body["user"]

    # ---------------------------------------------------------------- PB-34 site visits

    def test_pb34_tenant_books_a_visit_and_the_owner_answers(self):
        tenant, tenant2 = self.client("tenant@pfb.test"), self.client("tenant2@pfb.test")
        owner = self.client("owner@pfb.test")
        listing = self.property_id("Sunny apartment in Banasree")
        status, body = tenant.get(f"/api/properties/{listing}/visit-slots")
        self.assertEqual(status, 200)
        self.assertIsNone(body["myVisit"])
        self.assertEqual(len(body["slots"]), 14 * 8)   # 14 days, 8 one-hour slots a day
        slot = body["slots"][3]

        status, body = tenant.post(f"/api/properties/{listing}/visits", {"slotStart": slot, "note": "After office, please."})
        self.assertEqual(status, 201, body)
        visit = body["visit"]
        self.assertEqual((visit["status"], visit["role"], visit["property"]["address"]), ("requested", "tenant", None))
        self.assertNotIn("phone", visit["owner"])   # contact details only after the owner confirms
        # The slot is gone for everyone, and one tenant holds one open visit per home.
        self.assertNotIn(slot, tenant2.get(f"/api/properties/{listing}/visit-slots")[1]["slots"])
        self.assertEqual(tenant2.post(f"/api/properties/{listing}/visits", {"slotStart": slot})[0], 409)
        other_slot = tenant.get(f"/api/properties/{listing}/visit-slots")[1]["slots"][0]
        self.assertEqual(tenant.post(f"/api/properties/{listing}/visits", {"slotStart": other_slot})[0], 409)
        self.assertEqual(tenant.post(f"/api/properties/{listing}/visits", {"slotStart": "2020-01-01T10:00"})[0], 409)
        # Only tenants book; owners cannot book a visit to any home, guests must log in.
        self.assertEqual(owner.post(f"/api/properties/{listing}/visits", {"slotStart": other_slot})[0], 403)
        self.assertEqual(self.client().get(f"/api/properties/{listing}/visit-slots")[0], 401)
        self.assertIn("New visit request", self.notification_titles(owner))

        # The owner sees the request; another owner cannot answer it.
        visits = owner.get("/api/visits")[1]["visits"]
        mine = next(v for v in visits if v["id"] == visit["id"])
        self.assertEqual((mine["role"], mine["tenant"]["name"], mine["note"]), ("owner", "Rafi Chowdhury", "After office, please."))
        self.assertEqual(self.client("owner2@pfb.test").post(f"/api/visits/{visit['id']}/respond", {"decision": "confirmed"})[0], 403)
        self.assertEqual(owner.post(f"/api/visits/{visit['id']}/respond", {"decision": "declined"})[0], 400)  # a reason is needed
        status, body = owner.post(f"/api/visits/{visit['id']}/respond", {"decision": "confirmed"})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["visit"]["status"], "confirmed")
        self.assertEqual(body["visit"]["tenant"]["phone"], "01710000004")
        self.assertEqual(owner.post(f"/api/visits/{visit['id']}/respond", {"decision": "declined", "reply": "Sorry, busy."})[0], 409)
        mine = next(v for v in tenant.get("/api/visits")[1]["visits"] if v["id"] == visit["id"])
        self.assertEqual((mine["owner"]["phone"], mine["property"]["address"]), ("01710000002", "Block C, Banasree, Dhaka"))
        self.assertIn("Your visit is confirmed", self.notification_titles(tenant))

        # The tenant cancels: the slot is free again and the owner is told.
        self.assertEqual(tenant2.post(f"/api/visits/{visit['id']}/cancel")[0], 403)
        status, body = tenant.post(f"/api/visits/{visit['id']}/cancel")
        self.assertEqual((status, body["visit"]["status"]), (200, "cancelled"))
        self.assertIn(slot, tenant2.get(f"/api/properties/{listing}/visit-slots")[1]["slots"])
        self.assertIn("A visit was cancelled", self.notification_titles(owner))
        self.assertEqual(tenant.post(f"/api/visits/{visit['id']}/cancel")[0], 409)

    def test_pb34_demo_visits_and_declining(self):
        owner2 = self.client("owner2@pfb.test")
        visits = owner2.get("/api/visits")[1]["visits"]
        self.assertEqual(sorted(v["status"] for v in visits), ["confirmed", "requested"])
        waiting = next(v for v in visits if v["status"] == "requested")
        status, body = owner2.post(f"/api/visits/{waiting['id']}/respond", {"decision": "declined", "reply": "The flat is let already."})
        self.assertEqual((status, body["visit"]["status"], body["visit"]["ownerReply"]), (200, "declined", "The flat is let already."))
        self.assertIn("Your visit request was declined", self.notification_titles(self.client("tenant@pfb.test")))
        self.assertEqual(self.client("admin@pfb.test").get("/api/visits")[0], 403)

    # ---------------------------------------------------------------- PB-35 phone OTP

    def test_pb35_owner_confirms_phone_before_publishing(self):
        owner, user = self.new_owner()
        self.assertFalse(user["phoneVerified"])
        status, body = owner.post("/api/properties", rent_listing())
        self.assertEqual(status, 403)
        self.assertIn("Confirm your mobile number", body["error"])

        self.assertEqual(owner.post("/api/phone/send-code", {"phone": "12345"})[0], 400)
        status, sent = owner.post("/api/phone/send-code", {"phone": "+8801755599999"})
        self.assertEqual(status, 200, sent)
        self.assertEqual(sent["phone"], "017*****999")
        self.assertRegex(sent["demoCode"], r"^\d{6}$")
        self.assertEqual(owner.post("/api/phone/send-code", {})[0], 429)   # wait a minute between codes
        wrong = "000000" if sent["demoCode"] != "000000" else "111111"
        status, body = owner.post("/api/phone/verify", {"code": wrong})
        self.assertEqual((status, body["error"]), (400, "Wrong code. 4 tries left."))
        status, body = owner.post("/api/phone/verify", {"code": sent["demoCode"]})
        self.assertEqual(status, 200, body)
        self.assertTrue(body["user"]["phoneVerified"])
        self.assertEqual(body["user"]["phone"], "01755599999")   # the confirmed number is saved on the account
        self.assertTrue(owner.get("/api/auth/me")[1]["user"]["phoneVerified"])

        status, body = owner.post("/api/properties", rent_listing())
        self.assertEqual(status, 201, body)
        self.assertTrue(body["property"]["owner"]["phoneVerified"])
        self.assertEqual(owner.post("/api/phone/send-code", {})[0], 409)   # already confirmed
        with self.db() as connection:
            stored = connection.execute("SELECT code_hash FROM phone_verifications").fetchone()[0]
            actions = [r[0] for r in connection.execute("SELECT action_type FROM audit_log WHERE action_type = 'phone_verified'")]
        self.assertNotIn(sent["demoCode"], stored)   # only a hash of the code is kept
        self.assertEqual(actions, ["phone_verified"])

    def test_pb35_wrong_codes_expiry_and_roles(self):
        owner, _ = self.new_owner()
        code = owner.post("/api/phone/send-code", {})[1]["demoCode"]
        wrong = "000000" if code != "000000" else "111111"
        for left in (4, 3, 2, 1):
            self.assertEqual(owner.post("/api/phone/verify", {"code": wrong})[1]["error"], f"Wrong code. {left} {'try' if left == 1 else 'tries'} left.")
        self.assertEqual(owner.post("/api/phone/verify", {"code": wrong})[0], 429)
        self.assertEqual(owner.post("/api/phone/verify", {"code": code})[0], 429)   # blocked even with the right code
        # A new code after a minute works; an expired one does not.
        with self.db() as connection:
            connection.execute("UPDATE phone_verifications SET created_at = '2020-01-01T00:00:00+00:00'")
            connection.commit()
        code = owner.post("/api/phone/send-code", {})[1]["demoCode"]
        with self.db() as connection:
            connection.execute("UPDATE phone_verifications SET expires_at = '2020-01-01T00:00:00+00:00' WHERE verified_at IS NULL")
            connection.commit()
        status, body = owner.post("/api/phone/verify", {"code": code})
        self.assertEqual(status, 400)
        self.assertIn("expired", body["error"])
        self.assertEqual(self.client("tenant@pfb.test").post("/api/phone/send-code", {})[0], 403)
        self.assertEqual(self.client().post("/api/phone/verify", {"code": "123456"})[0], 401)
        # With an SMS gateway connected, the code is not shown on screen.
        other, _ = self.new_owner("other.owner@pfb.test", "01755512346")
        self.config.demo_sms = False
        try:
            status, body = other.post("/api/phone/send-code", {})
        finally:
            self.config.demo_sms = True
        self.assertEqual(status, 200)
        self.assertNotIn("demoCode", body)
        # Demo owners already confirmed their numbers and can publish.
        self.assertTrue(self.client("owner@pfb.test").get("/api/auth/me")[1]["user"]["phoneVerified"])

    # ---------------------------------------------------------------- PB-36 bKash / Nagad

    def test_pb36_wallet_payment_needs_a_pin_and_the_receipt_shows_the_wallet(self):
        tenant, advocate = self.client("tenant@pfb.test"), self.client("advocate@pfb.test")
        advocate_id = next(a["id"] for a in tenant.get("/api/advocates")[1]["advocates"] if a["name"] == "Adv. Sarah Rahman")
        slot = tenant.get(f"/api/advocates/{advocate_id}/slots")[1]["slots"][5]
        listing = self.property_id("A quiet home above the city")
        booking = tenant.post("/api/consultations", {"propertyId": listing, "advocateId": advocate_id, "slotStart": slot})[1]
        advocate.post(f"/api/consultations/{booking['id']}/respond", {"decision": "confirmed"})
        pay_url = f"/api/consultations/{booking['id']}/pay"
        for pin in (None, "12", "abcd", "123456"):
            payload = {"method": "bkash", "account": "01712345678"}
            if pin is not None:
                payload["pin"] = pin
            status, body = tenant.post(pay_url, payload)
            self.assertEqual(status, 400, pin)
            self.assertIn("pin", body["fields"])
        status, body = tenant.post(pay_url, {"method": "bkash", "account": "01712-345678", "pin": "54321"})
        self.assertEqual((status, body["state"]), (200, "booked"), body)
        self.assertEqual((body["receipt"]["method"], body["receipt"]["account"]), ("bKash", "017*****678"))
        self.assertRegex(body["receipt"]["transactionRef"], r"^PFB-[0-9A-F]{10}$")
        with self.db() as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(payments)")}
            stored = [tuple(r) for r in connection.execute("SELECT * FROM payments WHERE consultation_id = ?", (booking["id"],))]
        self.assertFalse(any("pin" in c for c in columns))   # the PIN is never stored
        self.assertNotIn("54321", str(stored))

    # ---------------------------------------------------------------- PB-37 map and near-me search

    def test_pb37_search_near_a_landmark_nearest_first(self):
        guest = self.client()
        status, body = guest.get("/api/landmarks")
        self.assertEqual(status, 200)
        self.assertIn("du", [l["id"] for l in body["landmarks"]])
        self.assertEqual(body["radii"], [1, 3, 5, 10])

        status, body = guest.get("/api/properties?near=du&radius=3")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["near"]["name"], "University of Dhaka")
        distances = [p["distanceKm"] for p in body["properties"]]
        self.assertTrue(distances)
        self.assertEqual(distances, sorted(distances))   # nearest first by default
        self.assertTrue(all(d <= 3 for d in distances))
        self.assertTrue(all(p["city"] == "Dhaka" for p in body["properties"]))
        wider = guest.get("/api/properties?near=du&radius=10")[1]["total"]
        self.assertGreater(wider, body["total"])
        # Other filters still apply, and another sort can be chosen.
        rents = guest.search_all("near=du&radius=10&purpose=rent&sort=price_asc")
        self.assertTrue(all(p["listingType"] == "rent" and p["distanceKm"] <= 10 for p in rents))
        self.assertEqual([p["amount"] for p in rents], sorted(p["amount"] for p in rents))
        # "Use my location" sends a point; it must be inside Bangladesh.
        status, body = guest.get("/api/properties?lat=22.3590&lng=91.8220&radius=5")
        self.assertEqual(status, 200)
        self.assertTrue(body["properties"] and all(p["city"] == "Chattogram" for p in body["properties"]))
        for query, field in (("near=mars", "near"), ("lat=51.5&lng=-0.12", "near"), ("lat=abc&lng=90", "near"),
                             ("near=du&radius=7", "radius"), ("sort=distance", "sort")):
            status, body = guest.get(f"/api/properties?{query}")
            self.assertEqual(status, 400, query)
            self.assertIn(field, body["fields"], query)

    def test_pb37_map_pins_and_owner_pin(self):
        guest = self.client()
        status, body = guest.get("/api/properties/map?purpose=rent")
        self.assertEqual(status, 200)
        total = guest.get("/api/properties?purpose=rent")[1]["total"]
        self.assertEqual(len(body["pins"]), total)   # every listing has a position (area centre at least)
        self.assertTrue(all(pin["lat"] and pin["lng"] and pin["listingType"] == "rent" for pin in body["pins"]))
        near = guest.get("/api/properties/map?near=buet&radius=1")[1]
        self.assertTrue(all(pin["distanceKm"] <= 1 for pin in near["pins"]))

        owner = self.client("owner@pfb.test")
        status, body = owner.post("/api/properties", rent_listing(latitude=23.7700, longitude=90.3800))
        self.assertEqual(status, 201, body)
        self.assertEqual((body["property"]["latitude"], body["property"]["longitude"]), (23.77, 90.38))
        listing_id = body["property"]["id"]
        status, body = owner.post("/api/properties", rent_listing(latitude=51.5, longitude=-0.12))
        self.assertEqual(status, 400)
        self.assertIn("latitude", body["fields"])
        # Without a pin, the area centre is used; moving the listing to another area moves it.
        status, body = owner.post("/api/properties", rent_listing(areaName="Gulshan 2"))
        self.assertEqual((body["property"]["latitude"], body["property"]["longitude"]), (23.7946, 90.4142))
        status, body = owner.put(f"/api/properties/{body['property']['id']}", rent_listing(areaName="Dhanmondi"))
        self.assertEqual((body["property"]["latitude"], body["property"]["longitude"]), (23.7461, 90.3742))
        # Editing other details keeps the owner's own pin.
        status, body = owner.put(f"/api/properties/{listing_id}", rent_listing(title="A new title for the pinned flat"))
        self.assertEqual((body["property"]["latitude"], body["property"]["longitude"]), (23.77, 90.38))

    def test_pb37_saved_search_near_a_landmark(self):
        tenant = self.client("tenant2@pfb.test")
        status, body = tenant.post("/api/saved-searches", {"filters": {"near": "du", "radius": "3", "purpose": "rent"}})
        self.assertEqual(status, 201, body)
        self.assertEqual(body["filters"], {"near": "du", "radius": "3", "purpose": "rent"})
        self.assertEqual(tenant.post("/api/saved-searches", {"filters": {"near": "mars"}})[0], 400)
        from pfb.sprint4 import matches
        row = {"listing_type": "rent", "property_type": "Apartment", "city": "Dhaka", "furnished": 0, "area_name": "Dhanmondi",
               "address": "Road 1", "amount": 30000, "bedrooms": 2, "latitude": 23.7461, "longitude": 90.3742}
        self.assertTrue(matches({"near": "du", "radius": "3"}, row))
        self.assertFalse(matches({"near": "du", "radius": "1"}, row))
        self.assertFalse(matches({"near": "sust", "radius": "10"}, row))

    # ---------------------------------------------------------------- PB-38 compare

    def test_pb38_compare_up_to_three_listings(self):
        guest = self.client()
        ids = [self.property_id(t) for t in ("A quiet home above the city", "Sunny apartment in Banasree",
                                              "The little studio with big light")]
        status, body = guest.get("/api/compare?ids=" + ",".join(map(str, ids)))
        self.assertEqual(status, 200, body)
        self.assertEqual([p["id"] for p in body["properties"]], ids)
        self.assertTrue(body["sameKind"])
        for item in body["properties"]:
            self.assertEqual(item["moveInCost"], item["rent"]["monthlyRent"] + item["rent"]["securityDeposit"])
            self.assertEqual(item["pricePerSqft"], round(item["amount"] / item["sizeSqft"]))
        cheapest = min(body["properties"], key=lambda p: p["amount"])["id"]
        biggest = max(body["properties"], key=lambda p: p["sizeSqft"])["id"]
        self.assertEqual((body["best"]["amount"], body["best"]["sizeSqft"]), ([cheapest], [biggest]))
        # A sale price and a rent are not compared with each other.
        sale = self.property_id("Garden mornings in a modern house")
        body = guest.get(f"/api/compare?ids={ids[0]},{sale}")[1]
        self.assertFalse(body["sameKind"])
        self.assertIsNone(body["best"]["amount"])
        # Removed listings are reported as missing; more than 3 or bad ids are refused.
        self.client("owner@pfb.test").delete(f"/api/properties/{ids[1]}")
        body = guest.get(f"/api/compare?ids={ids[0]},{ids[1]}")[1]
        self.assertEqual(([p["id"] for p in body["properties"]], body["missing"]), ([ids[0]], [ids[1]]))
        for query in ("", "ids=", "ids=1,2,3,4", "ids=a,b"):
            self.assertEqual(guest.get(f"/api/compare?{query}")[0], 400, query)

    # ---------------------------------------------------------------- PB-39 duplicate listings

    def test_pb39_copied_text_is_flagged_and_admin_removes_it(self):
        owner, owner2, admin = self.client("owner@pfb.test"), self.client("owner2@pfb.test"), self.client("admin@pfb.test")
        original = self.client().get(f"/api/properties/{self.property_id('Sunny apartment in Banasree')}")[1]
        self.assertGreater(len(original["description"]), 60)
        copied = original["description"].replace(".", "!", 1)
        status, body = owner2.post("/api/properties", rent_listing(title="Bright flat in Banasree", description=copied))
        self.assertEqual(status, 201, body)
        copy_id = body["property"]["id"]
        # The same owner reusing the text of their own other listing, and short texts, are not flagged.
        own = next(p for p in owner.get("/api/my/listings")[1]["properties"]
                   if p["id"] != original["id"] and len(p["description"]) > 60)
        owner.post("/api/properties", rent_listing(title="Second flat by the same owner", description=own["description"]))
        owner2.post("/api/properties", rent_listing(title="Short one", description="Nice flat near the market."))
        owner.post("/api/properties", rent_listing(title="Short two", description="Nice flat near the market."))

        status, body = admin.get("/api/admin/duplicate-flags")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["flags"]), 1)
        flag = body["flags"][0]
        self.assertEqual((flag["kind"], flag["listing"]["id"], flag["matchedListing"]["id"]), ("text", copy_id, original["id"]))
        self.assertGreaterEqual(flag["similarity"], 85)
        self.assertIn("Possible duplicate listing", self.notification_titles(admin))
        self.assertEqual(owner.get("/api/admin/duplicate-flags")[0], 403)

        status, body = admin.post(f"/api/admin/duplicate-flags/{flag['id']}/resolve", {"action": "remove"})
        self.assertEqual((status, body["flag"]["status"]), (200, "removed"), body)
        self.assertEqual(self.client().get(f"/api/properties/{copy_id}")[0], 404)
        self.assertIn("Your listing was removed", self.notification_titles(owner2))
        self.assertEqual(admin.post(f"/api/admin/duplicate-flags/{flag['id']}/resolve", {"action": "dismiss"})[0], 409)
        self.assertEqual(admin.get("/api/admin/duplicate-flags")[1]["flags"], [])
        self.assertEqual(admin.get("/api/admin/report")[1]["duplicateFlags"], {"open": 0, "dismissed": 0, "removed": 1})

    def test_pb39_reused_photo_is_flagged_and_can_be_dismissed(self):
        owner, owner2, admin = self.client("owner@pfb.test"), self.client("owner2@pfb.test"), self.client("admin@pfb.test")
        # Different texts, so only the photo can match.
        mine = owner.post("/api/properties", rent_listing(title="Owner one flat", description=""))[1]["property"]["id"]
        mine_too = owner.post("/api/properties", rent_listing(title="Owner one second flat", description=""))[1]["property"]["id"]
        theirs = owner2.post("/api/properties", rent_listing(title="Owner two flat", description=""))[1]["property"]["id"]
        photo = PNG_BYTES + b"same photo"
        self.assertEqual(owner.upload_photo(mine, "a.png", photo)[0], 201)
        self.assertEqual(owner.upload_photo(mine_too, "a.png", photo)[0], 201)   # own photo again: fine
        self.assertEqual(admin.get("/api/admin/duplicate-flags")[1]["flags"], [])
        self.assertEqual(owner2.upload_photo(theirs, "b.png", photo)[0], 201)
        flags = admin.get("/api/admin/duplicate-flags")[1]["flags"]
        self.assertEqual(sorted((f["kind"], f["listing"]["id"], f["matchedListing"]["id"]) for f in flags),
                         [("photo", theirs, mine), ("photo", theirs, mine_too)])
        self.assertEqual(flags[0]["similarity"], 100)
        status, body = admin.post(f"/api/admin/duplicate-flags/{flags[0]['id']}/resolve", {"action": "dismiss"})
        self.assertEqual((status, body["flag"]["status"]), (200, "dismissed"))
        self.assertEqual(self.client().get(f"/api/properties/{theirs}")[0], 200)   # dismissing keeps the listing
        self.assertEqual(admin.post(f"/api/admin/duplicate-flags/{flags[1]['id']}/resolve", {"action": "ban"})[0], 400)
        self.assertEqual(len(admin.get("/api/admin/duplicate-flags?status=all")[1]["flags"]), 2)

    # ---------------------------------------------------------------- PB-40 price guide

    def test_pb40_price_guide_and_listing_position(self):
        guest = self.client()
        status, body = guest.get("/api/price-guide?listingType=rent")
        self.assertEqual(status, 200)
        self.assertTrue(body["districts"])
        with self.db() as connection:
            rows = connection.execute(
                """SELECT p.id, p.city, p.bedrooms, rd.monthly_rent FROM properties p JOIN rent_details rd ON rd.property_id = p.id
                   WHERE p.listing_status = 'active' AND p.listing_type = 'rent'""").fetchall()
        for group in body["districts"]:
            amounts = [r[3] for r in rows if r[1] == group["city"] and r[2] == group["bedrooms"]]
            self.assertGreaterEqual(len(amounts), 3)
            self.assertEqual((group["count"], group["average"], group["lowest"], group["highest"]),
                             (len(amounts), round(sum(amounts) / len(amounts)), min(amounts), max(amounts)))
        self.assertTrue(all(g["count"] >= 3 for g in body["areas"]))
        self.assertEqual(guest.get("/api/price-guide?listingType=lease")[0], 400)
        self.assertTrue(all(g["city"] == "Sylhet" for g in guest.get("/api/price-guide?listingType=sale&city=Sylhet")[1]["districts"]))

        # A listing in a group with 3 or more other homes shows how far it is from their average.
        group = body["districts"][0]
        member = next(r for r in rows if r[1] == group["city"] and r[2] == group["bedrooms"])
        others = [r[3] for r in rows if r[1] == group["city"] and r[2] == group["bedrooms"] and r[0] != member[0]]
        guide = guest.get(f"/api/properties/{member[0]}")[1]["priceGuide"]
        if len(others) >= 3:
            average = round(sum(others) / len(others))
            self.assertEqual((guide["scope"], guide["count"], guide["average"]), ("district", len(others), average))
            self.assertEqual(guide["differencePercent"], round((member[3] - average) * 100 / average))
        self.assertIn("rent", self.client("admin@pfb.test").get("/api/admin/report")[1]["priceGuide"])

    # ---------------------------------------------------------------- PB-41 advocate reviews

    def test_pb41_client_rates_a_completed_consultation_once(self):
        tenant, tenant2 = self.client("tenant@pfb.test"), self.client("tenant2@pfb.test")
        done = next(c for c in tenant2.get("/api/consultations")[1]["consultations"] if c["state"] == "completed")
        self.assertIsNone(done["review"])
        url = f"/api/consultations/{done['id']}/review"
        self.assertEqual(tenant.post(url, {"rating": 5})[0], 403)
        for bad in ({"rating": 0}, {"rating": 6}, {"rating": "five"}, {}):
            self.assertEqual(tenant2.post(url, bad)[0], 400, bad)
        status, body = tenant2.post(url, {"rating": 4, "comment": "Clear advice on the deed."})
        self.assertEqual(status, 201, body)
        self.assertEqual((body["review"]["rating"], body["review"]["comment"]), (4, "Clear advice on the deed."))
        self.assertEqual(tenant2.post(url, {"rating": 1})[0], 409)
        # The rating shows in the Advocate Panel and on the advocate's reviews.
        advocate = next(a for a in tenant.get("/api/advocates")[1]["advocates"] if a["id"] == done["advocate"]["id"])
        self.assertEqual((advocate["rating"], advocate["reviewCount"]), (4.0, 1))
        reviews = self.client().get(f"/api/advocates/{advocate['id']}/reviews")[1]
        self.assertEqual(reviews["reviews"][0]["by"], "Sumaiya")   # first name only
        self.assertIn("New 4-star review", self.notification_titles(self.client("advocate2@pfb.test")))
        # Not completed yet: no rating.
        booked = next(c for c in tenant.get("/api/consultations")[1]["consultations"] if c["state"] == "booked")
        self.assertEqual(tenant.post(f"/api/consultations/{booked['id']}/review", {"rating": 5})[0], 409)

    # ---------------------------------------------------------------- PB-43 rent payments and reminders

    def sign_demo_agreement(self):
        tenant = self.client("tenant@pfb.test")
        agreement = next(a for a in tenant.get("/api/agreements")[1]["agreements"] if a["status"] == "approved")
        status, body = tenant.post(f"/api/agreements/{agreement['id']}/sign", {"signature": "Rafi Chowdhury"})
        self.assertEqual((status, body["status"]), (200, "signed"), body)
        return tenant, body

    def test_pb43_signing_creates_the_rent_schedule(self):
        tenant, agreement = self.sign_demo_agreement()
        status, body = tenant.get(f"/api/agreements/{agreement['id']}/payments")
        self.assertEqual(status, 200, body)
        payments = body["payments"]
        self.assertEqual(len(payments), 12)
        start = date.fromisoformat(agreement["startDate"])
        self.assertEqual(payments[0]["dueDate"], start.isoformat())
        from pfb.sprint5 import month_offset
        self.assertEqual([p["dueDate"] for p in payments], [month_offset(start, n).isoformat() for n in range(12)])
        self.assertTrue(all(p["amount"] == agreement["monthlyRent"] and p["status"] == "due" for p in payments))
        self.assertEqual((body["role"], body["summary"]["nextDue"]), ("tenant", start.isoformat()))
        self.assertIn("Your rent schedule is ready", self.notification_titles(tenant))
        # Only the two sides and admins see it.
        self.assertEqual(self.client("owner@pfb.test").get(f"/api/agreements/{agreement['id']}/payments")[1]["role"], "landlord")
        self.assertEqual(self.client("admin@pfb.test").get(f"/api/agreements/{agreement['id']}/payments")[0], 200)
        self.assertEqual(self.client("tenant2@pfb.test").get(f"/api/agreements/{agreement['id']}/payments")[0], 403)

    def test_pb43_reminders_and_paid_months(self):
        tenant, agreement = self.sign_demo_agreement()
        owner = self.client("owner@pfb.test")
        payments = tenant.get(f"/api/agreements/{agreement['id']}/payments")[1]["payments"]
        today = (datetime.now(timezone.utc) + timedelta(hours=6)).date()
        with self.db() as connection:   # make one month due in 2 days and one overdue
            connection.execute("UPDATE rent_payments SET due_date = ? WHERE id = ?", ((today + timedelta(days=2)).isoformat(), payments[0]["id"]))
            connection.execute("UPDATE rent_payments SET due_date = ? WHERE id = ?", ((today - timedelta(days=4)).isoformat(), payments[1]["id"]))
            connection.commit()
        titles = self.notification_titles(tenant)
        self.assertEqual((titles.count("Rent due soon"), titles.count("Rent is overdue")), (1, 1))
        self.assertEqual(self.notification_titles(owner).count("Rent not paid yet"), 1)
        titles = self.notification_titles(tenant)   # opening again does not repeat them
        self.assertEqual((titles.count("Rent due soon"), titles.count("Rent is overdue")), (1, 1))
        body = tenant.get(f"/api/agreements/{agreement['id']}/payments")[1]
        self.assertEqual(body["summary"]["overdue"], 1)

        overdue = payments[1]["id"]
        self.assertEqual(owner.post(f"/api/rent-payments/{overdue}/mark-paid", {})[0], 403)
        self.assertEqual(self.client("tenant2@pfb.test").post(f"/api/rent-payments/{overdue}/mark-paid", {})[0], 403)
        status, body = tenant.post(f"/api/rent-payments/{overdue}/mark-paid", {"note": "bKash TrxID 8N7A6B5C"})
        self.assertEqual((status, body["status"], body["overdue"]), (200, "marked_paid", False))
        self.assertEqual(tenant.post(f"/api/rent-payments/{overdue}/mark-paid", {})[0], 409)
        self.assertIn("Rent marked as paid", self.notification_titles(owner))
        self.assertEqual(tenant.post(f"/api/rent-payments/{overdue}/confirm")[0], 403)
        status, body = owner.post(f"/api/rent-payments/{overdue}/confirm")
        self.assertEqual((status, body["status"]), (200, "confirmed"))
        self.assertEqual(owner.post(f"/api/rent-payments/{overdue}/confirm")[0], 409)
        self.assertIn("Rent payment confirmed", self.notification_titles(tenant))
        # Cash handed over: the landlord confirms a month the tenant did not mark.
        self.assertEqual(owner.post(f"/api/rent-payments/{payments[2]['id']}/confirm")[1]["status"], "confirmed")
        summary = owner.get(f"/api/agreements/{agreement['id']}/payments")[1]["summary"]
        self.assertEqual((summary["confirmed"], summary["overdue"]), (2, 0))

    # ---------------------------------------------------------------- PB-42 Bangla, and the database upgrade

    def test_pb42_language_switch_is_served(self):
        guest = self.client()
        status, script = guest.get("/js/i18n.js")
        self.assertEqual(status, 200)
        for text in ("বাংলা".encode(), "বাড়ি খুঁজুন".encode(), b"localStorage", b"MutationObserver"):
            self.assertIn(text, script)
        self.assertIn(b"i18n.js", guest.get("/js/app.js")[1])

    def test_upgrade_from_a_version_6_database(self):
        old = Path(self.temp.name) / "old6.sqlite3"
        connection = sqlite3.connect(old)
        connection.executescript(db.SCHEMA + db.HISTORY_SCHEMA + db.ADVOCATE_VERIFICATION_SCHEMA + db.SPRINT3_SCHEMA
                                 + db.SPRINT4_SCHEMA + db.PHOTOS_SCHEMA)
        for user_id, email in ((1, "with@x.test"), (2, "without@x.test")):
            connection.execute("INSERT INTO users (id, full_name, email, phone, password_hash, role, created_at) "
                               "VALUES (?, 'O', ?, '01700000000', 'x', 'owner', '2026-01-01')", (user_id, email))
        connection.execute("INSERT INTO properties (owner_id, title, description, listing_type, property_type, price, area_name, "
                           "city, address, size_sqft, bedrooms, bathrooms, created_at, updated_at) VALUES "
                           "(1, 'Old', '', 'sale', 'House', 100, 'Mirpur', 'Dhaka', 'Road 1', 900, 2, 1, '2026-01-01', '2026-01-01')")
        connection.execute("PRAGMA user_version = 6")
        connection.commit()
        connection.close()
        self.assertFalse(db.initialize(old))
        with contextlib.closing(sqlite3.connect(old)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
            verified = dict(connection.execute("SELECT email, phone_verified_at IS NOT NULL FROM users").fetchall())
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        # An owner who already had listings keeps publishing; a new one confirms the phone first.
        self.assertEqual(verified, {"with@x.test": 1, "without@x.test": 0})
        self.assertTrue({"site_visits", "phone_verifications", "duplicate_flags", "reviews", "rent_payments"} <= tables)


class ProfileTests(ApiTestCase):
    """My profile: details, profile picture and password. Also the headers that let the map and location work."""

    def test_profile_details_are_saved(self):
        tenant = self.client("tenant@pfb.test")
        status, me = tenant.get("/api/profile")
        self.assertEqual(status, 200)
        self.assertEqual((me["fullName"], me["bio"], me["occupation"], me["avatarUrl"]), ("Rafi Chowdhury", "", "", None))
        self.assertIn("savedHomes", me["counts"])
        status, body = tenant.put("/api/profile", {"fullName": "Rafi Ahmed Chowdhury", "phone": "01710000004",
                                                    "occupation": "Teacher", "bio": "Looking for a 2-bed flat near Gulshan."})
        self.assertEqual(status, 200, body)
        self.assertEqual((body["fullName"], body["occupation"], body["bio"]), ("Rafi Ahmed Chowdhury", "Teacher", "Looking for a 2-bed flat near Gulshan."))
        self.assertEqual(tenant.get("/api/auth/me")[1]["user"]["fullName"], "Rafi Ahmed Chowdhury")
        status, body = tenant.put("/api/profile", {"fullName": "R", "phone": "123", "bio": "x" * 501})
        self.assertEqual(status, 400)
        self.assertTrue({"fullName", "phone", "bio"} <= set(body["fields"]))
        self.assertEqual(self.client().get("/api/profile")[0], 401)
        with self.db() as connection:
            details = connection.execute("SELECT details FROM audit_log WHERE action_type = 'profile_updated'").fetchone()[0]
        self.assertIn("name", details)

    def test_owner_changing_phone_must_confirm_again(self):
        owner = self.client("owner@pfb.test")
        self.assertTrue(owner.get("/api/profile")[1]["phoneVerified"])
        same = owner.put("/api/profile", {"fullName": "Nadia Rahman", "phone": "01710000002"})[1]
        self.assertTrue(same["phoneVerified"])   # saving without a new number keeps the confirmation
        changed = owner.put("/api/profile", {"fullName": "Nadia Rahman", "phone": "01799988877"})[1]
        self.assertFalse(changed["phoneVerified"])
        self.assertEqual(owner.post("/api/properties", rent_listing())[0], 403)

    def test_profile_picture_upload_replace_and_remove(self):
        owner = self.client("owner@pfb.test")
        status, body = owner.call("POST", "/api/profile/avatar?name=me.png", raw=PNG_BYTES, content_type="image/png")
        self.assertEqual(status, 201, body)
        first = body["avatarUrl"]
        self.assertRegex(first, r"^/uploads/avatars/[0-9a-f]{32}\.png$")
        self.assertEqual(self.client().get(first), (200, PNG_BYTES))
        self.assertEqual(owner.get("/api/auth/me")[1]["user"]["avatarUrl"], first)
        listing = owner.get("/api/my/listings")[1]["properties"][0]
        self.assertEqual(listing["owner"]["avatarUrl"], first)   # shown next to the owner's name on listings
        # A new picture replaces the old file.
        status, body = owner.call("POST", "/api/profile/avatar?name=me.jpg", raw=JPG_BYTES, content_type="image/jpeg")
        self.assertEqual(status, 201)
        self.assertEqual(self.client().get(first)[0], 404)
        self.assertEqual(sorted(p.name for p in self.config.avatar_dir.iterdir()), [body["avatarUrl"].rsplit("/", 1)[1]])
        # Wrong files are refused.
        for name, data, kind, expected in (("me.gif", b"GIF89a", "image/gif", 400), ("me.png", b"%PDF-1.4", "image/png", 400),
                                           ("me.png", PNG_BYTES + b"\x00" * (2 * 1024 * 1024), "image/png", 413)):
            self.assertEqual(owner.call("POST", f"/api/profile/avatar?name={name}", raw=data, content_type=kind)[0], expected, name)
        status, body = owner.delete("/api/profile/avatar")
        self.assertEqual((status, body["avatarUrl"]), (200, None))
        self.assertEqual(list(self.config.avatar_dir.iterdir()), [])

    def test_password_change(self):
        tenant, other_device = self.client("tenant@pfb.test"), self.client("tenant@pfb.test")
        status, body = tenant.post("/api/profile/password", {"currentPassword": "wrong", "newPassword": "NewSecret99"})
        self.assertEqual(status, 400)
        self.assertIn("currentPassword", body["fields"])
        status, body = tenant.post("/api/profile/password", {"currentPassword": DEMO_PASSWORD, "newPassword": "short"})
        self.assertEqual(status, 400)
        self.assertIn("newPassword", body["fields"])
        status, body = tenant.post("/api/profile/password", {"currentPassword": DEMO_PASSWORD, "newPassword": "NewSecret99"})
        self.assertEqual((status, body["otherSessionsEnded"]), (200, 1), body)
        self.assertEqual(tenant.get("/api/profile")[0], 200)          # still signed in here
        self.assertEqual(other_device.get("/api/profile")[0], 401)    # signed out elsewhere
        self.assertEqual(self.client().post("/api/auth/login", {"email": "tenant@pfb.test", "password": DEMO_PASSWORD})[0], 401)
        fresh = self.client()
        self.assertEqual(fresh.post("/api/auth/login", {"email": "tenant@pfb.test", "password": "NewSecret99"})[0], 200)

    def test_location_and_google_maps_are_allowed(self):
        request = urllib.request.Request(self.base + "/")
        with urllib.request.urlopen(request) as response:
            policy = response.headers["Permissions-Policy"]
            csp = response.headers["Content-Security-Policy"]
        self.assertIn("geolocation=(self)", policy)   # "Use my location" can ask the visitor
        self.assertIn("frame-src https://www.google.com", csp)
        self.assertNotIn("cdnjs", csp)
        script = self.client().get("/js/views/sprint5.js")[1]
        self.assertIn(b"https://www.google.com/maps?q=", script)
        self.assertIn(b"getCurrentPosition", script)


class PhotoTests(ApiTestCase):
    """Owners upload photos of their listings; buyers see them in a gallery and on search cards."""

    def new_listing(self, owner, title="Photo test flat in Mirpur"):
        status, body = owner.post("/api/properties", rent_listing(title=title))
        self.assertEqual(status, 201, body)
        return body["property"]["id"]

    def images(self, property_id):
        return self.client().get(f"/api/properties/{property_id}")[1]["images"]

    def stored_files(self, property_id):
        folder = self.config.photo_dir / str(property_id)
        return sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []

    def test_valid_upload_is_saved_served_and_becomes_the_cover(self):
        owner = self.client("owner@pfb.test")
        listing = self.new_listing(owner)
        status, body = owner.upload_photo(listing, "My%20Flat.png", PNG_BYTES)
        self.assertEqual(status, 201, body)
        image = body["image"]
        self.assertTrue(image["isCover"])
        self.assertTrue(image["uploaded"])
        # Saved under <photo folder>/<listing id>/ with a random name, never the owner's file name.
        files = self.stored_files(listing)
        self.assertEqual(len(files), 1)
        self.assertRegex(files[0], r"^[0-9a-f]{32}\.png$")
        self.assertEqual(image["url"], f"/uploads/properties/{listing}/{files[0]}")
        self.assertEqual((self.config.photo_dir / str(listing) / files[0]).read_bytes(), PNG_BYTES)
        # Anyone can load the photo, and the search card shows it as the cover.
        guest = self.client()
        status, served = guest.get(image["url"])
        self.assertEqual((status, served), (200, PNG_BYTES))
        card = next(p for p in guest.search_all("purpose=rent") if p["id"] == listing)
        self.assertEqual(card["image"], image["url"])
        # JPG and WebP work too; later photos are not the cover.
        status, body = owner.upload_photo(listing, "b.jpeg", JPG_BYTES, "image/jpeg")
        self.assertEqual((status, body["image"]["isCover"]), (201, False))
        status, body = owner.upload_photo(listing, "c.webp", WEBP_BYTES, "image/webp")
        self.assertEqual(status, 201, body)
        self.assertEqual([i["isCover"] for i in self.images(listing)], [True, False, False])
        with self.db() as connection:
            actions = [row[0] for row in connection.execute(
                "SELECT action_type FROM audit_log WHERE target_type = 'property' AND target_id = ?", (listing,))]
        self.assertEqual(actions.count("photo_added"), 3)

    def test_wrong_file_types_are_refused_with_clear_messages(self):
        owner = self.client("owner@pfb.test")
        listing = self.new_listing(owner)
        cases = [
            ("house.gif", b"GIF89a" + b"\x00" * 20, "image/gif", "Only JPG, PNG and WebP"),
            ("house", PNG_BYTES, "image/png", "Only JPG, PNG and WebP"),
            ("house.png", sample_pdf(["Not a photo"]), "image/png", "not a real PNG"),   # renamed PDF
            ("house.png", PNG_BYTES, "application/pdf", "does not look like a PNG"),     # wrong MIME type
            ("house.webp", PNG_BYTES, "image/webp", "not a real WebP"),
            ("house.jpg", b"", "image/jpeg", "empty"),
        ]
        for name, data, content_type, message in cases:
            status, body = owner.upload_photo(listing, name, data, content_type)
            self.assertEqual(status, 400, (name, body))
            self.assertIn(message, body["error"])
        self.assertEqual(self.images(listing), [])
        self.assertEqual(self.stored_files(listing), [])

    def test_oversized_photo_is_refused(self):
        owner = self.client("owner@pfb.test")
        listing = self.new_listing(owner)
        big = PNG_BYTES + b"\x00" * (5 * 1024 * 1024)
        status, body = owner.upload_photo(listing, "big.png", big)
        self.assertEqual(status, 413)
        self.assertIn("5 MB", body["error"])
        self.assertEqual(self.images(listing), [])

    def test_at_most_ten_photos_per_listing(self):
        owner = self.client("owner@pfb.test")
        listing = self.new_listing(owner)
        for number in range(10):
            self.assertEqual(owner.upload_photo(listing, f"p{number}.png", PNG_BYTES)[0], 201)
        status, body = owner.upload_photo(listing, "eleven.png", PNG_BYTES)
        self.assertEqual(status, 409)
        self.assertIn("at most 10 photos", body["error"])
        self.assertEqual(len(self.stored_files(listing)), 10)

    def test_only_the_owner_or_an_admin_can_change_photos(self):
        owner = self.client("owner@pfb.test")
        listing = self.new_listing(owner)
        status, body = owner.upload_photo(listing, "a.png", PNG_BYTES)
        image_id = body["image"]["id"]
        for email, expected in (("owner2@pfb.test", 403), ("tenant@pfb.test", 403), ("advocate@pfb.test", 403), (None, 401)):
            other = self.client(email)
            self.assertEqual(other.upload_photo(listing, "x.png", PNG_BYTES)[0], expected, email)
            self.assertEqual(other.delete(f"/api/properties/{listing}/images/{image_id}")[0], expected, email)
            self.assertEqual(other.post(f"/api/properties/{listing}/images/{image_id}/cover")[0], expected, email)
        self.assertEqual(len(self.images(listing)), 1)
        # Changes need the security header like every other change (CSRF).
        self.assertEqual(owner.call("DELETE", f"/api/properties/{listing}/images/{image_id}", csrf=False)[0], 403)
        # An admin may manage the photos of any listing.
        admin = self.client("admin@pfb.test")
        self.assertEqual(admin.upload_photo(listing, "admin.png", PNG_BYTES)[0], 201)
        # A photo id from another listing is not found through this listing.
        other_listing = self.new_listing(owner, "Second photo test flat")
        self.assertEqual(owner.delete(f"/api/properties/{other_listing}/images/{image_id}")[0], 404)

    def test_delete_removes_the_file_and_the_next_photo_becomes_cover(self):
        owner = self.client("owner@pfb.test")
        listing = self.new_listing(owner)
        ids = [owner.upload_photo(listing, f"{n}.png", PNG_BYTES)[1]["image"]["id"] for n in range(3)]
        cover_file = self.stored_files(listing)
        self.assertEqual(len(cover_file), 3)
        # Delete a photo that is not the cover: the cover stays.
        status, body = owner.delete(f"/api/properties/{listing}/images/{ids[1]}")
        self.assertEqual(status, 200, body)
        self.assertEqual([(i["id"], i["isCover"]) for i in body["images"]], [(ids[0], True), (ids[2], False)])
        self.assertEqual(len(self.stored_files(listing)), 2)
        # Delete the cover: the next photo becomes the cover, and its file is gone from disk.
        url = body["images"][0]["url"]
        status, body = owner.delete(f"/api/properties/{listing}/images/{ids[0]}")
        self.assertEqual([(i["id"], i["isCover"]) for i in body["images"]], [(ids[2], True)])
        self.assertNotIn(url.rsplit("/", 1)[1], self.stored_files(listing))
        self.assertEqual(self.client().get(url)[0], 404)
        # Delete the last one: the listing falls back to the placeholder (no image).
        owner.delete(f"/api/properties/{listing}/images/{ids[2]}")
        self.assertEqual(self.stored_files(listing), [])
        self.assertIsNone(self.client().get(f"/api/properties/{listing}")[1]["image"])
        self.assertEqual(owner.delete(f"/api/properties/{listing}/images/{ids[2]}")[0], 404)

    def test_set_cover_changes_the_card_photo(self):
        owner = self.client("owner@pfb.test")
        listing = self.new_listing(owner)
        first = owner.upload_photo(listing, "a.png", PNG_BYTES)[1]["image"]
        second = owner.upload_photo(listing, "b.png", PNG_BYTES)[1]["image"]
        status, body = owner.post(f"/api/properties/{listing}/images/{second['id']}/cover")
        self.assertEqual(status, 200, body)
        self.assertEqual([(i["id"], i["isCover"]) for i in body["images"]], [(second["id"], True), (first["id"], False)])
        self.assertEqual(self.client().get(f"/api/properties/{listing}")[1]["image"], second["url"])
        with self.db() as connection:
            covers = connection.execute(
                "SELECT COUNT(*) FROM property_images WHERE property_id = ? AND is_cover = 1", (listing,)).fetchone()[0]
        self.assertEqual(covers, 1)

    def test_demo_photos_and_files_outside_the_photo_folder(self):
        # Demo listings keep their linked photo as the cover, and it can be deleted (there is no file).
        owner = self.client("owner@pfb.test")
        listing = owner.get("/api/my/listings")[1]["properties"][0]["id"]
        demo = self.images(listing)
        self.assertTrue(demo and demo[0]["isCover"] and not demo[0]["uploaded"])
        added = owner.upload_photo(listing, "new.png", PNG_BYTES)[1]["image"]
        self.assertFalse(added["isCover"])
        status, body = owner.delete(f"/api/properties/{listing}/images/{demo[0]['id']}")
        self.assertEqual([(i["id"], i["isCover"]) for i in body["images"]], [(added["id"], True)])
        # Only photos are served from the photo address, never other files.
        guest = self.client()
        (self.config.photo_dir / "notes.txt").write_text("private")
        for path in ("/uploads/properties/notes.txt", "/uploads/properties/../pfb.sqlite3",
                     "/uploads/properties/%2e%2e/pfb.sqlite3", "/uploads/properties/999/missing.png"):
            self.assertEqual(guest.get(path)[0], 404, path)

    def test_upgrade_from_a_version_5_database_keeps_photos(self):
        old = Path(self.temp.name) / "old.sqlite3"
        connection = sqlite3.connect(old)
        connection.executescript(db.SCHEMA + db.HISTORY_SCHEMA + db.ADVOCATE_VERIFICATION_SCHEMA + db.SPRINT3_SCHEMA + db.SPRINT4_SCHEMA)
        connection.execute("INSERT INTO users (id, full_name, email, phone, password_hash, role, created_at) "
                           "VALUES (1, 'O', 'o@x.test', '01700000000', 'x', 'owner', '2026-01-01')")
        connection.execute("INSERT INTO properties (id, owner_id, title, description, listing_type, property_type, price, "
                           "area_name, city, address, size_sqft, bedrooms, bathrooms, created_at, updated_at) "
                           "VALUES (1, 1, 'Old', '', 'sale', 'House', 100, 'Mirpur', 'Dhaka', 'Road 1', 900, 2, 1, '2026-01-01', '2026-01-01')")
        connection.execute("INSERT INTO property_images (property_id, image_url, is_primary, uploaded_at) "
                           "VALUES (1, 'https://example.test/a.jpg', 1, '2026-01-01')")
        connection.execute("PRAGMA user_version = 5")
        connection.commit()
        connection.close()
        self.assertFalse(db.initialize(old))
        with contextlib.closing(sqlite3.connect(old)) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(property_images)")}
            row = connection.execute("SELECT image_url, is_cover, file_path FROM property_images").fetchone()
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
            with self.assertRaises(sqlite3.IntegrityError):   # still only one cover per listing
                connection.execute("INSERT INTO property_images (property_id, image_url, is_cover, uploaded_at) "
                                   "VALUES (1, 'https://example.test/b.jpg', 1, '2026-01-02')")
        self.assertTrue({"is_cover", "file_path"} <= columns)
        self.assertNotIn("is_primary", columns)
        self.assertEqual(row, ("https://example.test/a.jpg", 1, None))


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
