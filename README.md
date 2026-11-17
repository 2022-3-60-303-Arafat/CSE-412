# Property Finder Bangladesh (PFB): Sprints 1 to 5

CSE412 Software Engineering · Section 07 · Group 08

This build delivers **every story in the product backlog: Sprint 1 (PB-01 to PB-09), Sprint 2 (PB-10 to PB-17), Sprint 3 (PB-18 to PB-25), Sprint 4 (PB-26 to PB-33) and Sprint 5 (PB-34 to PB-45)** from
`PFB_Product_Backlog_4_Sprints.xlsx`. Class and table names follow `PFB_Class_Based_Modeling_CRC_Cards.docx`.

## Run it

You only need Python 3.10 or newer. No packages to install.

```
python server.py
```

Open <http://127.0.0.1:8765>. The first run creates `instance/pfb.sqlite3` with demo data.

Do not open the site through VS Code Live Server or by double-clicking `index.html`. Those only show the pages; log in, saving and uploads need `server.py`.

All data is **demo data** (sample listings, people and papers). Real data will be collected in a later sprint.

- `python server.py --reset` deletes all data, uploaded papers and listing photos, then loads fresh demo data (use it before each demo).
- `python server.py --port 9000` runs the site on another port.

### Demo accounts

All demo accounts use the password **`Demo@1234`**. The login page also lists them, and clicking one fills in the form.

| Role | Email | What they can do |
|---|---|---|
| Buyer / Tenant | `tenant@pfb.test`, `tenant2@pfb.test` | Search, save homes, contact owners, calculators, ask advocates, book and pay for consultations. `tenant@pfb.test` has a chat, a booked consultation and one waiting for payment; `tenant2@pfb.test` has one waiting for the advocate and one completed with notes |
| Owner | `owner@pfb.test` | Own listings, legal verification, paper uploads |
| Owner (second, third) | `owner2@pfb.test`, `owner3@pfb.test` | Show that one owner cannot change another owner's listings |
| Advocate | `advocate@pfb.test` | Verification queue, checklist, decisions, badge levels, chats and consultations (fee 500 taka) |
| Advocate (second) | `advocate2@pfb.test` | Has one review in progress; shows that a review belongs to one advocate only (fee 700 taka) |
| Advocate (applied) | `applicant@pfb.test` | Signed up as an advocate and is waiting for an appointment; cannot open the queue yet |
| Admin | `admin@pfb.test` | Advocates, high-demand areas, all requests, audit log |

## The database

Everything is stored in one SQLite database file, `instance/pfb.sqlite3`. It is created on the first start; uploaded papers are saved in `instance/uploads/` (private) and listing photos in `public/uploads/properties/` (public). You can open the file with any SQLite viewer (for example *DB Browser for SQLite*) to show the tables.

| Group | Tables |
|---|---|
| Accounts | `users`, `advocate_profiles`, `sessions` |
| Listings | `properties`, `rent_details`, `property_images`, `favorites`, `inquiries` |
| Legal verification | `verification_requests`, `legal_documents`, `verification_reports` (the legal report of each verified listing), `high_demand_areas`, `audit_log` |
| Consultations (Sprint 3) | `consultations` (free chats and paid bookings), `chat_messages`, `payments` (paid and failed attempts), `notifications` |
| Agreements and reports (Sprint 4) | `rent_agreements`, `saved_searches`, `listing_reports` |
| Sprint 5 | `site_visits`, `phone_verifications`, `duplicate_flags`, `reviews`, `rent_payments`; new columns `users.phone_verified_at`, `properties.latitude` / `longitude`, `property_images.file_hash`, `payments.account_masked` |
| Browsing history | `property_views` (every listing opened: which listing, who or "guest", how it was found, when), `search_history` (searches by signed-in users: filters, number of results, when) |

How browsing history works:
- Buyers/tenants and owners see their own **History** page (recent searches with "Search again", recently viewed homes) and can **clear** it.
- Owners see how many times each listing was viewed (in total and in the last 7 days) on My listings.
- The admin panel has a **Browsing activity** tab: total views, most viewed listings, most searched areas, latest views and searches.
- Privacy: guests are counted without any personal details, and no IP addresses are stored. Opening the same listing again within 30 minutes is not counted twice. Views by the listing's own owner, advocates and admins are not counted. Clearing history unlinks the views from the person but keeps the listing's view count.

