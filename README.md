# Property Finder Bangladesh (PFB): Sprint 1 and Sprint 2

CSE412 Software Engineering · Section 07 · Group 08

This build delivers **every story in Sprint 1 (PB-01 to PB-09) and Sprint 2 (PB-10 to PB-17)** from
`PFB_Product_Backlog_4_Sprints.xlsx`. Class and table names follow `PFB_Class_Based_Modeling_CRC_Cards.docx`.

## Run it

You only need Python 3.10 or newer. No packages to install.

```
python server.py
```

Open <http://127.0.0.1:8765>. The first run creates `instance/pfb.sqlite3` with demo data.

Do not open the site through VS Code Live Server or by double-clicking `index.html`. Those only show the pages; log in, saving and uploads need `server.py`.

All data is **demo data** (sample listings, people and papers). Real data will be collected in a later sprint.

- `python server.py --reset` deletes all data and uploads, then loads fresh demo data (use it before each demo).
- `python server.py --port 9000` runs the site on another port.

### Demo accounts

All demo accounts use the password **`Demo@1234`**. The login page also lists them, and clicking one fills in the form.

| Role | Email | What they can do |
|---|---|---|
| Buyer / Tenant | `tenant@pfb.test`, `tenant2@pfb.test` | Search, save homes, contact owners, calculators |
| Owner | `owner@pfb.test` | Own listings, legal verification, paper uploads |
| Owner (second, third) | `owner2@pfb.test`, `owner3@pfb.test` | Show that one owner cannot change another owner's listings |
| Advocate | `advocate@pfb.test` | Verification queue, checklist, decisions |
| Advocate (second) | `advocate2@pfb.test` | Has one review in progress; shows that a review belongs to one advocate only |
| Advocate (applied) | `applicant@pfb.test` | Signed up as an advocate and is waiting for an appointment; cannot open the queue yet |
| Admin | `admin@pfb.test` | Advocates, high-demand areas, all requests, audit log |

## The database

Everything is stored in one SQLite database file, `instance/pfb.sqlite3`. It is created on the first start; uploaded papers are saved in `instance/uploads/`. You can open the file with any SQLite viewer (for example *DB Browser for SQLite*) to show the tables.

| Group | Tables |
|---|---|
| Accounts | `users`, `advocate_profiles`, `sessions` |
| Listings | `properties`, `rent_details`, `property_images`, `favorites`, `inquiries` |
| Legal verification | `verification_requests`, `legal_documents`, `verification_reports`, `high_demand_areas`, `audit_log` |
| Browsing history | `property_views` (every listing opened: which listing, who or "guest", how it was found, when), `search_history` (searches by signed-in users: filters, number of results, when) |
| Later sprints (tables ready) | `consultations`, `chat_messages`, `payments`, `rent_agreements` |

How browsing history works:
- Buyers/tenants and owners see their own **History** page (recent searches with "Search again", recently viewed homes) and can **clear** it.
- Owners see how many times each listing was viewed (in total and in the last 7 days) on My listings.
- The admin panel has a **Browsing activity** tab: total views, most viewed listings, most searched areas, latest views and searches.
- Privacy: guests are counted without any personal details, and no IP addresses are stored. Opening the same listing again within 30 minutes is not counted twice. Views by the listing's own owner, advocates and admins are not counted. Clearing history unlinks the views from the person but keeps the listing's view count.

An older database is upgraded automatically on start-up (schema version 1 or 2 to 3); no reset is needed. Advocates already in an older database stay verified.

## Advocate sign-up and in-person verification

Advocates can apply for an account themselves instead of waiting for the admin to create one.

1. **Apply.** On the **Create an account** page the advocate picks **Work as an advocate** (the third account type, next to Buy or rent and Sell or rent out; `#/advocate/signup` opens the page with it already chosen) and enters name, email, mobile number, Bar Council ID, specialization and a password. The account is created as an advocate with the status **Waiting for appointment**.
2. **Appointment.** In the Admin panel → **Advocates**, the application appears under **Advocate applications**. The admin clicks **Send appointment** and enters a date and time, a place and an optional message.
3. **Message.** The advocate logs in on the normal Log in page and sees the appointment and the admin's message on **My application**. No email or SMS is sent; the message is shown inside the site.
4. **In person.** The advocate comes to the appointment. After checking them, the admin clicks **Mark verified in person** (or **Reject** with a reason, which the advocate sees).
5. **Access.** Only a verified advocate can open the verification queue, requests and legal papers. The server checks this on every request, not just the menu.

The status is stored in `advocate_profiles` (`verification_status`, `appointment_at`, `appointment_place`, `admin_message`, `reviewed_by`, `reviewed_at`), and each step is written to the audit log. **Add an advocate** in the admin panel still creates an account that is verified at once, for advocates the admin has already met.

Demo: log in as `applicant@pfb.test` to see a waiting application, then as `admin@pfb.test` to send the appointment and verify.

