#!/usr/bin/env python
"""
seed_sample_data.py — safe, additive sample data for Liable production testing.

NEVER deletes existing records. All objects are created with get_or_create
so the script is idempotent (safe to run multiple times).

Usage (on the server):
    cd /var/www/liablebackend
    source venv/bin/activate
    python seed_sample_data.py

What it creates (only if they don't already exist):
    • 1 super-admin account
    • 1 staff account
    • 3 landlord accounts   (APPROVED)
    • 5 student accounts    (APPROVED)
    • 6 properties          (mix of APPROVED / DRAFT)
    • 5 student intents     (one per student)
    • 5 ISRA scores         (mix of LOW / MEDIUM / HIGH)
    • 3 active tenancies
    • 3 rent ledger entries
    • 2 complaints
"""

import os
import sys
import django
from pathlib import Path
from datetime import date, timedelta
from decimal import Decimal

# ── Bootstrap Django ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "liablewebsite.settings")
django.setup()

# ── Imports (after django.setup) ──────────────────────────────────────────────
from django.utils import timezone
from accounts.models import User
from core.models import (
    Property, IntentForm, ISRAscore, Tenancy, RentLedger, Complaint,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def p(msg):
    print(f"  {msg}")

def make_user(email, full_name, role, password="LiableTest2026!", verified=True, is_staff=False, is_superuser=False):
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "full_name": full_name,
            "role": role,
            "verification_status": "APPROVED" if verified else "PENDING",
            "is_staff": is_staff or is_superuser,
            "is_superuser": is_superuser,
            "is_active": True,
        },
    )
    if created:
        user.set_password(password)
        user.save()
        p(f"CREATED  {role:10s}  {email}  (password: {password})")
    else:
        p(f"EXISTS   {role:10s}  {email}")
    return user


def make_property(title, slug, city, landlord, status="APPROVED", rent=1200, deposit=1200,
                  bedrooms=2, bathrooms=1, prop_type="APARTMENT", cover_url=""):
    prop, created = Property.objects.get_or_create(
        slug=slug,
        defaults={
            "title": title,
            "city": city,
            "country": "United Kingdom",
            "state": "England",
            "locality": city,
            "property_type": prop_type,
            "room_type": "ENTIRE",
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "rent_monthly": Decimal(str(rent)),
            "deposit_amount": Decimal(str(deposit)),
            "currency": "GBP",
            "status": status,
            "furnish_status": "FULL",
            "bills_included": True,
            "has_wifi": True,
            "has_ac": bedrooms >= 2,
            "has_washing_machine": True,
            "has_security": True,
            "map_pin_verified": status == "APPROVED",
            "available_from": date.today(),
            "min_stay_months": 6,
            "max_stay_months": 12,
            "assigned_landlord": landlord,
            "created_by": landlord,
            "cover_image_url": cover_url or "https://images.unsplash.com/photo-1526129318478-62ed807ebdf9?fm=jpg&q=80&w=800",
            "isra_threshold": 55,
            "is_featured": status == "APPROVED",
        },
    )
    p(f"{'CREATED' if created else 'EXISTS '} PROPERTY  [{status:9s}]  {title} — £{rent}/mo")
    return prop


def make_intent(user, city="London", budget_min=600, budget_max=1400,
                university="University College London", course="MSc Computer Science",
                visa_type="Student Visa", move_days=30):
    intent, created = IntentForm.objects.get_or_create(
        user=user,
        defaults={
            "identity": "STUDENT",
            "purpose": "STUDY",
            "room_type": "ENTIRE",
            "budget_min": budget_min,
            "budget_max": budget_max,
            "city": city,
            "preferred_locality": "Zone 1-2",
            "university": university,
            "course": course,
            "nationality": "International",
            "visa_type": visa_type,
            "visa_expiry": date.today() + timedelta(days=365),
            "proof_of_funds_verified": True,
            "move_in_date": date.today() + timedelta(days=move_days),
        },
    )
    p(f"{'CREATED' if created else 'EXISTS '} INTENT  {user.email}  budget £{budget_min}–£{budget_max}")
    return intent


def make_isra(user, stability, financial, behavioural, risk_band, max_rent):
    total = stability + financial + behavioural
    score, created = ISRAscore.objects.get_or_create(
        user=user,
        defaults={
            "stability_score": stability,
            "financial_score": financial,
            "behavioural_score": behavioural,
            "total_score": total,
            "risk_band": risk_band,
            "recommended_max_rent": max_rent,
            "notes": f"Seeded profile. Risk: {risk_band}.",
            "calculated_at": timezone.now(),
        },
    )
    p(f"{'CREATED' if created else 'EXISTS '} ISRA  {user.email}  score={total}  band={risk_band}")
    return score