An older database is upgraded automatically on start-up (schema version 1 to 7 up to 8); no reset is needed. Owners who already had listings keep publishing without confirming their phone again. Advocates already in an older database stay verified and get the standard fee of 500 taka.

## Listing photos

Owners add photos of their house or flat on the listing form (**+ List a property** or **Edit**). Buyers see them on the listing page as a gallery (a main photo with clickable thumbnails) and the cover photo on search cards. A listing without photos shows a placeholder.

- JPG, PNG or WebP only, up to 5 MB each and 10 photos per listing. The server checks the file name, the file type the browser sends and the file's first bytes, so a renamed file of another kind is refused with a clear message.
- The first photo becomes the **cover**. On the edit page each photo has **Set as cover** and **Delete**. Deleting the cover makes the oldest remaining photo the cover. Deleting a photo also removes its file.
- Only the listing's owner (or an admin, through the API) can add, delete or change photos. Every change is in the audit log.
- Files are saved as `public/uploads/properties/<listing id>/<random name>.<jpg|png|webp>`; the owner's file name is never used. The photos are public on purpose. Uploaded photos are not in git (only the folder's `.gitkeep` is).
- In the database, photos are rows in `property_images` (`is_cover`, `file_path`). The demo listings keep their linked photos (with no `file_path`), so an owner's new photo does not replace a demo cover until they choose **Set as cover**.

## My profile

Every signed-in user opens **My profile** from the picture and name at the top right. They can:
- upload a profile picture (JPG, PNG or WebP, up to 2 MB) or remove it; it shows in the menu and next to an owner's name on listings;
- change their name, mobile number, occupation and a short "About me";
- change their password (other devices are signed out).

An owner who changes their mobile number confirms the new number with a code before the next listing (PB-35). Pictures are saved in `public/uploads/avatars/` with random names.

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

There are 90 automated tests: at least one per story's acceptance criteria (9 for Sprint 3, 7 for Sprint 4, 17 for Sprint 5), 5 for browsing history, 4 for advocate sign-up and verification, 6 for search filters and pages, 9 for listing photos, 5 for the profile page, and 2 for the hosted version. Set `PFB_TEST_WSGI=1` to run all of them against the hosted (WSGI) version. Each test starts its own server on a temporary database, so your demo data is never touched.

## Where each story is done

