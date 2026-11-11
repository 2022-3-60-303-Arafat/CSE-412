"""Input checks that turn bad form values into clear, per-field error messages."""

import re
from datetime import date, timedelta

from .db import PROPERTY_TYPES
from .web import ApiError

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Bangladeshi mobile numbers: 01XXXXXXXXX, optionally with +88 / 88 in front.
PHONE_PATTERN = re.compile(r"^(?:\+?88)?01[3-9]\d{8}$")
CITIES = ("Dhaka", "Chattogram", "Sylhet", "Rajshahi", "Khulna", "Barishal", "Rangpur", "Mymensingh")
TENANT_PREFERENCES = ("family", "bachelor", "any")
MAX_SALE_PRICE = 100_000_000_000
MAX_MONTHLY_RENT = 100_000_000


class Checker:
    """Collects one message per field, then raises them together."""

    def __init__(self, data):
        self.data = data
        self.errors = {}
        self.clean = {}

    def fail(self, field, message):
        self.errors.setdefault(field, message)

    def text(self, field, label, min_length=1, max_length=200, required=True):
        value = self.data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            if required:
                self.fail(field, f"{label} is required.")
            else:
                self.clean[field] = ""
            return None
        if not isinstance(value, str):
            self.fail(field, f"{label} must be text.")
            return None
        value = value.strip()
        if len(value) < min_length:
            self.fail(field, f"{label} must be at least {min_length} characters.")
        elif len(value) > max_length:
            self.fail(field, f"{label} must be at most {max_length} characters.")
        else:
            self.clean[field] = value
            return value
        return None

    def integer(self, field, label, minimum, maximum, required=True, default=None):
        value = self.data.get(field)
        if value is None or value == "":
            if required:
                self.fail(field, f"{label} is required.")
            else:
                self.clean[field] = default
            return default
        if isinstance(value, bool):
            self.fail(field, f"{label} must be a whole number.")
            return None
        if isinstance(value, str):
            value = value.strip().replace(",", "")
        try:
            number = int(value)
            if isinstance(value, float) and value != number:
                raise ValueError
        except (TypeError, ValueError):
            self.fail(field, f"{label} must be a whole number.")
            return None
        if number < minimum:
            if minimum == 1:
                self.fail(field, f"{label} must be more than 0.")
            elif minimum == 0:
                self.fail(field, f"{label} cannot be negative.")
            else:
                self.fail(field, f"{label} must be at least {minimum:,}.")
            return None
        if number > maximum:
            self.fail(field, f"{label} must be at most {maximum:,}.")
            return None
        self.clean[field] = number
        return number

    def choice(self, field, label, options, required=True, default=None):
        value = self.data.get(field)
        if value in (None, ""):
            if required:
                self.fail(field, f"Choose a {label.lower()}.")
            else:
                self.clean[field] = default
            return default
        if value not in options:
            self.fail(field, f"Choose a valid {label.lower()}.")
            return None
        self.clean[field] = value
        return value

    def boolean(self, field, default=False):
        value = self.data.get(field, default)
        self.clean[field] = value is True or value in ("true", "1", 1, "on")
        return self.clean[field]

    def date(self, field, label, earliest=None, latest=None):
        value = self.data.get(field)
        if not value:
            self.fail(field, f"{label} is required.")
            return None
        try:
            parsed = date.fromisoformat(str(value))
        except ValueError:
            self.fail(field, f"{label} must be a valid date.")
            return None
        if earliest and parsed < earliest:
            self.fail(field, f"{label} cannot be before {earliest.isoformat()}.")
            return None
        if latest and parsed > latest:
            self.fail(field, f"{label} must be within the next two years.")
            return None
        self.clean[field] = parsed.isoformat()
        return parsed

    def done(self, message="Please fix the highlighted fields."):
        if self.errors:
            raise ApiError(400, message, self.errors)
        return self.clean


def normalize_phone(value):
    return re.sub(r"[\s-]", "", value or "")


def check_phone(checker, field="phone"):
    phone = checker.text(field, "Phone number", max_length=20)
    if phone is not None:
        phone = normalize_phone(phone)
        if not PHONE_PATTERN.match(phone):
            checker.fail(field, "Enter a Bangladeshi mobile number such as 01712345678.")
        else:
            checker.clean[field] = phone


def check_email(checker, field="email"):
    email = checker.text(field, "Email", max_length=254)
    if email is not None:
        if not EMAIL_PATTERN.match(email):
            checker.fail(field, "Enter a valid email address.")
        else:
            checker.clean[field] = email.lower()


def check_new_password(checker, field="password"):
    password = checker.data.get(field)
    if not isinstance(password, str) or not password:
        checker.fail(field, "Password is required.")
    elif len(password) < 8 or len(password) > 128:
        checker.fail(field, "Password must be 8 to 128 characters long.")
    elif not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        checker.fail(field, "Password must contain at least one letter and one number.")
    else:
        checker.clean[field] = password


def clean_listing(data, existing_available_from=None):
    """Validate the owner listing form (PB-05). Returns cleaned values and rent details."""
    checker = Checker(data)
    checker.text("title", "Title", min_length=5, max_length=100)
    checker.text("description", "Description", min_length=20, max_length=2000)
    listing_type = checker.choice("listingType", "Listing type (Sale or Rent)", ("sale", "rent"))
    property_type = checker.choice("propertyType", "Property type", PROPERTY_TYPES)
    checker.text("areaName", "Area", min_length=2, max_length=60)
    checker.choice("city", "City", CITIES)
    checker.text("address", "Address", min_length=5, max_length=160)
    checker.integer("sizeSqft", "Size", 100, 1_000_000)
    min_bedrooms = 0 if property_type in ("Plot", "Commercial", "Studio") else 1
    checker.integer("bedrooms", "Bedrooms", min_bedrooms, 20)
    checker.integer("bathrooms", "Bathrooms", 0, 20)
    checker.boolean("furnished")

    rent = None
    if listing_type == "sale":
        checker.integer("price", "Sale price", 1, MAX_SALE_PRICE)
    elif listing_type == "rent":
        rent_data = data.get("rent")
        if not isinstance(rent_data, dict):
            rent_data = {}
        rent_checker = Checker(rent_data)
        monthly = rent_checker.integer("monthlyRent", "Monthly rent", 1, MAX_MONTHLY_RENT)
        deposit = rent_checker.integer("securityDeposit", "Security deposit", 0, MAX_MONTHLY_RENT * 12)
        if monthly and deposit is not None and deposit > monthly * 12:
            rent_checker.fail("securityDeposit", "Security deposit cannot be more than 12 months of rent.")
        today = date.today()
        available = rent_data.get("availableFrom")
        if existing_available_from and available == existing_available_from:
            rent_checker.clean["availableFrom"] = available
        else:
            rent_checker.date("availableFrom", "Available-from date", earliest=today, latest=today + timedelta(days=730))
        rent_checker.integer("minLeaseMonths", "Minimum lease", 1, 60, required=False, default=12)
        rent_checker.boolean("utilitiesIncluded")
        rent_checker.choice("tenantPreference", "Tenant preference", TENANT_PREFERENCES)
        for field, message in rent_checker.errors.items():
            checker.fail(f"rent.{field}", message)
        rent = rent_checker.clean
        checker.clean["price"] = None

    cleaned = checker.done()
    return cleaned, rent
