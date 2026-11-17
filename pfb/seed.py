"""Demo data so every Sprint 1 to 4 feature can be shown right after start-up."""

import json
import secrets
from datetime import date, datetime, timedelta, timezone

from . import reports
from .db import audit, notify
from .security import hash_password

DEMO_PASSWORD = "Demo@1234"

USERS = [
    ("admin", "Farhana Admin", "admin@pfb.test", "01710000001", "admin"),
    ("owner", "Nadia Rahman", "owner@pfb.test", "01710000002", "owner"),
    ("owner2", "Tanvir Hasan", "owner2@pfb.test", "01710000003", "owner"),
    ("owner3", "Karim Uddin", "owner3@pfb.test", "01710000007", "owner"),
    ("tenant", "Rafi Chowdhury", "tenant@pfb.test", "01710000004", "buyer_tenant"),
    ("tenant2", "Sumaiya Islam", "tenant2@pfb.test", "01710000008", "buyer_tenant"),
    ("advocate", "Adv. Sarah Rahman", "advocate@pfb.test", "01710000005", "advocate"),
    ("advocate2", "Adv. Mahmud Karim", "advocate2@pfb.test", "01710000006", "advocate"),
    ("applicant", "Adv. Imran Hossain", "applicant@pfb.test", "01710000009", "advocate"),
]

ADVOCATES = {
    "advocate": ("DBC-2016-0412", "Land and property documents"),
    "advocate2": ("DBC-2018-1187", "Rental agreements and title review"),
}
# Applied through the advocate sign-up page; waiting for the admin to send an appointment.
ADVOCATE_APPLICANTS = {
    "applicant": ("DBC-2022-0731", "Property transfer and registration"),
}

# key, owner, listing type, title, area, city, address, type, amount, beds, baths, sqft, furnished, photo, description, rent extras
LISTINGS = [
    ("gulshan", "owner", "sale", "Light-filled corner apartment", "Gulshan 2", "Dhaka", "Road 83, Gulshan 2, Dhaka", "Apartment", 28_500_000, 3, 3, 1780, False,
     "photo-1600607687939-ce8a6c25118c", "A bright home with generous windows, a calm neutral palette and a wide balcony. The building has a lift, backup generator and dedicated parking.", None),
    ("banani", "owner2", "rent", "A quiet home above the city", "Banani", "Dhaka", "Road 11, Banani, Dhaka", "Apartment", 78_000, 2, 2, 1240, True,
     "photo-1600607687920-4e2a09cf159d", "An easy-to-live-in apartment close to cafes, schools and the Banani lake walk. Fully furnished, with building security and one parking space.", (156_000, 10, 12, False, "family")),
    ("bashundhara", "owner", "sale", "A family home with room to grow", "Bashundhara R/A", "Dhaka", "Block D, Bashundhara R/A, Dhaka", "Duplex", 41_200_000, 4, 4, 2680, False,
     "photo-1600566753086-00f18fb6b3ea", "Planned across two levels, with a roomy living area, a separate dining space and a sunny terrace. Parks nearby and easy access to the main road.", None),
    ("dhanmondi-studio", "owner", "rent", "The little studio with big light", "Dhanmondi", "Dhaka", "Road 8/A, Dhanmondi, Dhaka", "Studio", 32_000, 1, 1, 610, True,
     "photo-1600210492486-724fe5c67fb0", "A well-planned studio with lovely afternoon light, built-in storage and a separate kitchenette. A short walk to the lake.", (64_000, 0, 6, True, "bachelor")),
    ("uttara", "owner2", "sale", "Garden mornings in a modern house", "Uttara Sector 7", "Dhaka", "Sector 7, Uttara, Dhaka", "House", 19_800_000, 3, 3, 2110, False,
     "photo-1600585154340-be6161a56a0c", "A detached home with a private garden, a practical kitchen and space to gather. Close to schools and a short drive from the airport.", None),
    ("dhanmondi-lake", "owner", "rent", "Easy, airy living by the lake", "Dhanmondi", "Dhaka", "Road 27, Dhanmondi, Dhaka", "Apartment", 58_000, 2, 2, 1390, False,
     "photo-1600047509807-ba8f99d2cdde", "A comfortable apartment with a breezy balcony and well-proportioned rooms. The lakeside path, groceries and transport are all close.", (116_000, 5, 12, False, "family")),
    ("panchlaish", "owner2", "sale", "A calm, contemporary duplex", "Panchlaish", "Chattogram", "Panchlaish, Chattogram", "Duplex", 25_200_000, 3, 3, 1930, False,
     "photo-1600607687644-c7171b42498f", "A clean-lined duplex with open living and dining space, a study nook and a generous balcony. Close to hospitals, schools and shops.", None),
    ("zindabazar", "owner2", "rent", "A bright corner place in Sylhet", "Zindabazar", "Sylhet", "Zindabazar, Sylhet", "Apartment", 45_000, 2, 2, 1160, True,
     "photo-1600607687920-4e2a09cf159d", "A move-in-ready apartment with a sunny corner balcony. Close to shops, cafes and the city centre.", (90_000, 20, 12, True, "any")),
    ("halishahar", "owner", "sale", "Room to breathe near the river", "Halishahar", "Chattogram", "Halishahar, Chattogram", "Apartment", 13_400_000, 3, 2, 1510, False,
     "photo-1600607687939-ce8a6c25118c", "A practical, spacious apartment with good cross-breezes and a sunny dining corner, in a peaceful neighbourhood.", None),
    ("mirpur", "owner", "rent", "A practical flat close to Mirpur 10", "Mirpur 10", "Dhaka", "Mirpur 10, Dhaka", "Apartment", 28_000, 2, 1, 930, False,
     "photo-1600607687644-c7171b42498f", "A bright two-bedroom flat close to local shops and public transport. An affordable start for a small household.", (56_000, 0, 12, False, "any")),
    ("mohammadpur", "owner2", "sale", "A roomy family flat in Mohammadpur", "Mohammadpur", "Dhaka", "Mohammadpur, Dhaka", "Apartment", 16_400_000, 3, 2, 1560, False,
     "photo-1600566753086-00f18fb6b3ea", "A spacious family home with an open living and dining area, good natural light and daily essentials nearby.", None),
    ("banasree", "owner", "rent", "Sunny apartment in Banasree", "Banasree", "Dhaka", "Block C, Banasree, Dhaka", "Apartment", 36_000, 2, 2, 1080, False,
     "photo-1600210492486-724fe5c67fb0", "A comfortable two-bedroom apartment with a balcony and easy access to groceries and schools.", (72_000, 15, 12, False, "family")),
    ("baridhara", "owner2", "sale", "A generous home in Baridhara", "Baridhara", "Dhaka", "Baridhara, Dhaka", "House", 56_800_000, 4, 4, 3020, False,
     "photo-1600585154340-be6161a56a0c", "A spacious home with several living areas, a sunny garden and room for a growing family, in quiet Baridhara.", None),
]