| Story | What was built | Main code |
|---|---|---|
| PB-01 | Tables for all new classes (RentDetails, VerificationRequest, LegalDocument, VerificationReport, AuditLog, Consultation, ChatMessage, Payment, RentAgreement), linked to `properties` and `users`. Demo data: 38 sample listings across all eight divisions and all six property types (apartments, houses, duplexes, studios, plots, commercial spaces). | `pfb/db.py`, `pfb/seed.py` |
| PB-02 | Four roles. The role is saved at sign up (Buyer/Tenant or Owner); advocates apply on their own page or are added by the admin. The menu changes by role. Every API call checks the role on the server, and the browser shows "not available" on another role's page. | `pfb/api.py`, `public/js/app.js` |
| PB-03 | Only the owner can edit or delete a listing. Any attempt to set `verificationStatus` from the listing form is refused; only advocate decisions change it. | `owned_property`, `reject_verification_fields` in `pfb/api.py` |
| PB-04 | Admin adds advocates (with Bar Council ID), blocks, unblocks and removes them, and verifies advocates who applied themselves after an in-person appointment. Blocking signs the advocate out and returns their open reviews to the queue. | Admin panel → Advocates |
| PB-05 | Sell / Rent out choice on the listing form. Rent listings save monthly rent, deposit, available-from date, minimum lease, utilities and tenant preference. Wrong values show a message next to the field. | `pfb/validation.py`, `public/js/views/owner.js` |
| PB-06 | The listing page shows rent, deposit and **move-in cost = first rent + deposit**. | `public/js/views/property.js` |
| PB-07 | Search by All / Buy / Rent, area or city, district, type, min-max price (the labels switch to rent per month), bedrooms, furnished / unfurnished and sort, with 12 homes per page. Every filter and the page number are in the address (for example `#/?purpose=rent&city=Dhaka&furnished=yes&page=2`), so a search can be shared and the form shows the same choices when it is opened. A friendly message shows when nothing matches. | `search_properties`, `public/js/views/home.js` |
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
| PB-18 | A plain-language legal report is created when an advocate marks a property Document Verified. Anyone can download it as a PDF from the listing: each paper checked, the result, the advocate, the date and a disclaimer. A small built-in PDF writer makes it, so no package is needed. | `pfb/reports.py`, `pfb/pdf.py` |
| PB-19 | Three badge levels: Document Verified, Site Visited, Fully Verified. The advocate who verified the listing sets the level on the request page; the listing, the search cards and the report show it. | `set_badge_level` in `pfb/api.py` |
| PB-20 | **Ask an Advocate** on verified listings, for buyers/tenants. It asks them to choose a free question or a paid booking. | `askPanel` in `public/js/views/property.js` |
| PB-21 | Free chat on the property page. The question goes to the advocate who verified the listing. Messages are saved, the advocate replies from **Consultations**, and the chat history stays on the property page. New messages appear within a few seconds. | `pfb/consult.py`, `public/js/views/consult.js` |
| PB-22 | Paid booking: choose an advocate (with their fee) and a free slot in the next 7 days (10 am to 5 pm, closed on Fridays). A slot that is asked for or booked is not offered again, and the database refuses a double booking. | `book_consultation`, `free_slots` |
| PB-23 | The advocate accepts or refuses a request (with a reason), then adds follow-up notes after the session. The notes show in the buyer's Consultations page. | `respond_to_request`, `complete_consultation` |
| PB-24 | After the advocate accepts, the buyer pays with bKash, Nagad or a card. The booking is confirmed only after a successful payment, and a receipt is shown. **Demo payment: no real money moves.** A number ending in 0000 shows the failed-payment message. | `pay_consultation` |
| PB-26 | On **My listings** a rent listing has a **Rent agreement** button. The landlord enters the tenant's email, the move-in date, the lease length and any special terms; the landlord, tenant, rent, deposit, utilities and end date are filled in from the listing and the accounts. The agreement downloads as a PDF. | `pfb/sprint4.py`, `public/js/views/agreements.js` |
| PB-27 | The agreement moves Draft, Under review, Approved, Signed. An advocate approves it or sends it back with notes. Signing (typing your full name) is refused until an advocate has approved it; it is Signed when both the landlord and the tenant have signed. Every step is in the audit log. | `review_agreement`, `sign_agreement` |
| PB-28 | Buyers press **Save this search** on the search results. Saved searches are listed (and deleted) on the History page. When an advocate verifies a home that matches, the buyer gets a notification. | `alert_saved_searches` |
| PB-29 | The admin panel opens on a **Platform report**: verified and unverified listings, for sale and for rent, the verification pipeline, each advocate's pending work, consultations and rent agreements. | `admin_report` |
| PB-30 | Signed-in users can **Report this listing** from the listing page. The admin's **Listing reports** tab dismisses a report or removes the listing, which then leaves the search results; the owner and the reporters are told. | `report_listing`, `resolve_listing_report` |
| PB-31 | Every page works on a phone (checked at 390 px wide, no sideways scrolling). Photos load only when they scroll into view, and the search cards ask for smaller photos than the listing page. | `photo()` in `public/js/ui.js` |
| PB-32 | Automated tests cover every story, and the whole flow of each sprint was also run in a browser. See "Known limitations" below for what is not covered. | `tests/test_api.py` |
| PB-33 | This README holds the demo steps for all five sprints and the steps to put the site online. | `README.md` |
| PB-34 | **Visit this home** on a listing page: a tenant picks a one-hour slot in the next 14 days and adds a note. A slot cannot be taken twice. The owner confirms or declines (with a reason) under **Visits**; both get a notification, and the address and phone numbers are shared only after the owner confirms. The tenant can cancel before the visit. | `pfb/sprint5.py`, `visitPanel`, `renderVisits` |
| PB-35 | A new owner confirms their mobile number with a 6-digit code before the first listing can be published. The code expires after 10 minutes, 5 wrong tries block it and only a hash is stored. Listings show **Phone verified**. There is no SMS gateway, so the code is shown on screen (set `PFB_DEMO_SMS=0` once SMS is connected). | `send_phone_code`, `verify_phone_code`, `phonePanel` |
| PB-36 | Paying a consultation with **bKash** or **Nagad** asks for the wallet number and the wallet PIN (sandbox: the PIN is checked for shape and never stored). The receipt shows the wallet as `017*****678` and the transaction ID. | `pay_consultation` in `pfb/consult.py` |
| PB-37 | Search **Near a place** (21 landmarks: universities, business districts, hospitals, the airport) or **Use my location**, within 1, 3, 5 or 10 km, nearest first, with the distance on each card. **Map** opens Google Maps next to the list of matching homes, nearest first; pressing a home shows its exact pin. Opening the map asks for the visitor's location (the browser asks permission) and explains how to turn it on if it is blocked or off. Each listing page shows its Google map with **Get directions**. Owners set the position with **Use my current location** or by pasting it from Google Maps; otherwise the area centre is used. Saved searches can be near a landmark too. | `search_conditions`, `pfb/places.py`, `askLocation`, `googleMap` |
| PB-38 | **+ Compare** on a listing page adds it to a list of up to 3 (kept in the browser). **Compare homes** shows price or rent, deposit, move-in cost, size, price per sqft, bedrooms and the legal check side by side and marks the best value in each row. | `compare`, `renderCompare` |
| PB-39 | A photo identical to one on another owner's listing, or a description at least 85% the same, creates a flag for the admin (**Duplicate listings** tab), who dismisses it or removes the copy. Reusing your own photos is fine; short descriptions are not compared. | `check_duplicate_photo`, `check_duplicate_text` |
| PB-40 | **Price guide** page: average, lowest and highest rent or price by district and by area and bedroom count, for groups of 3 or more active listings. The listing page says how far the price is above or below similar homes (the area, or the district when the area has fewer than 3). The admin report includes it. | `price_guide`, `price_position` |
| PB-41 | After a completed consultation the buyer rates the advocate (1 to 5 stars, optional comment), once. The average and the number of reviews show when choosing an advocate. | `review_advocate`, `reviewPanel` |
| PB-42 | **বাংলা / English** button in the header. The menu, search, listing cards, listing page, log-in and sign-up pages switch to Bangla; the choice is remembered in the browser. Text people typed is shown as written. | `public/js/i18n.js` |
| PB-43 | When both sides sign a rent agreement, one rent payment per month of the lease is created. The tenant gets a reminder 3 days before each due date and when it is overdue (the landlord too). The tenant marks a month as paid and the landlord confirms it, on the agreement page. | `create_rent_schedule`, `send_rent_reminders`, `mountRentPayments` |
| PB-44 | **My profile** (from the picture and name in the header): upload, change or remove a profile picture, edit name, phone, occupation and "about me", and change the password (other devices are signed out). An owner who changes their phone confirms it again. | `pfb/profile.py`, `public/js/views/profile.js` |
| PB-45 | Owners upload photos (JPG, PNG, WebP, up to 5 MB, 10 per listing), choose the cover, and delete photos. The listing page shows a gallery; search cards show the cover. | `pfb/photos.py`, `public/js/views/owner.js` |
| PB-25 | A bell in the menu shows the unread count. Owners are told the verification result; advocates are told about new requests, questions and bookings; buyers are told about replies, accepted or refused bookings and notes. Clicking a notification opens the right page. | `notify` in `pfb/db.py`, `/notifications` |

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

