from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import User, UserRole, VerificationStatus
from core.engines import calculate_isra_for_user, run_propmatch_for_user
from core.yoe import refresh_yoe_metrics
from core.tenancy_intelligence import refresh_all_tenancy_health_scores
from core.models import (
    Complaint,
    ComplaintStatus,
    IntentForm,
    IntentIdentity,
    IntentPurpose,
    Property,
    PropertyExpense,
    PropertyImage,
    PropertyStatus,
    PropertyType,
    RentLedger,
    RentLedgerStatus,
    TenancyHealthEvent,
    TenancyHealthScore,
    TenancyRecord,
    RoomType,
    Tenancy,
    TenancyStatus,
)


def unique_slug(title):
    base = slugify(title) or "property"
    slug = base
    index = 2
    while Property.objects.filter(slug=slug).exists():
        slug = f"{base}-{index}"
        index += 1
    return slug


class Command(BaseCommand):
    help = "Seed Year 1 proof data for ISRA + PropMatch demo flows."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete proof seed data before creating it.")

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write(self.style.WARNING("Clearing Year 1 proof data..."))
            RentLedger.objects.all().delete()
            TenancyHealthEvent.objects.all().delete()
            TenancyHealthScore.objects.all().delete()
            TenancyRecord.objects.all().delete()
            Complaint.objects.all().delete()
            Tenancy.objects.all().delete()
            PropertyExpense.objects.all().delete()
            PropertyImage.objects.filter(property__internal_notes__icontains="Year 1 proof").delete()
            Property.objects.filter(internal_notes__icontains="Year 1 proof").delete()
            User.objects.filter(email__endswith="@liable-demo.test").delete()

        admin = self._user("admin@liable-demo.test", "Liable Admin", UserRole.ADMIN)
        landlords = [
            self._user("landlord1@liable-demo.test", "David Chen", UserRole.LANDLORD),
            self._user("landlord2@liable-demo.test", "Sarah Mills", UserRole.LANDLORD),
            self._user("landlord3@liable-demo.test", "James Park", UserRole.LANDLORD),
        ]
        students = [
            self._user("student1@liable-demo.test", "Ahmed Rahman", UserRole.STUDENT),
            self._user("student2@liable-demo.test", "Priya Nair", UserRole.STUDENT),
            self._user("student3@liable-demo.test", "Liu Wei", UserRole.STUDENT),
            self._user("student4@liable-demo.test", "Amara Okonkwo", UserRole.STUDENT),
            self._user("student5@liable-demo.test", "Carlos Mendes", UserRole.STUDENT),
            self._user("student6@liable-demo.test", "Fatima Khan", UserRole.STUDENT),
        ]

        properties = self._properties(admin, landlords)
        self._intents_scores_matches(students)
        self._tenancies_complaints_expenses(students, properties, landlords)
        refresh_yoe_metrics()
        refresh_all_tenancy_health_scores()

        self.stdout.write(self.style.SUCCESS("Year 1 proof data ready."))
        self.stdout.write(self.style.SUCCESS("Login users use password: Password123!"))
        self.stdout.write(self.style.SUCCESS(f"Students: {len(students)} | Landlords: {len(landlords)} | Properties: {len(properties)}"))

    def _user(self, email, full_name, role):
        user, created = User.objects.update_or_create(
            email=email,
            defaults={
                "full_name": full_name,
                "phone": "+447000000000",
                "role": role,
                "is_active": True,
                "is_staff": role in [UserRole.ADMIN, UserRole.STAFF],
                "is_superuser": role == UserRole.ADMIN,
                "verification_status": VerificationStatus.APPROVED,
                "verified_at": timezone.now(),
            },
        )
        if created or not user.has_usable_password():
            user.set_password("Password123!")
            user.save(update_fields=["password"])
        return user

    def _properties(self, admin, landlords):
        today = timezone.now().date()
        rows = [
            ("Maple House Studio", "Manchester", "City Centre", 850, 70, landlords[0], PropertyType.STUDIO),
            ("Oak Road Ensuite", "Manchester", "Fallowfield", 720, 62, landlords[0], PropertyType.PG),
            ("Birch Lane Flat", "Manchester", "Hulme", 980, 78, landlords[1], PropertyType.APARTMENT),
            ("Park Avenue Room", "Leeds", "Headingley", 640, 58, landlords[1], PropertyType.PG),
            ("Canal Wharf Studio", "Birmingham", "Aston", 790, 65, landlords[2], PropertyType.STUDIO),
        ]
        created = []
        for index, (title, city, locality, rent, threshold, landlord, ptype) in enumerate(rows, start=1):
            prop, _ = Property.objects.update_or_create(
                title=title,
                defaults={
                    "slug": Property.objects.filter(title=title).first().slug if Property.objects.filter(title=title).exists() else unique_slug(title),
                    "description": "Year 1 proof property used for ISRA and PropMatch demonstrations.",
                    "created_by": admin,
                    "assigned_landlord": landlord,
                    "property_type": ptype,
                    "room_type": RoomType.PRIVATE if ptype == PropertyType.PG else RoomType.ENTIRE,
                    "bedrooms": 1,
                    "bathrooms": 1,
                    "area_sqft": 320 + index * 30,
                    "currency": "GBP",
                    "rent_monthly": Decimal(str(rent)),
                    "deposit_amount": Decimal(str(rent)),
                    "maintenance_amount": Decimal("0"),
                    "bills_included": index % 2 == 0,
                    "status": PropertyStatus.APPROVED,
                    "available_from": today + timezone.timedelta(days=7 * index),
                    "country": "United Kingdom",
                    "state": "England",
                    "city": city,
                    "locality": locality,
                    "address_line1": f"{20 + index} Demo Street",
                    "postal_code": f"M{index} 1AA",
                    "map_pin_verified": True,
                    "has_wifi": True,
                    "has_security": True,
                    "has_cctv": True,
                    "guests_allowed": True,
                    "is_featured": index <= 3,
                    "priority_rank": 100 - index,
                    "isra_threshold": threshold,
                    "internal_notes": "Year 1 proof seed data",
                },
            )
            PropertyImage.objects.get_or_create(
                property=prop,
                image_url=f"https://picsum.photos/seed/liable-proof-{index}/1200/800",
                defaults={"alt_text": title, "is_cover": True, "sort_order": 1},
            )
            created.append(prop)
        return created

    def _intents_scores_matches(self, students):
        today = timezone.now().date()
        rows = [
            ("Manchester", "City Centre", "Manchester Metropolitan University", 400, 900, True, "Student Visa", 365),
            ("Manchester", "Fallowfield", "University of Manchester", 350, 780, True, "Student Visa", 280),
            ("Leeds", "Headingley", "University of Leeds", 300, 700, True, "Graduate Visa", 450),
            ("Birmingham", "Aston", "Aston University", 350, 820, False, "Student Visa", 160),
            ("Manchester", "Hulme", "Manchester Metropolitan University", 450, 1050, True, "Skilled Worker", 700),
            ("Leeds", "City Centre", "Leeds Beckett University", 300, 680, False, "Student Visa", 120),
        ]
        for user, row in zip(students, rows):
            city, locality, uni, min_budget, max_budget, funds, visa, visa_days = row
            IntentForm.objects.update_or_create(
                user=user,
                defaults={
                    "identity": IntentIdentity.STUDENT,
                    "purpose": IntentPurpose.STUDY,
                    "room_type": "Studio" if max_budget >= 850 else "En-suite",
                    "budget_min": min_budget,
                    "budget_max": max_budget,
                    "city": city,
                    "preferred_locality": locality,
                    "university": uni,
                    "course": "MSc International Business",
                    "nationality": "India" if "student1" in user.email or "student2" in user.email else "China",
                    "visa_type": visa,
                    "visa_expiry": today + timezone.timedelta(days=visa_days),
                    "proof_of_funds_verified": funds,
                    "move_in_date": today + timezone.timedelta(days=28),
                    "lifestyle_preferences": {"quiet_household": True, "non_smoking": True},
                },
            )
            calculate_isra_for_user(user)
            run_propmatch_for_user(user)

    def _tenancies_complaints_expenses(self, students, properties, landlords):
        today = timezone.now().date()
        for index, user in enumerate(students[:3]):
            prop = properties[index]
            tenancy, _ = Tenancy.objects.update_or_create(
                user=user,
                property=prop,
                defaults={
                    "start_date": today - timezone.timedelta(days=30),
                    "end_date": today - timezone.timedelta(days=3) if index == 2 else today + timezone.timedelta(days=45 if index == 1 else 335),
                    "rent_amount": prop.rent_monthly,
                    "deposit_amount": prop.deposit_amount,
                    "status": TenancyStatus.ENDED if index == 2 else TenancyStatus.ACTIVE,
                    "deposit_status": "Protected",
                },
            )
            RentLedger.objects.update_or_create(
                tenancy=tenancy,
                due_date=today.replace(day=1),
                defaults={
                    "rent_amount": prop.rent_monthly,
                    "utility_amount": Decimal("50.00"),
                    "paid_amount": prop.rent_monthly + Decimal("50.00"),
                    "status": RentLedgerStatus.PAID,
                    "paid_at": timezone.now(),
                },
            )
            Complaint.objects.update_or_create(
                user=user,
                property=prop,
                title=f"Maintenance check {index + 1}",
                defaults={
                    "category": "Maintenance",
                    "description": "Demo complaint for admin and landlord visibility testing.",
                    "status": [ComplaintStatus.OPEN, ComplaintStatus.IN_PROGRESS, ComplaintStatus.RESOLVED][index],
                    "admin_notes": "Year 1 proof complaint flow.",
                    "resolved_at": timezone.now() if index == 2 else None,
                },
            )

        for index, prop in enumerate(properties):
            PropertyExpense.objects.update_or_create(
                property=prop,
                landlord=prop.assigned_landlord,
                category="FURNITURE",
                description="Demo furniture setup",
                defaults={
                    "amount": Decimal(str(500 + index * 120)),
                    "incurred_on": today - timezone.timedelta(days=15 + index),
                },
            )