def make_tenancy(student, prop, status="ACTIVE", months=10, rent=None):
    start = date.today() - timedelta(days=60)
    end = start + timedelta(days=months * 30)
    rent_val = Decimal(str(rent)) if rent else prop.rent_monthly
    tenancy, created = Tenancy.objects.get_or_create(
        user=student,
        property=prop,
        defaults={
            "start_date": start,
            "end_date": end,
            "rent_amount": rent_val,
            "deposit_amount": prop.deposit_amount,
            "status": status,
            "deposit_status": "HELD",
        },
    )
    p(f"{'CREATED' if created else 'EXISTS '} TENANCY  {student.email} → {prop.title}  [{status}]")
    return tenancy


def make_rent_entry(tenancy, amount, month_label):
    due = date.today().replace(day=1)
    entry, created = RentLedger.objects.get_or_create(
        tenancy=tenancy,
        due_date=due,
        defaults={
            "rent_amount": Decimal(str(amount)),
            "paid_amount": Decimal(str(amount)),
            "utility_amount": Decimal("0"),
            "status": "PAID",
            "paid_at": timezone.now() - timedelta(days=5),
        },
    )
    p(f"{'CREATED' if created else 'EXISTS '} RENT     £{amount}  [{month_label}]")
    return entry


def make_complaint(student, prop, title, status="OPEN"):
    complaint, created = Complaint.objects.get_or_create(
        user=student,
        property=prop,
        title=title,
        defaults={
            "description": f"Sample complaint: {title}. Created by seed script for testing.",
            "category": "MAINTENANCE",
            "status": status,
        },
    )
    p(f"{'CREATED' if created else 'EXISTS '} COMPLAINT  [{status:11s}]  {title}")
    return complaint


# ── MAIN ──────────────────────────────────────────────────────────────────────