**Sprint 3:** download a legal report, chat with an advocate, book and pay for a consultation.
1. Log out, tick **Verified only** and open "A quiet home above the city": it shows **Fully Verified**. Click **Download the legal report (PDF)**.
2. Log in as `tenant2@pfb.test`, open a verified listing, click **Ask an Advocate**, then **Ask a free question**, and send a question.
3. Log in as the advocate named in the chat. The bell shows a new notification. Open **Consultations**, open the question and reply. Back as the tenant, the reply is on the property page.
4. As `tenant2@pfb.test`: **Ask an Advocate**, then **Book a paid consultation**. Choose an advocate and a slot, then **Send booking request**.
5. As that advocate: **Consultations**, open the request, **Accept this slot**.
6. As the tenant: open the booking and pay with bKash number `01712340000` to show a failed payment, then `01712345678` to pay. The receipt appears.
7. As the advocate: write the follow-up notes and click **Save notes and mark completed**. The tenant sees them under **Consultations**.
8. As `advocate@pfb.test`: open a request you verified (under **Your recent decisions**) and set the **Badge level** to Site Visited.

**Sprint 4:** rent agreement, saved-search alert, admin report, fake-listing report.
1. Log in as `owner@pfb.test` → **My listings** → **Rent agreement** on "Easy, airy living by the lake". Enter `tenant2@pfb.test`, a move-in date and 12 months → **Create draft** → **Send to an advocate**.
2. As `advocate@pfb.test` → **Agreements** → open it → **Approve**.
3. As `tenant2@pfb.test` → **Agreements** → open it → type `Sumaiya Islam`, tick the box → **Sign agreement**. Then as the owner, sign with `Nadia Rahman`: the status becomes **Signed**. **Download PDF** shows the signed agreement. (The demo data also has an approved agreement that `tenant@pfb.test` can sign straight away.)
4. As `tenant2@pfb.test` → **Find homes** → **Rent**, area "Dhanmondi" → **Save this search**. As `advocate@pfb.test`, verify "Easy, airy living by the lake" (as in the Sprint 2 demo). Back as the tenant, the bell shows "A new verified home matches your search".
5. As any buyer → open "Residential plot in Purbachal" → **Report this listing**. As `admin@pfb.test` → **Listing reports** → write a note → **Remove the listing**. It no longer appears in search.
6. As `admin@pfb.test` → **Platform report** shows the counts of verified, unverified, sale and rent listings and each advocate's pending work.

