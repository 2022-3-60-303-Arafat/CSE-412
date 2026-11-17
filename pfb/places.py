"""Places for the map and "near me" search (PB-37).

Coordinates are approximate centres (to about 300 m), good enough to sort homes by distance.
A listing without its own map pin is placed at the centre of its area, or of its district.
"""

# District (division city) centres, used when an area is not in AREA_CENTRES.
CITY_CENTRES = {
    "Dhaka": (23.8103, 90.4125),
    "Chattogram": (22.3569, 91.7832),
    "Sylhet": (24.8949, 91.8687),
    "Rajshahi": (24.3745, 88.6042),
    "Khulna": (22.8456, 89.5403),
    "Barishal": (22.7010, 90.3535),
    "Rangpur": (25.7439, 89.2752),
    "Mymensingh": (24.7471, 90.4203),
}

# Area centres, keyed by (district, area in lower case).
AREA_CENTRES = {
    ("Dhaka", "badda"): (23.7806, 90.4267),
    ("Dhaka", "banani"): (23.7937, 90.4066),
    ("Dhaka", "banasree"): (23.7633, 90.4337),
    ("Dhaka", "baridhara"): (23.8007, 90.4206),
    ("Dhaka", "bashundhara r/a"): (23.8193, 90.4526),
    ("Dhaka", "dhanmondi"): (23.7461, 90.3742),
    ("Dhaka", "gulshan"): (23.7925, 90.4078),
    ("Dhaka", "gulshan 1"): (23.7808, 90.4167),
    ("Dhaka", "gulshan 2"): (23.7946, 90.4142),
    ("Dhaka", "keraniganj"): (23.6985, 90.3451),
    ("Dhaka", "mirpur"): (23.8223, 90.3654),
    ("Dhaka", "mirpur 10"): (23.8069, 90.3687),
    ("Dhaka", "mirpur dohs"): (23.8366, 90.3693),
    ("Dhaka", "mohakhali"): (23.7781, 90.4006),
    ("Dhaka", "mohammadpur"): (23.7662, 90.3589),
    ("Dhaka", "motijheel"): (23.7330, 90.4172),
    ("Dhaka", "purbachal"): (23.8400, 90.5000),
    ("Dhaka", "purbachal sector 4"): (23.8460, 90.5050),
    ("Dhaka", "shyamoli"): (23.7743, 90.3653),
    ("Dhaka", "uttara"): (23.8740, 90.3960),
    ("Dhaka", "uttara sector 7"): (23.8698, 90.4006),
    ("Dhaka", "uttara sector 11"): (23.8759, 90.3925),
    ("Dhaka", "wari"): (23.7186, 90.4210),
    ("Chattogram", "agrabad"): (22.3248, 91.8125),
    ("Chattogram", "halishahar"): (22.3330, 91.7780),
    ("Chattogram", "khulshi"): (22.3603, 91.8094),
    ("Chattogram", "nasirabad"): (22.3643, 91.8226),
    ("Chattogram", "panchlaish"): (22.3617, 91.8340),
    ("Barishal", "band road"): (22.6987, 90.3700),
    ("Mymensingh", "charpara"): (24.7568, 90.4073),
    ("Rangpur", "dhap"): (25.7480, 89.2580),
    ("Rajshahi", "kazla"): (24.3634, 88.6276),
    ("Rajshahi", "uposhahar"): (24.3743, 88.5996),
    ("Khulna", "khalishpur"): (22.8573, 89.5345),
    ("Khulna", "sonadanga"): (22.8166, 89.5426),
    ("Sylhet", "shibganj"): (24.8930, 91.8840),
    ("Sylhet", "uposhohor"): (24.8901, 91.8858),
    ("Sylhet", "zindabazar"): (24.8958, 91.8686),
}

# Places people commute to: universities, business districts, hospitals and the airport.
LANDMARKS = [
    {"id": "du", "name": "University of Dhaka", "city": "Dhaka", "lat": 23.7340, "lng": 90.3928},
    {"id": "buet", "name": "BUET", "city": "Dhaka", "lat": 23.7265, "lng": 90.3925},
    {"id": "nsu", "name": "North South University (Bashundhara)", "city": "Dhaka", "lat": 23.8151, "lng": 90.4255},
    {"id": "bracu", "name": "BRAC University (Merul Badda)", "city": "Dhaka", "lat": 23.7726, "lng": 90.4258},
    {"id": "ewu", "name": "East West University (Aftabnagar)", "city": "Dhaka", "lat": 23.7689, "lng": 90.4256},
    {"id": "motijheel", "name": "Motijheel commercial area", "city": "Dhaka", "lat": 23.7330, "lng": 90.4172},
    {"id": "gulshan1", "name": "Gulshan 1 circle", "city": "Dhaka", "lat": 23.7808, "lng": 90.4167},
    {"id": "karwan", "name": "Karwan Bazar", "city": "Dhaka", "lat": 23.7510, "lng": 90.3935},
    {"id": "dmch", "name": "Dhaka Medical College Hospital", "city": "Dhaka", "lat": 23.7257, "lng": 90.3976},
    {"id": "airport", "name": "Hazrat Shahjalal Airport", "city": "Dhaka", "lat": 23.8433, "lng": 90.3978},
    {"id": "uttara-house", "name": "Uttara house building", "city": "Dhaka", "lat": 23.8737, "lng": 90.4005},
    {"id": "agrabad", "name": "Agrabad commercial area", "city": "Chattogram", "lat": 22.3248, "lng": 91.8125},
    {"id": "gec", "name": "GEC circle", "city": "Chattogram", "lat": 22.3590, "lng": 91.8220},
    {"id": "cmch", "name": "Chittagong Medical College", "city": "Chattogram", "lat": 22.3594, "lng": 91.8318},
    {"id": "sust", "name": "Shahjalal University (SUST)", "city": "Sylhet", "lat": 24.9180, "lng": 91.8320},
    {"id": "zindabazar", "name": "Zindabazar", "city": "Sylhet", "lat": 24.8958, "lng": 91.8686},
    {"id": "ru", "name": "University of Rajshahi", "city": "Rajshahi", "lat": 24.3636, "lng": 88.6280},
    {"id": "ku", "name": "Khulna University", "city": "Khulna", "lat": 22.8030, "lng": 89.5340},
    {"id": "barishal-centre", "name": "Barishal city centre", "city": "Barishal", "lat": 22.7010, "lng": 90.3535},
    {"id": "brur", "name": "Begum Rokeya University", "city": "Rangpur", "lat": 25.7193, "lng": 89.2603},
    {"id": "bau", "name": "Bangladesh Agricultural University", "city": "Mymensingh", "lat": 24.7258, "lng": 90.4310},
]
LANDMARKS_BY_ID = {landmark["id"]: landmark for landmark in LANDMARKS}

# Bangladesh, roughly: a map pin outside this box is refused.
LATITUDE_RANGE = (20.5, 26.7)
LONGITUDE_RANGE = (88.0, 92.7)


def default_location(area_name, city):
    """The area centre, then a shorter area name ('Gulshan 2' -> 'Gulshan'), then the district centre."""
    area = (area_name or "").strip().lower()
    while area:
        if (city, area) in AREA_CENTRES:
            return AREA_CENTRES[(city, area)]
        area = area.rsplit(" ", 1)[0] if " " in area else ""
    return CITY_CENTRES.get(city)