## Put it online for free (PythonAnywhere)

This gives the site a free address, `https://YOURNAME.pythonanywhere.com`, that keeps working when your own PC is off. The database and uploaded papers are stored on PythonAnywhere.

1. **Create an account.** Go to <https://www.pythonanywhere.com>, choose *Pricing & signup* and create a free **Beginner** account. Your username becomes part of the address, so pick it with care (for example `pfbgroup8`).
2. **Upload the project.**
   - On your PC, right-click the `CSE412` folder, then **Send to → Compressed (zipped) folder**. This gives `CSE412.zip`.
   - On PythonAnywhere, open the **Files** tab and use **Upload a file** to upload `CSE412.zip` into your home folder.
   - Open the **Consoles** tab and start a **Bash** console. Run:
     ```
     unzip CSE412.zip -d ~
     cd ~/CSE412
     python3 server.py --reset --setup-only
     ```
     The last command creates the database with the demo data. It does not start a server; PythonAnywhere runs the site itself.
3. **Create the web app.** Open the **Web** tab → **Add a new web app** → *Next* → **Manual configuration** (not Flask or Django) → choose the newest Python 3 version → *Next*.
4. **Point it at `wsgi.py`.** On the Web tab, click the link next to **WSGI configuration file** (it ends in `_wsgi.py`). Delete everything in that file and paste this, with your own username:
   ```python
   import sys
   path = "/home/YOURNAME/CSE412"
   if path not in sys.path:
       sys.path.insert(0, path)
   from wsgi import application
   ```
   Click **Save**.
5. **Turn on HTTPS.** On the Web tab, under *Security*, switch **Force HTTPS** on. The login cookie is marked Secure, so the site must be opened with `https://`.
6. **Start it.** Click the green **Reload** button at the top of the Web tab, then open `https://YOURNAME.pythonanywhere.com`.

Good to know:
- **Keep it alive:** on the free plan, log in at least once a month and click the **Run until ...** extend button on the Web tab, or the site is paused. (Since January 2026 free web apps expire after 1 month, not 3.)
- **Updating the site:** upload the changed files (or a new zip), then click **Reload** on the Web tab. Your database is kept unless you run `--reset` again.
- **If something goes wrong:** the **Error log** link on the Web tab shows what happened.
- **Custom domain:** the free plan only allows the `pythonanywhere.com` address. A custom domain such as `pfb.com.bd` needs a paid plan and a bought domain.
- **Demo data only:** the demo accounts and the password `Demo@1234` are public in this README. Before you collect real data online, run `--reset` and change or remove the demo accounts.

## Run the tests

```
python -m unittest discover -s tests -v
```

There are 37 automated tests: at least one per story's acceptance criteria, 5 for browsing history, 4 for advocate sign-up and verification, and 2 for the hosted version. Set `PFB_TEST_WSGI=1` to run all of them against the hosted (WSGI) version. Each test starts its own server on a temporary database, so your demo data is never touched.

## Where each story is done

| Story | What was built | Main code |
|---|---|---|
| PB-01 | Tables for all new classes (RentDetails, VerificationRequest, LegalDocument, VerificationReport, AuditLog, Consultation, ChatMessage, Payment, RentAgreement), linked to `properties` and `users`. Demo data: 38 sample listings across all eight divisions and all six property types (apartments, houses, duplexes, studios, plots, commercial spaces). | `pfb/db.py`, `pfb/seed.py` |
| PB-02 | Four roles. The role is saved at sign up (Buyer/Tenant or Owner); advocates apply on their own page or are added by the admin. The menu changes by role. Every API call checks the role on the server, and the browser shows "not available" on another role's page. | `pfb/api.py`, `public/js/app.js` |
| PB-03 | Only the owner can edit or delete a listing. Any attempt to set `verificationStatus` from the listing form is refused; only advocate decisions change it. | `owned_property`, `reject_verification_fields` in `pfb/api.py` |
| PB-04 | Admin adds advocates (with Bar Council ID), blocks, unblocks and removes them, and verifies advocates who applied themselves after an in-person appointment. Blocking signs the advocate out and returns their open reviews to the queue. | Admin panel → Advocates |
| PB-05 | Sell / Rent out choice on the listing form. Rent listings save monthly rent, deposit, available-from date, minimum lease, utilities and tenant preference. Wrong values show a message next to the field. | `pfb/validation.py`, `public/js/views/owner.js` |
| PB-06 | The listing page shows rent, deposit and **move-in cost = first rent + deposit**. | `public/js/views/property.js` |
| PB-07 | Search by All / Buy / Rent, area or city, type, min-max price (the labels switch to rent per month), bedrooms and sort. A friendly message shows when nothing matches. | `search_properties`, `public/js/views/home.js` |
| PB-08 | Rent affordability calculator (up to 30% of income = affordable, 30–40% = a stretch, more = not affordable). The EMI calculator still works. | `public/js/views/calculator.js` |
| PB-09 | New listings are live at once with an **Unverified** label; the status is stored in `properties.verification_status`. | `create_property` |
| PB-10 | "Request Legal Verification" checkbox on the new listing form (and a button in My listings) creates a **Pending** request. The owner sees its status. | `create_verification_request` |
| PB-11 | Upload land deed, mutation paper and tax receipt (and an optional ownership history). Only PDF/JPG/PNG up to 5 MB are accepted, and the file content is checked, not just the name. Files live in `instance/uploads/`, outside the website folder, and only the owner, the assigned advocate and admins can open them. | `upload_document`, `download_document` |
| PB-12 | Advocate dashboard: pending and in-review requests with property, area, date and paper count. The advocate opens one and starts the review (the papers unlock then). | `advocate_queue`, `public/js/views/review.js` |
| PB-13 | Checklist (deed, mutation, tax receipt, ownership history) with OK/Problem for each, required notes, and a **Document Verified** or **Issue Found** decision. Status changes are saved for the request, each paper and the listing. | `decide_request` |
| PB-14 | The owner sees **Issue Found** with the advocate's notes. Uploading a corrected paper sends the request back to **Pending**; the old paper is kept as "replaced". | `upload_document` |
| PB-15 | Verified badge only after advocate approval, plus a **Verified only** filter. "Issue Found" is shown only to the owner and staff; the public sees "Unverified". | `property_json`, `home.js` |
| PB-16 | Every change is saved in `audit_log` with user, time, old and new value. Database triggers block any edit or delete of log entries. The admin can browse and filter the log. | `audit()` + triggers in `pfb/db.py` |
| PB-17 | Admin marks high-demand areas; their requests go to the top of the queue. "Gulshan" also covers "Gulshan 2". | `HIGH_DEMAND_SQL` in `pfb/api.py` |