# More sample listings so every city and property type has something to show.
# A photo of None means "no photo yet" (used for plots and commercial spaces).
LISTINGS += [
    ("gulshan1-serviced", "owner3", "rent", "Furnished serviced apartment in Gulshan 1", "Gulshan 1", "Dhaka", "Road 34, Gulshan 1, Dhaka", "Apartment", 150_000, 3, 3, 2000, True,
     "photo-1600607687920-4e2a09cf159d", "A fully furnished apartment with weekly cleaning, generator backup, a gym on the roof and two parking spaces. Suits a family or company staff.", (300_000, 14, 12, True, "any")),
    ("uttara-rent", "owner2", "rent", "Family flat near Uttara Sector 11 park", "Uttara Sector 11", "Dhaka", "Road 7, Sector 11, Uttara, Dhaka", "Apartment", 30_000, 3, 2, 1250, False,
     "photo-1600047509807-ba8f99d2cdde", "A three-bedroom flat on the fourth floor with a lift. Two minutes from the park and close to schools and the metro rail station.", (60_000, 10, 12, False, "family")),
    ("mohammadpur-rent", "owner3", "rent", "Affordable flat in Mohammadpur", "Mohammadpur", "Dhaka", "Tajmahal Road, Mohammadpur, Dhaka", "Apartment", 18_000, 2, 1, 800, False,
     "photo-1600607687644-c7171b42498f", "A simple two-room flat for students or young professionals. Gas and water are available all day. Bus stop on the main road.", (36_000, 5, 6, False, "bachelor")),
    ("bashundhara-rent", "owner", "rent", "Spacious duplex for rent in Bashundhara", "Bashundhara R/A", "Dhaka", "Block G, Bashundhara R/A, Dhaka", "Duplex", 95_000, 4, 4, 2600, False,
     "photo-1600566753086-00f18fb6b3ea", "A two-level duplex with a private roof terrace, servant room and two car parking. Near the international schools of Bashundhara.", (190_000, 30, 24, False, "family")),
    ("shyamoli-studio", "owner2", "rent", "Small studio in Shyamoli", "Shyamoli", "Dhaka", "Ring Road, Shyamoli, Dhaka", "Studio", 15_000, 1, 1, 450, True,
     "photo-1600210492486-724fe5c67fb0", "A compact furnished studio with an attached bath and kitchenette. Good for a single working person.", (30_000, 0, 6, True, "bachelor")),
    ("badda-rent", "owner3", "rent", "Quiet flat off Badda link road", "Badda", "Dhaka", "Link Road, Middle Badda, Dhaka", "Apartment", 22_000, 2, 2, 950, False,
     "photo-1600607687939-ce8a6c25118c", "A two-bedroom flat on a quiet lane, ten minutes from Gulshan 1. South-facing balcony.", (44_000, 7, 12, False, "any")),
    ("mohakhali-office", "owner", "rent", "Office floor near Mohakhali flyover", "Mohakhali", "Dhaka", "Mohakhali C/A, Dhaka", "Commercial", 180_000, 0, 2, 2400, False,
     None, "An open-plan office floor with two washrooms, a lift and 24-hour security. Suitable for a software or design firm.", (540_000, 20, 24, False, "any")),
    ("banani-office", "owner2", "rent", "Small office space on Banani Road 11", "Banani", "Dhaka", "Road 11, Banani, Dhaka", "Commercial", 85_000, 0, 1, 900, False,
     None, "A ready office space on the third floor of a commercial building, with reception area and one washroom.", (255_000, 15, 12, False, "any")),
    ("motijheel-commercial", "owner3", "sale", "Commercial floor in Motijheel", "Motijheel", "Dhaka", "Dilkusha C/A, Motijheel, Dhaka", "Commercial", 32_000_000, 0, 2, 3000, False,
     None, "A full commercial floor in the main business area, close to banks and offices. Lift, generator and parking available.", None),
    ("purbachal-plot", "owner", "sale", "Residential plot in Purbachal", "Purbachal Sector 4", "Dhaka", "Sector 4, Purbachal New Town, Dhaka", "Plot", 9_500_000, 0, 0, 3600, False,
     None, "A 5 katha RAJUK residential plot on a 40-feet road. All utility lines are planned for the sector.", None),
    ("keraniganj-plot", "owner3", "sale", "Plot near the Dhaka-Mawa highway", "Keraniganj", "Dhaka", "Zinjira, Keraniganj, Dhaka", "Plot", 3_800_000, 0, 0, 2880, False,
     None, "A 4 katha plot on a raised piece of land, a short drive from the Padma Bridge road.", None),
    ("mirpur-dohs", "owner2", "sale", "Corner flat in Mirpur DOHS", "Mirpur DOHS", "Dhaka", "Avenue 3, Mirpur DOHS, Dhaka", "Apartment", 14_500_000, 3, 3, 1650, False,
     "photo-1600607687939-ce8a6c25118c", "A corner flat with three balconies in a well-managed DOHS area. Open views and a playground nearby.", None),
    ("wari-house", "owner3", "sale", "Old Dhaka family house in Wari", "Wari", "Dhaka", "Rankin Street, Wari, Dhaka", "House", 22_000_000, 5, 4, 3200, False,
     "photo-1600585154340-be6161a56a0c", "A two-storey family house with a courtyard, on one of the older and quieter streets of Wari.", None),
    ("khulshi-rent", "owner2", "rent", "Hillside apartment in Khulshi", "Khulshi", "Chattogram", "Road 2, Khulshi, Chattogram", "Apartment", 40_000, 3, 3, 1500, False,
     "photo-1600047509807-ba8f99d2cdde", "A bright apartment on the hill side of Khulshi with a view of the green. Generator backup and one parking space.", (80_000, 10, 12, False, "family")),
    ("agrabad-office", "owner3", "rent", "Office suite in Agrabad", "Agrabad", "Chattogram", "Agrabad C/A, Chattogram", "Commercial", 120_000, 0, 2, 1800, False,
     None, "An office suite near the port and the banks of Agrabad. Fitted with partitions and air conditioning.", (360_000, 30, 24, False, "any")),
    ("nasirabad-flat", "owner", "sale", "Three-bed flat in Nasirabad", "Nasirabad", "Chattogram", "Nasirabad Housing, Chattogram", "Apartment", 9_800_000, 3, 2, 1350, False,
     "photo-1600566753086-00f18fb6b3ea", "A practical family flat in a gated housing society, near schools and shops.", None),
    ("uposhohor-house", "owner2", "sale", "Two-storey house in Uposhohor", "Uposhohor", "Sylhet", "Block B, Uposhohor, Sylhet", "House", 18_500_000, 4, 3, 2400, False,
     "photo-1600585154340-be6161a56a0c", "A two-storey house with a small garden and roof space, in a calm residential area of Sylhet.", None),
    ("shibganj-plot", "owner3", "sale", "Plot in Shibganj", "Shibganj", "Sylhet", "Shibganj, Sylhet", "Plot", 4_200_000, 0, 0, 2160, False,
     None, "A 3 katha plot beside a paved road, suitable for a family house.", None),
    ("kazla-flat", "owner", "rent", "Flat near Rajshahi University", "Kazla", "Rajshahi", "Kazla, Rajshahi", "Apartment", 12_000, 2, 1, 850, False,
     "photo-1600607687644-c7171b42498f", "A two-bedroom flat five minutes from the university gate. Popular with students and teachers.", (24_000, 3, 6, False, "bachelor")),
    ("rajshahi-house", "owner3", "sale", "House with a garden in Uposhahar", "Uposhahar", "Rajshahi", "Sector 2, Uposhahar, Rajshahi", "House", 11_000_000, 3, 2, 1800, False,
     "photo-1600585154340-be6161a56a0c", "A single-storey house with a front garden and mango trees, in a quiet part of Rajshahi.", None),
    ("sonadanga-flat", "owner2", "rent", "Apartment in Sonadanga", "Sonadanga", "Khulna", "Sonadanga R/A, Khulna", "Apartment", 16_000, 2, 2, 1000, False,
     "photo-1600210492486-724fe5c67fb0", "A two-bedroom apartment near the bus terminal, with a balcony and a car garage.", (32_000, 12, 12, False, "family")),
    ("khalishpur-flat", "owner3", "sale", "New flat in Khalishpur", "Khalishpur", "Khulna", "Khalishpur, Khulna", "Apartment", 6_500_000, 3, 2, 1300, False,
     "photo-1600607687939-ce8a6c25118c", "A newly built flat with tiled floors and a lift, near the Khalishpur industrial area.", None),
    ("barishal-flat", "owner", "rent", "Riverside flat in Barishal", "Band Road", "Barishal", "Band Road, Barishal Sadar", "Apartment", 14_000, 2, 1, 900, False,
     "photo-1600047509807-ba8f99d2cdde", "A two-bedroom flat near the Kirtankhola river, close to the launch terminal.", (28_000, 5, 12, False, "family")),
    ("rangpur-plot", "owner2", "sale", "Plot in Rangpur town", "Dhap", "Rangpur", "Dhap, Rangpur", "Plot", 2_800_000, 0, 0, 1800, False,
     None, "A 2.5 katha plot in a developing residential block of Rangpur town.", None),
    ("charpara-flat", "owner3", "rent", "Flat near Mymensingh Medical College", "Charpara", "Mymensingh", "Charpara, Mymensingh", "Apartment", 13_000, 2, 1, 850, False,
     "photo-1600566753086-00f18fb6b3ea", "A two-bedroom flat a short walk from the medical college. Suits doctors, nurses and students.", (26_000, 0, 6, False, "any")),
]