def run():
    print("\n" + "=" * 60)
    print("  Liable — Sample Data Seeder")
    print("  Safe & additive — no existing records modified")
    print("=" * 60 + "\n")

    # ── Users ──────────────────────────────────────────────────
    print("[ USERS ]")
    admin = make_user(
        "admin@lgsltd.uk", "Liable Admin", "ADMIN",
        password="AdminLiable2026!",
        is_staff=True, is_superuser=True,
    )
    staff = make_user(
        "staff@lgsltd.uk", "Liable Staff", "STAFF",
        password="StaffLiable2026!",
        is_staff=True,
    )
    landlord1 = make_user("james.chen@landlord.test", "James Chen",       "LANDLORD")
    landlord2 = make_user("sarah.patel@landlord.test", "Sarah Patel",     "LANDLORD")
    landlord3 = make_user("david.osei@landlord.test", "David Osei",       "LANDLORD")

    student1 = make_user("aisha.rahman@student.test",  "Aisha Rahman",    "STUDENT")
    student2 = make_user("leo.kim@student.test",       "Leo Kim",         "STUDENT")
    student3 = make_user("fatima.ali@student.test",    "Fatima Ali",      "STUDENT")
    student4 = make_user("carlos.gomez@student.test",  "Carlos Gomez",    "STUDENT")
    student5 = make_user("priya.nair@student.test",    "Priya Nair",      "STUDENT")

    # ── Properties ─────────────────────────────────────────────
    print("\n[ PROPERTIES ]")
    prop1 = make_property(
        "Camden Studio Flat", "camden-studio-flat-001", "London", landlord1,
        status="APPROVED", rent=1150, deposit=1150, bedrooms=0,
        prop_type="STUDIO",
        cover_url="https://images.unsplash.com/photo-1512359953714-f0c9a632ab85?fm=jpg&q=80&w=800",
    )
    prop2 = make_property(
        "Shoreditch 2-Bed Apartment", "shoreditch-2bed-apt-002", "London", landlord1,
        status="APPROVED", rent=1800, deposit=1800, bedrooms=2,
        cover_url="https://images.unsplash.com/photo-1510265119258-db115b0e8172?fm=jpg&q=80&w=800",
    )
    prop3 = make_property(
        "Brixton Shared House Room", "brixton-shared-house-003", "London", landlord2,
        status="APPROVED", rent=850, deposit=850, bedrooms=1,
        prop_type="OTHER",
        cover_url="https://images.unsplash.com/photo-1550647512-8b8a24d4f646?fm=jpg&q=80&w=800",
    )
    prop4 = make_property(
        "Hackney 1-Bed Flat", "hackney-1bed-flat-004", "London", landlord2,
        status="APPROVED", rent=1300, deposit=1300, bedrooms=1,
        cover_url="https://images.unsplash.com/photo-1526129318478-62ed807ebdf9?fm=jpg&q=80&w=800",
    )
    prop5 = make_property(
        "Manchester City Centre Studio", "manchester-studio-005", "Manchester", landlord3,
        status="APPROVED", rent=900, deposit=900, bedrooms=0,
        prop_type="STUDIO",
        cover_url="https://images.unsplash.com/photo-1480449649358-ee14c6ee0b17?fm=jpg&q=80&w=800",
    )
    prop6 = make_property(
        "Birmingham 2-Bed Near Uni", "birmingham-2bed-006", "Birmingham", landlord3,
        status="DRAFT", rent=1050, deposit=1050, bedrooms=2,
        cover_url="https://images.unsplash.com/photo-1609679604891-f69f884eddae?fm=jpg&q=80&w=800",
    )

    # ── Student Intents ────────────────────────────────────────
    print("\n[ STUDENT INTENTS ]")
    make_intent(student1, city="London",     budget_min=900,  budget_max=1300, move_days=20)
    make_intent(student2, city="London",     budget_min=1500, budget_max=2000,
                university="London School of Economics", course="MSc Finance", move_days=45)
    make_intent(student3, city="London",     budget_min=700,  budget_max=1000, move_days=15)
    make_intent(student4, city="Manchester", budget_min=600,  budget_max=950,
                university="University of Manchester", course="MBA", move_days=30)
    make_intent(student5, city="London",     budget_min=1100, budget_max=1500,
                university="King's College London", course="MSc Data Science", move_days=10)

    # ── ISRA Scores ────────────────────────────────────────────
    print("\n[ ISRA SCORES ]")
    make_isra(student1, stability=28, financial=25, behavioural=24, risk_band="LOW",    max_rent=1300)
    make_isra(student2, stability=30, financial=28, behavioural=27, risk_band="LOW",    max_rent=2000)
    make_isra(student3, stability=20, financial=18, behavioural=16, risk_band="MEDIUM", max_rent=950)
    make_isra(student4, stability=15, financial=12, behavioural=10, risk_band="HIGH",   max_rent=800)
    make_isra(student5, stability=26, financial=24, behavioural=23, risk_band="LOW",    max_rent=1500)

    # ── Tenancies ──────────────────────────────────────────────
    print("\n[ TENANCIES ]")
    t1 = make_tenancy(student1, prop4, status="ACTIVE", months=10)
    t2 = make_tenancy(student2, prop2, status="ACTIVE", months=12)
    t3 = make_tenancy(student5, prop1, status="ACTIVE", months=6)

    # ── Rent Ledger ────────────────────────────────────────────
    print("\n[ RENT LEDGER ]")
    try:
        make_rent_entry(t1, 1300, "Jun 2026")
        make_rent_entry(t2, 1800, "Jun 2026")
        make_rent_entry(t3, 1150, "Jun 2026")
    except Exception as e:
        p(f"SKIP rent ledger ({e})")

    # ── Complaints ─────────────────────────────────────────────
    print("\n[ COMPLAINTS ]")
    try:
        make_complaint(student1, prop4, "Heating not working in bedroom", status="OPEN")
        make_complaint(student5, prop1, "Hot water pressure very low",    status="IN_PROGRESS")
    except Exception as e:
        p(f"SKIP complaints ({e})")

    # ── Summary ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  SEED COMPLETE")
    print("=" * 60)
    print(f"""
  LOGIN CREDENTIALS (all test accounts)
  ──────────────────────────────────────────────
  Admin    admin@lgsltd.uk          AdminLiable2026!
  Staff    staff@lgsltd.uk          StaffLiable2026!
  ──────────────────────────────────────────────
  Landlord james.chen@landlord.test LiableTest2026!
  Landlord sarah.patel@landlord.test LiableTest2026!
  Landlord david.osei@landlord.test LiableTest2026!
  ──────────────────────────────────────────────
  Student  aisha.rahman@student.test LiableTest2026!  LOW  risk
  Student  leo.kim@student.test      LiableTest2026!  LOW  risk
  Student  fatima.ali@student.test   LiableTest2026!  MED  risk
  Student  carlos.gomez@student.test LiableTest2026!  HIGH risk
  Student  priya.nair@student.test   LiableTest2026!  LOW  risk

  Dashboard: https://app.lgsltd.uk/admin
  Website:   https://lgsltd.uk
""")


if __name__ == "__main__":
    run()