The baseline features the backlog assumes (sign up, login, search, listing page, inquiries with owner replies, favorites, EMI calculator, admin panel) were rebuilt as part of this rewrite.

## Sprint review demos

Run `python server.py --reset` first.

**Sprint 1:** create a rent listing, filter by Rent, see rent and deposit, use the affordability calculator.
1. Log in as `owner@pfb.test` → **+ List a property** → *Rent out*. Enter a negative rent to show the error, then fix it and publish. It appears in search at once as Unverified.
2. Log out → **Find homes** → **Rent**, set a max rent → open a listing to see rent, deposit and move-in cost.
3. Click **Can I afford this rent?** and enter an income.
4. Try opening `#/owner/listings` as `tenant@pfb.test` to show the role check.

**Sprint 2:** owner uploads papers, advocate marks Document Verified, the Verified badge appears.
1. As `owner@pfb.test`, open My listings → **Request legal verification** on a listing → upload the three papers.
2. As `advocate@pfb.test`, the queue shows the Gulshan request first (high-demand area). Open your new request → **Start review** → open the papers → tick the checklist → write notes → **Mark Document Verified**.
3. Log out → **Verified only** filter: the listing now has the badge.
4. As `admin@pfb.test` → **Audit log** shows who changed what and when. Under **High-demand areas**, add "Mirpur" and watch the queue order change.
5. To show PB-14: the demo listing "A family home with room to grow" already has **Issue Found**. As the owner, open **Fix issue**, read the notes and upload a corrected mutation paper; it goes back to Pending.

## Project layout

```
server.py            start-up, settings, --reset, --setup-only
wsgi.py              entry point for hosting (PythonAnywhere)
pfb/db.py            schema (all tables, audit-log triggers)
pfb/api.py           every API endpoint, with role checks
pfb/validation.py    form rules and error messages
pfb/security.py      password hashing, sessions, login throttling
pfb/web.py           small router on top of http.server, security headers
pfb/wsgi_app.py      the same site as a WSGI app, for hosting
pfb/seed.py          demo users, listings, verification requests and sample PDFs
public/              the website (HTML, CSS, JavaScript modules, no build step)
tests/test_api.py    acceptance tests for PB-01 to PB-17
instance/            database and uploaded papers (created at run time, not in git)
```

## Security notes

- Passwords are never stored as plain text. Each one is hashed with PBKDF2-SHA256 (240,000 rounds) and its own random salt, so two accounts with the same password have different stored values and the password cannot be read back from the database. Sessions use a random token in an HttpOnly, SameSite cookie, and only a hash of the token is stored.
- Five wrong passwords in 10 minutes lock that email from that computer for a while.
- Every POST, PUT and DELETE must carry an `X-PFB-Request` header. This blocks cross-site form attacks.
- The page HTML is built with an escaping template helper. A strict Content-Security-Policy and other security headers are sent on every response.
- This is a course demo bound to `127.0.0.1`. Before a real launch you would still need HTTPS (`PFB_SECURE_COOKIES=1`), a malware scan for uploads, backups, and email verification.