**Sprint 5:** site visit, phone code, bKash, map search, compare, price guide, rating, Bangla, duplicates, rent reminders.
1. As `tenant@pfb.test` → open "Sunny apartment in Banasree" → **Visit this home** → pick a day and time → **Ask for this visit**. As `owner@pfb.test` → **Visits** → **Confirm visit**. Back as the tenant, the visit shows the owner's phone and the address.
2. **Sign up** a new owner account → **+ List a property** asks to confirm the mobile number → **Send code** (the demo shows the code) → enter it → the listing form opens. The published listing shows **Phone verified**.
3. As `tenant@pfb.test` → **Consultations** → the request waiting for payment → choose **bKash**, number `01712345678`, PIN `12345` → **Pay**. The receipt shows `017*****678`.
4. **Find homes** → press **Map**. The browser asks to use your location: allow it (and turn on Location on the device) and the map shows where you are, with the nearest homes listed. Or choose **Near a place** = University of Dhaka, within 3 km. Press a home in the list to see its exact pin; open a listing for **Get directions**.
5. Open two or three rent listings → **+ Compare** on each → **Compare homes**. The listing page also shows how its rent compares with similar homes; **Price guide** in the menu shows the averages.
6. As `tenant2@pfb.test` → **Consultations** → the completed one → give 4 stars. The rating shows when booking that advocate.
7. Press **বাংলা** in the header: the menu, search and listing pages switch to Bangla. Press **English** to switch back.
8. As `owner2@pfb.test`, publish a listing that copies the description of "Sunny apartment in Banasree". As `admin@pfb.test` → **Duplicate listings** shows the flag → **Remove listing**.
9. As `tenant@pfb.test` → **Agreements** → sign the approved agreement with `Rafi Chowdhury`: a **Monthly rent** table appears. **Mark as paid** a month; as `owner@pfb.test`, **Confirm received**.