VERIFIED = ["banani", "dhanmondi-studio", "uttara", "panchlaish", "zindabazar",
            "gulshan1-serviced", "mirpur-dohs", "motijheel-commercial", "uposhohor-house", "rajshahi-house"]
PENDING_READY = ["khulshi-rent", "wari-house", "dhanmondi-lake", "gulshan"]
PENDING_INCOMPLETE = {"mirpur": ["land_deed"], "charpara-flat": ["land_deed", "tax_receipt"]}
ISSUE_FOUND = {
    "bashundhara": ("mutation", "The mutation paper is for plot 14 but the deed is for plot 41. Please upload the mutation paper for the correct plot."),
    "khalishpur-flat": ("tax_receipt", "The tax receipt is from 2021. Please upload the land development tax receipt for this year."),
}
# Already picked up by the second advocate, so the queue shows a review in progress.
IN_REVIEW = {"bashundhara-rent": "advocate2"}
HIGH_DEMAND_AREAS = ["Gulshan", "Banani"]
# Sprint 3: verified listings where the advocate did more than check the papers (PB-19).
BADGE_LEVELS = {"banani": "fully_verified", "uttara": "site_visited"}
CONSULTATION_FEES = {"advocate": 500, "advocate2": 700}


def sample_pdf(lines):
    """Build a small, valid one-page PDF that stands in for a scanned paper."""
    def escape(text):
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    stream = "BT /F1 14 Tf 72 740 Td 22 TL " + " ".join(f"({escape(line)}) '" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode("latin-1")
    output += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("latin-1")
    return output


def seed(connection, upload_dir):
    now = datetime.now(timezone.utc)

    def at(days_ago, hours=0):
        return (now - timedelta(days=days_ago, hours=hours)).isoformat(timespec="seconds")

    users = {}
    for key, name, email, phone, role in USERS:
        cursor = connection.execute(
            "INSERT INTO users (full_name, email, phone, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            # Hashed separately for each account, so every account gets its own salt.
            (name, email, phone, hash_password(DEMO_PASSWORD), role, at(30)),
        )
        users[key] = cursor.lastrowid
    for key, (bar_id, specialization) in ADVOCATES.items():
        connection.execute(
            "INSERT INTO advocate_profiles (user_id, bar_council_id, specialization, added_by, added_at) VALUES (?, ?, ?, ?, ?)",
            (users[key], bar_id, specialization, users["admin"], at(29)),
        )
        audit(connection, users["admin"], "advocate_added", "user", users[key], None, "active", "Demo data")
    for key, (bar_id, specialization) in ADVOCATE_APPLICANTS.items():
        connection.execute(
            """INSERT INTO advocate_profiles (user_id, bar_council_id, specialization, added_at, verification_status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (users[key], bar_id, specialization, at(2)),
        )
        audit(connection, users[key], "advocate_applied", "user", users[key], None, "pending", "Demo data")

    properties = {}
    for index, (key, owner, kind, title, area, city, address, ptype, amount, beds, baths, sqft, furnished, photo, desc, rent) in enumerate(LISTINGS):
        created = at(60 - index)
        cursor = connection.execute(
            """INSERT INTO properties (owner_id, title, description, listing_type, property_type, price, area_name, city,
                                       address, size_sqft, bedrooms, bathrooms, furnished, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (users[owner], title, desc, kind, ptype, amount if kind == "sale" else None, area, city, address, sqft,
             beds, baths, int(furnished), created, created),
        )
        property_id = cursor.lastrowid
        properties[key] = (property_id, owner, title)
        if rent:
            deposit, available_in_days, lease, utilities, preference = rent
            connection.execute(
                """INSERT INTO rent_details (property_id, monthly_rent, security_deposit, available_from,
                                             min_lease_months, utilities_included, tenant_preference)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (property_id, amount, deposit, (date.today() + timedelta(days=available_in_days)).isoformat(), lease, int(utilities), preference),
            )
        if photo:
            connection.execute(
                "INSERT INTO property_images (property_id, image_url, caption, is_primary, uploaded_at) VALUES (?, ?, ?, 1, ?)",
                (property_id, f"https://images.unsplash.com/{photo}?auto=format&fit=crop&w=1100&q=80", title, created),
            )
        audit(connection, users[owner], "listing_created", "property", property_id, None, "active / unverified", title)

    def add_documents(request_id, owner_key, title, types, uploaded_at, review_status="not_checked"):
        for document_type in types:
            storage_name = f"{secrets.token_hex(16)}.pdf"
            label = document_type.replace("_", " ").title()
            body = sample_pdf([f"SAMPLE {label.upper()}", f"Property: {title}", "Demo document for the PFB project.", "Not a real legal paper."])
            (upload_dir / storage_name).write_bytes(body)
            connection.execute(
                """INSERT INTO legal_documents (request_id, document_type, file_name, file_type, file_size_kb, storage_name,
                                                review_status, uploaded_by, uploaded_at)
                   VALUES (?, ?, ?, 'pdf', ?, ?, ?, ?, ?)""",
                (request_id, document_type, f"{document_type}.pdf", max(1, round(len(body) / 1024)), storage_name,
                 review_status, users[owner_key], uploaded_at),
            )
            audit(connection, users[owner_key], "document_uploaded", "verification_request", request_id, None, document_type, f"{document_type}.pdf")

    def add_request(key, status, days_ago, documents, notes=None, checklist=None, advocate="advocate"):
        property_id, owner_key, title = properties[key]
        submitted = at(days_ago)
        cursor = connection.execute(
            "INSERT INTO verification_requests (property_id, owner_id, status, submitted_at) VALUES (?, ?, 'pending', ?)",
            (property_id, users[owner_key], submitted),
        )
        request_id = cursor.lastrowid
        audit(connection, users[owner_key], "verification_requested", "verification_request", request_id, None, "pending", f"Property #{property_id}: {title}")
        add_documents(request_id, owner_key, title, documents, submitted)
        if status == "in_review":
            connection.execute(
                "UPDATE verification_requests SET status = 'in_review', advocate_id = ?, assigned_at = ? WHERE id = ?",
                (users[advocate], at(days_ago - 1), request_id),
            )
            audit(connection, users[advocate], "verification_status_changed", "verification_request", request_id, "pending", "in_review", "Review started")
        if status in ("document_verified", "issue_found"):
            connection.execute(
                """UPDATE verification_requests SET status = ?, advocate_id = ?, assigned_at = ?, completed_at = ?,
                       advocate_notes = ?, checklist = ? WHERE id = ?""",
                (status, users[advocate], at(days_ago - 1), at(days_ago - 2), notes, json.dumps(checklist), request_id),
            )
            for document_type, result in checklist.items():
                connection.execute(
                    "UPDATE legal_documents SET review_status = ? WHERE request_id = ? AND document_type = ?",
                    (result, request_id, document_type),
                )
            audit(connection, users[advocate], "verification_status_changed", "verification_request", request_id, "pending", "in_review", "Review started")
            audit(connection, users[advocate], "verification_status_changed", "verification_request", request_id, "in_review", status, notes)
            connection.execute(
                "UPDATE properties SET verification_status = ?, badge_level = ? WHERE id = ?",
                (status, "document_verified" if status == "document_verified" else "none", property_id),
            )
            audit(connection, users[advocate], "verification_status_changed", "property", property_id, "unverified", status, f"Decision on request #{request_id}")

    all_ok = {item: "ok" for item in ("land_deed", "mutation", "tax_receipt", "ownership_history")}
    for offset, key in enumerate(VERIFIED):
        add_request(key, "document_verified", 20 - offset, ["land_deed", "mutation", "tax_receipt"],
                    notes="Deed, mutation and tax receipt match the owner and the plot. Ownership chain is clear.",
                    checklist=all_ok, advocate="advocate" if offset % 2 == 0 else "advocate2")
    for key, (problem, notes) in ISSUE_FOUND.items():
        add_request(key, "issue_found", 6, ["land_deed", "mutation", "tax_receipt"], notes=notes,
                    checklist={**all_ok, problem: "problem"})
    for key, advocate in IN_REVIEW.items():
        add_request(key, "in_review", 5, ["land_deed", "mutation", "tax_receipt", "ownership_history"], advocate=advocate)
    # Gulshan is submitted last, so it reaches the top of the queue only because it is a high-demand area.
    for offset, key in enumerate(PENDING_READY):
        add_request(key, "pending", 5 - offset, ["land_deed", "mutation", "tax_receipt"])
    for key, documents in PENDING_INCOMPLETE.items():
        add_request(key, "pending", 1, documents)

    for area in HIGH_DEMAND_AREAS:
        cursor = connection.execute(
            "INSERT INTO high_demand_areas (area_name, added_by, created_at) VALUES (?, ?, ?)", (area, users["admin"], at(25))
        )
        audit(connection, users["admin"], "high_demand_area_added", "high_demand_area", cursor.lastrowid, None, area)

    senders = {"tenant": ("Rafi Chowdhury", "01710000004"), "tenant2": ("Sumaiya Islam", "01710000008")}
    inquiries = [
        ("dhanmondi-lake", "tenant", "Hi, is the flat still available from next month? We are a family of three.", 2, None),
        ("gulshan", "tenant2", "Is the price negotiable? I would also like to know the monthly service charge.", 4,
         "Thank you for asking. The price is a little negotiable and the service charge is 6,000 taka a month."),
        ("kazla-flat", "tenant2", "Can two students share this flat? When can we visit?", 1, None),
        ("purbachal-plot", "tenant", "Has RAJUK handed over the plot, and is the road already built?", 3, None),
    ]
    for key, sender, message, days_ago, reply in inquiries:
        name, phone = senders[sender]
        connection.execute(
            """INSERT INTO inquiries (property_id, sender_id, sender_name, sender_phone, message, status, reply_message,
                                      created_at, replied_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (properties[key][0], users[sender], name, phone, message, "replied" if reply else "new", reply,
             at(days_ago), at(days_ago - 1) if reply else None),
        )
    for sender, key in (("tenant", "banani"), ("tenant", "uttara-rent"), ("tenant2", "gulshan"), ("tenant2", "kazla-flat")):
        connection.execute(
            "INSERT INTO favorites (user_id, property_id, saved_at) VALUES (?, ?, ?)", (users[sender], properties[key][0], at(2))
        )
    seed_browsing(connection, users, properties, at)
    seed_sprint3(connection, users, properties, at, now)
    seed_sprint4(connection, users, properties, at, now)


# Searches the demo tenants made (before the demo starts), for the History page.
DEMO_SEARCHES = [
    ("tenant", {"purpose": "rent", "area": "Uttara", "maxPrice": "40000"}, 6),
    ("tenant", {"purpose": "rent", "bedrooms": "2", "verified": "1"}, 4),
    ("tenant", {"purpose": "rent", "area": "Dhanmondi"}, 3),
    ("tenant2", {"purpose": "sale", "area": "Gulshan"}, 5),
    ("tenant2", {"purpose": "rent", "area": "Rajshahi", "maxPrice": "15000"}, 1),
    ("tenant2", {"type": "Plot"}, 2),
]
# Listings the demo tenants opened: (who, listing, how many days ago, how they found it).
DEMO_VIEWS = [
    ("tenant", "uttara-rent", 6, "search"), ("tenant", "banani", 4, "search"), ("tenant", "dhanmondi-lake", 3, "search"),
    ("tenant", "dhanmondi-studio", 3, "search"), ("tenant", "banani", 2, "favorites"), ("tenant", "purbachal-plot", 1, "direct"),
    ("tenant2", "gulshan", 5, "search"), ("tenant2", "gulshan1-serviced", 5, "search"), ("tenant2", "kazla-flat", 1, "search"),
    ("tenant2", "keraniganj-plot", 2, "search"), ("tenant2", "gulshan", 1, "favorites"),
]


def count_matches(filters):
    """Count demo listings that match a search, so saved result counts are realistic."""
    count = 0
    for key, _owner, kind, _title, area, city, address, ptype, amount, beds, *_rest in LISTINGS:
        text = f"{area} {city} {address}".lower()
        if filters.get("purpose") and kind != filters["purpose"]:
            continue
        if filters.get("area") and filters["area"].lower() not in text:
            continue
        if filters.get("type") and ptype != filters["type"]:
            continue
        if filters.get("maxPrice") and amount > int(filters["maxPrice"]):
            continue
        if filters.get("bedrooms") and beds < int(filters["bedrooms"]):
            continue
        if filters.get("verified") and key not in VERIFIED:
            continue
        count += 1
    return count


def seed_browsing(connection, users, properties, at):
    # Guest visits, spread over the last week (more for some listings than others).
    for index, (property_id, _owner, _title) in enumerate(properties.values()):
        for n in range((index * 7) % 9 + 1):
            connection.execute(
                "INSERT INTO property_views (property_id, user_id, source, viewed_at) VALUES (?, NULL, ?, ?)",
                (property_id, ("search", "direct")[n % 2], at(n % 7, hours=index % 12)),
            )
    for who, key, days_ago, source in DEMO_VIEWS:
        connection.execute(
            "INSERT INTO property_views (property_id, user_id, source, viewed_at) VALUES (?, ?, ?, ?)",
            (properties[key][0], users[who], source, at(days_ago, hours=3)),
        )
    for who, filters, days_ago in DEMO_SEARCHES:
        connection.execute(
            "INSERT INTO search_history (user_id, filters, result_count, searched_at) VALUES (?, ?, ?, ?)",
            (users[who], json.dumps(filters, sort_keys=True), count_matches(filters), at(days_ago, hours=4)),
        )


def seed_sprint3(connection, users, properties, at, now):
    """Legal reports, badge levels, consultations, payments and notifications (PB-18 to PB-25)."""
    connection.execute("UPDATE advocate_profiles SET consultation_fee = 500 WHERE consultation_fee = 0")
    for key, fee in CONSULTATION_FEES.items():
        connection.execute("UPDATE advocate_profiles SET consultation_fee = ? WHERE user_id = ?", (fee, users[key]))
    for key, level in BADGE_LEVELS.items():
        connection.execute("UPDATE properties SET badge_level = ? WHERE id = ?", (level, properties[key][0]))
    for (request_id,) in connection.execute("SELECT id FROM verification_requests WHERE status = 'document_verified'").fetchall():
        reports.ensure_report(connection, request_id)

    def slot(days_ahead, hour):
        """A slot on a working day (not Friday), in Bangladesh time."""
        day = (now + timedelta(hours=6)).date() + timedelta(days=days_ahead)
        if day.weekday() == 4:
            day += timedelta(days=1)
        return f"{day.isoformat()}T{hour:02d}:00"

    def consultation(client, advocate, key, kind, status, slot_start=None, notes=None, days_ago=2):
        fee = 0 if kind == "free_chat" else CONSULTATION_FEES[advocate]
        return connection.execute(
            """INSERT INTO consultations (property_id, client_id, advocate_id, kind, slot_start, fee, status, follow_up_notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (properties[key][0], users[client], users[advocate], kind, slot_start, fee, status, notes, at(days_ago)),
        ).lastrowid

    def paid(consultation_id, advocate, method, reference, days_ago):
        connection.execute(
            """INSERT INTO payments (consultation_id, amount, method, status, transaction_ref, created_at, paid_at)
               VALUES (?, ?, ?, 'paid', ?, ?, ?)""",
            (consultation_id, CONSULTATION_FEES[advocate], method, reference, at(days_ago), at(days_ago)),
        )

    # A free question with an answer (PB-21).
    chat = consultation("tenant", "advocate", "banani", "free_chat", "confirmed")
    for sender, body, hours in (
        ("tenant", "Hello, is there any bank loan or mortgage on this flat that I should know about?", 30),
        ("advocate", "Hello. The deed and the mutation record show no mortgage or charge on this flat. "
                     "Ask the owner for a recent non-encumbrance certificate before you pay the booking money.", 26),
    ):
        connection.execute(
            "INSERT INTO chat_messages (consultation_id, sender_id, body, sent_at) VALUES (?, ?, ?, ?)",
            (chat, users[sender], body, at(0, hours=hours)),
        )
    # Paid consultations in every state (PB-22 to PB-24).
    booked = consultation("tenant", "advocate", "uttara", "paid", "confirmed", slot(1, 10))
    paid(booked, "advocate", "bkash", "PFB-DEMO000001", 1)
    waiting_payment = consultation("tenant", "advocate2", "dhanmondi-studio", "paid", "confirmed", slot(2, 16), days_ago=1)
    waiting_advocate = consultation("tenant2", "advocate", "banani", "paid", "requested", slot(1, 11), days_ago=0)
    done = consultation(
        "tenant2", "advocate2", "panchlaish", "paid", "completed", (now - timedelta(days=3)).strftime("%Y-%m-%dT15:00"),
        notes="We went through the deed and the mutation paper together. Before you sign: 1) see the original deed, "
              "2) collect the latest tax receipt, 3) register the sale deed at the sub-registry office and keep the receipt.",
        days_ago=6,
    )
    paid(done, "advocate2", "nagad", "PFB-DEMO000002", 5)

    # Unread notifications, so the bell shows a count for each demo account (PB-25).
    verified_request = connection.execute(
        "SELECT id FROM verification_requests WHERE property_id = ? ORDER BY id DESC LIMIT 1", (properties["banani"][0],)
    ).fetchone()[0]
    pending_request = connection.execute(
        "SELECT id FROM verification_requests WHERE property_id = ? ORDER BY id DESC LIMIT 1", (properties["gulshan"][0],)
    ).fetchone()[0]
    notify(connection, users[properties["banani"][1]], "verification_result", "Your property is Document Verified",
           f"{properties['banani'][2]} now shows the Verified badge. Buyers can download its legal report.",
           f"/owner/verification/{verified_request}")
    notify(connection, users["advocate"], "verification_request", "New verification request",
           f"{properties['gulshan'][2]} is waiting in the queue.", f"/advocate/requests/{pending_request}")
    notify(connection, users["advocate"], "consultation", "New consultation request",
           "Sumaiya Islam asked for a paid consultation.", f"/consultations/{waiting_advocate}")
    notify(connection, users["tenant"], "chat_message", "Adv. Sarah Rahman replied to your question",
           "The deed and the mutation record show no mortgage or charge on this flat.", f"/consultations/{chat}")
    notify(connection, users["tenant"], "consultation", "Your consultation was accepted",
           "Adv. Mahmud Karim accepted your slot. Pay the fee of 700 taka to confirm the booking.",
           f"/consultations/{waiting_payment}")
    notify(connection, users["tenant2"], "consultation", "Follow-up notes from your advocate",
           "Adv. Mahmud Karim added notes after your consultation.", f"/consultations/{done}")


def seed_sprint4(connection, users, properties, at, now):
    """Rent agreements, saved searches and listing reports (PB-26 to PB-30)."""
    from .sprint4 import add_months

    today = (now + timedelta(hours=6)).date()

    def agreement(key, tenant, status, start_in_days, months, reviewer=None, landlord_signed=False, special=None):
        property_id, owner_key, title = properties[key]
        rent = connection.execute("SELECT * FROM rent_details WHERE property_id = ?", (property_id,)).fetchone()
        start = today + timedelta(days=start_in_days)
        submitted = at(2) if status != "draft" else None
        reviewed = at(1) if status in ("approved", "signed") else None
        agreement_id = connection.execute(
            """INSERT INTO rent_agreements (property_id, landlord_id, tenant_id, reviewer_id, start_date, end_date, lease_months,
                   monthly_rent, security_deposit, utilities_included, special_terms, status, submitted_at, reviewed_at,
                   landlord_signed_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (property_id, users[owner_key], users[tenant], users[reviewer] if reviewer else None, start.isoformat(),
             add_months(start, months).isoformat(), months, rent["monthly_rent"], rent["security_deposit"],
             rent["utilities_included"], special, status, submitted, reviewed, at(0, hours=20) if landlord_signed else None, at(3)),
        ).lastrowid
        audit(connection, users[owner_key], "agreement_created", "rent_agreement", agreement_id, None, "draft", title)
        if status != "draft":
            audit(connection, users[owner_key], "agreement_status_changed", "rent_agreement", agreement_id, "draft", "under_review", title)
        if reviewer:
            audit(connection, users[reviewer], "agreement_status_changed", "rent_agreement", agreement_id, "under_review", status, None)
        return agreement_id

    # Approved and signed by the landlord: the tenant can sign it in the demo.
    approved = agreement("dhanmondi-studio", "tenant", "approved", 14, 12, reviewer="advocate", landlord_signed=True,
                         special="The tenant may keep one small pet.")
    # Waiting for an advocate to review it.
    waiting = agreement("banani", "tenant2", "under_review", 20, 24)
    notify(connection, users["tenant"], "agreement", "Please sign the rent agreement",
           f"Nadia Rahman signed the agreement for {properties['dhanmondi-studio'][2]}.", f"/agreements/{approved}")
    notify(connection, users["advocate"], "agreement", "A rent agreement needs review",
           f"{properties['banani'][2]}: Tanvir Hasan and Sumaiya Islam.", f"/agreements/{waiting}")

    # Saved searches (PB-28). Verifying "Easy, airy living by the lake" (the Sprint 2 demo) alerts the first tenant.
    for who, filters, days_ago in (
        ("tenant", {"purpose": "rent", "area": "Dhanmondi"}, 4),
        ("tenant", {"purpose": "rent", "bedrooms": "2", "maxPrice": "40000"}, 3),
        ("tenant2", {"purpose": "sale", "area": "Gulshan"}, 5),
    ):
        connection.execute("INSERT INTO saved_searches (user_id, filters, created_at) VALUES (?, ?, ?)",
                           (users[who], json.dumps(filters, sort_keys=True), at(days_ago)))

    # Reports of suspicious listings waiting for the admin (PB-30).
    for who, key, reason, details, days_ago in (
        ("tenant2", "purbachal-plot", "fake", "The plot number is not in the RAJUK allotment list I checked.", 1),
        ("tenant", "purbachal-plot", "wrong_details", "The price is far below every other plot in Sector 4.", 2),
        ("tenant", "wari-house", "already_gone", "The neighbours say this house was sold last month.", 3),
    ):
        report_id = connection.execute(
            "INSERT INTO listing_reports (property_id, reporter_id, reason, details, created_at) VALUES (?, ?, ?, ?, ?)",
            (properties[key][0], users[who], reason, details, at(days_ago)),
        ).lastrowid
        audit(connection, users[who], "listing_reported", "property", properties[key][0], None, reason, details)
    notify(connection, users["admin"], "listing_report", "A listing was reported",
           f"{properties['purbachal-plot'][2]}: The listing looks fake.", "/admin?tab=reports")
