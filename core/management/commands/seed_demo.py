import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from core.models import (
    Property, PropertyImage, PropertyVideo,
    BlogPost,
    PropertyStatus, PropertyType, RoomType, FurnishStatus, VideoProvider
)

CITIES = ["London", "Manchester", "Birmingham", "Leeds", "Liverpool", "Bristol", "Glasgow", "Edinburgh"]
LOCALITIES = ["City Centre", "Shoreditch", "Camden", "Canary Wharf", "Greenwich", "Wembley", "Stratford", "Croydon"]
COUNTRIES = ["United Kingdom"]
STATES = ["England", "England", "England", "Scotland"]
TITLES = [
    "Modern Studio Near Metro",
    "Luxury Apartment With Gym",
    "Budget Friendly Shared Room",
    "Premium Student Accommodation",
    "Spacious 2BHK With Balcony",
    "Fully Furnished City Flat",
    "Co-living Space For Students",
    "Riverside Apartment With View",
]

BLOG_TITLES = [
    "Ultimate Guide to Student Accommodation in London",
    "Top 10 Neighborhoods for Young Professionals",
    "How to Navigate UK Rental Agreements",
    "Money-Saving Tips for International Students",
    "Landlord's Guide to Property Management",
    "Preparing for University: A Complete Checklist",
    "How to Pick the Right Flatmate",
    "Understanding Deposits & Deposit Protection",
    "Best Apps for Students in the UK",
    "How to Avoid Rental Scams",
]

BLOG_EXCERPTS = [
    "Everything you need to know to find your perfect place.",
    "Discover areas with the best work-life balance.",
    "Know your rights and responsibilities before signing.",
    "Practical advice on saving money in the UK.",
    "Best practices for landlords and property care.",
]

def unique_slug(model, base: str, slug_field="slug", max_len=220):
    base = slugify(base)[:max_len] or "item"
    slug = base
    i = 2
    qs = model.objects.all()
    while qs.filter(**{slug_field: slug}).exists():
        suffix = f"-{i}"
        slug = (base[: max_len - len(suffix)] + suffix)
        i += 1
    return slug