## Known limitations

- Payments are simulated (sandbox); no real bKash, Nagad or card payment is made, and wallet PINs are never stored.
- No email or SMS is sent. Appointments, alerts and replies are shown inside the site (the bell and the Notifications page). The phone confirmation code is shown on screen for the same reason.
- The map (PB-37) is Google's embedded map, which needs internet but no API key. It shows one pin at a time (the chosen place or the home pressed in the list). Showing every home as a pin at once needs the paid Google Maps JavaScript API and a key. Landmark and area positions are approximate (about 300 m); search by distance works without the map.
- The browser asks for location only on a secure address: `http://127.0.0.1` (this computer) or `https://` (PythonAnywhere).
- Rent reminders are created when the tenant or landlord opens the site, not by a background job, so someone who never logs in sees them on their next visit.
- The Bangla switch translates the main pages (menu, search, listing cards, listing page, log in, sign up). Owner, advocate and admin pages stay in English.
- Chat messages appear within about 8 seconds, not instantly.
- Signing an agreement on the site is a typed-name signature. For a court-enforceable agreement it still has to be printed on stamp paper and registered.
- The legal report and the agreement PDF use a standard font, so Bangla text in a listing would not print correctly in them.
- Story status in `PFB_Product_Backlog_4_Sprints.xlsx` is left for the team to update, because the Definition of Done asks for a team member other than the author to test each story.

## Project layout

```
server.py            start-up, settings, --reset, --setup-only
wsgi.py              entry point for hosting (PythonAnywhere)
pfb/db.py            schema (all tables, audit-log triggers)
pfb/api.py           API endpoints for Sprints 1 and 2, with role checks
pfb/consult.py       API endpoints for Sprint 3: chat, bookings, payments, notifications
pfb/sprint4.py       API endpoints for Sprint 4: rent agreements, saved searches, admin report, listing reports
pfb/photos.py        listing photos: upload, delete, set cover
pfb/sprint5.py       API endpoints for Sprint 5: visits, phone code, compare, duplicates, price guide, reviews, rent payments
pfb/places.py        area centres and landmarks for map search (PB-37)
pfb/profile.py       my profile: details, profile picture, password
pfb/reports.py       legal reports and badge levels (PB-18, PB-19)
pfb/pdf.py           a small PDF writer for the legal report and the rent agreement
pfb/validation.py    form rules and error messages
pfb/security.py      password hashing, sessions, login throttling
pfb/web.py           small router on top of http.server, security headers
pfb/wsgi_app.py      the same site as a WSGI app, for hosting
pfb/seed.py          demo users, listings, verification requests, sample PDFs, consultations and notifications
public/              the website (HTML, CSS, JavaScript modules, no build step)
public/js/i18n.js    Bangla / English switch (PB-42)
public/js/views/sprint5.js  Sprint 5 pages and panels (Google Maps helpers too)
public/js/views/profile.js  the My profile page
tests/test_api.py    acceptance tests for PB-01 to PB-43
public/uploads/      listing photos and profile pictures (public; not in git)
instance/            database and uploaded papers (created at run time, not in git)
```

## Security notes

- Passwords are never stored as plain text. Each one is hashed with PBKDF2-SHA256 (240,000 rounds) and its own random salt, so two accounts with the same password have different stored values and the password cannot be read back from the database. Sessions use a random token in an HttpOnly, SameSite cookie, and only a hash of the token is stored.
- Five wrong passwords in 10 minutes lock that email from that computer for a while.
- Every POST, PUT and DELETE must carry an `X-PFB-Request` header. This blocks cross-site form attacks.
- The page HTML is built with an escaping template helper. A strict Content-Security-Policy and other security headers are sent on every response.
- Chats and consultations can only be read by the buyer and the advocate in them, and every action checks the role on the server.
- Payments are simulated. A real launch would connect bKash, Nagad or a card gateway through their merchant APIs.
- This is a course demo bound to `127.0.0.1`. Before a real launch you would still need HTTPS (`PFB_SECURE_COOKIES=1`), a malware scan for uploads, backups, and email verification.