class Command(BaseCommand):
    help = "Seed demo data: 20 properties + 10 blogs"

    def add_arguments(self, parser):
        parser.add_argument("--properties", type=int, default=20)
        parser.add_argument("--blogs", type=int, default=10)
        parser.add_argument("--clear", action="store_true", help="Delete existing demo data first")

    def handle(self, *args, **opts):
        prop_count = opts["properties"]
        blog_count = opts["blogs"]
        clear = opts["clear"]

        if clear:
            self.stdout.write(self.style.WARNING("Clearing existing demo data..."))
            PropertyVideo.objects.all().delete()
            PropertyImage.objects.all().delete()
            Property.objects.all().delete()
            BlogPost.objects.all().delete()

        created_props = self._seed_properties(prop_count)
        created_blogs = self._seed_blogs(blog_count)

        self.stdout.write(self.style.SUCCESS(f"✅ Seed completed"))
        self.stdout.write(self.style.SUCCESS(f"   Properties: {created_props}"))
        self.stdout.write(self.style.SUCCESS(f"   Blogs:      {created_blogs}"))

    def _seed_properties(self, n: int) -> int:
        now = timezone.now()
        props_created = 0

        property_types = [c[0] for c in PropertyType.choices]
        room_types = [c[0] for c in RoomType.choices]
        furnish_types = [c[0] for c in FurnishStatus.choices]

        for i in range(1, n + 1):
            title = random.choice(TITLES) + f" #{i}"
            slug = unique_slug(Property, title, max_len=260)

            city = random.choice(CITIES)
            locality = random.choice(LOCALITIES)
            state = random.choice(STATES)
            country = random.choice(COUNTRIES)

            rent = Decimal(random.randrange(650, 2500))  # monthly rent
            deposit = rent * Decimal("1.5")
            maintenance = Decimal(random.randrange(0, 150))

            p = Property.objects.create(
                title=title,
                slug=slug,
                description=(
                    "Demo listing for testing. Clean rooms, good transport links, "
                    "near shops and universities. Suitable for students and professionals."
                ),

                property_type=random.choice(property_types),
                room_type=random.choice(room_types),

                bedrooms=random.randint(0, 4),
                bathrooms=random.randint(1, 3),
                area_sqft=random.choice([None, 250, 320, 450, 650, 900, 1200]),

                currency="GBP",
                rent_monthly=rent,
                deposit_amount=deposit,
                maintenance_amount=maintenance,
                bills_included=random.choice([True, False]),

                status=PropertyStatus.APPROVED,
                available_from=(now.date()),

                country=country,
                state=state,
                city=city,
                locality=locality,
                address_line1=f"{random.randint(10, 220)} Demo Street",
                address_line2="",
                postal_code=f"EC1V {random.randint(1, 9)}NX",

                latitude=None,
                longitude=None,
                map_pin_verified=False,

                furnish_status=random.choice(furnish_types),

                has_wifi=random.choice([True, False]),
                has_ac=random.choice([True, False]),
                has_parking=random.choice([True, False]),
                has_gym=random.choice([True, False]),
                has_pool=random.choice([True, False]),
                has_lift=random.choice([True, False]),
                has_power_backup=random.choice([True, False]),
                has_security=random.choice([True, False]),
                has_cctv=random.choice([True, False]),
                has_washing_machine=random.choice([True, False]),

                smoking_allowed=False,
                pets_allowed=random.choice([True, False]),
                alcohol_allowed=False,
                guests_allowed=True,

                cover_image_url="https://picsum.photos/seed/property-cover/1200/800",
                featured_video_url="",

                is_featured=(i <= 4),
                priority_rank=(100 - i),

                internal_notes="Demo seed data",
            )

            # images 2-5
            img_count = random.randint(2, 5)
            cover_index = random.randint(1, img_count)
            for j in range(1, img_count + 1):
                PropertyImage.objects.create(
                    property=p,
                    image_url=f"https://picsum.photos/seed/{p.slug}-{j}/1200/800",
                    alt_text=f"{p.title} image {j}",
                    caption="",
                    is_cover=(j == cover_index),
                    sort_order=j,
                )

            # videos 0-2
            vid_count = random.randint(0, 2)
            for k in range(1, vid_count + 1):
                PropertyVideo.objects.create(
                    property=p,
                    provider=VideoProvider.YOUTUBE,
                    title=f"{p.title} Walkthrough {k}",
                    video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    thumbnail_url=f"https://picsum.photos/seed/{p.slug}-thumb-{k}/800/450",
                    is_featured=(k == 1),
                    sort_order=k,
                )

            props_created += 1

        return props_created

    def _seed_blogs(self, n: int) -> int:
        created = 0
        now = timezone.now()

        for i in range(1, n + 1):
            title = BLOG_TITLES[(i - 1) % len(BLOG_TITLES)]
            title = f"{title} (Demo {i})"
            slug = unique_slug(BlogPost, title)

            excerpt = random.choice(BLOG_EXCERPTS)
            content = f"""
<h2>{title}</h2>
<p>This is demo blog content used for testing your News/Blog pages.</p>
<p><strong>Tip:</strong> You can replace this HTML with real content later.</p>
<ul>
  <li>Point 1: Demo</li>
  <li>Point 2: Demo</li>
  <li>Point 3: Demo</li>
</ul>
<p>Created on {now.date()}.</p>
""".strip()

            BlogPost.objects.create(
                slug=slug,
                title=title,
                excerpt=excerpt,
                content=content,
                is_published=True,
                published_at=now - timezone.timedelta(days=random.randint(0, 30)),
                created_at=now - timezone.timedelta(days=random.randint(0, 60)),
            )
            created += 1

        return created
